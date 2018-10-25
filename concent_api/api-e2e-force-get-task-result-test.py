#!/usr/bin/env python3

import os
import sys
import hashlib
import time

from freezegun import freeze_time

from golem_messages import message
from golem_messages.factories.tasks import ReportComputedTaskFactory

from common.helpers import get_current_utc_timestamp
from common.helpers import get_storage_result_file_path
from common.helpers import upload_file_to_storage_cluster
from common.helpers import sign_message
from api_testing_common import api_request
from api_testing_common import assert_condition
from api_testing_common import count_fails
from api_testing_common import create_client_auth_message
from api_testing_common import create_signed_task_to_compute
from api_testing_common import PROVIDER_PRIVATE_KEY
from api_testing_common import PROVIDER_PUBLIC_KEY
from api_testing_common import REQUESTOR_PRIVATE_KEY
from api_testing_common import REQUESTOR_PUBLIC_KEY
from api_testing_common import run_tests
from api_testing_common import timestamp_to_isoformat
from protocol_constants import ProtocolConstants

import requests

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "concent_api.settings")


def get_force_get_task_result(
    current_time: int,
    size: int,
    package_hash: str,
) -> message.concents.ForceGetTaskResult:
    task_to_compute = create_signed_task_to_compute(
        deadline=current_time,
        price=1,
    )

    with freeze_time(timestamp_to_isoformat(current_time - 1)):
        report_computed_task = ReportComputedTaskFactory(
            task_to_compute=task_to_compute,
            size=size,
            package_hash=package_hash,
        )
        sign_message(report_computed_task, PROVIDER_PRIVATE_KEY)

    with freeze_time(timestamp_to_isoformat(current_time)):
        force_get_task_result = message.concents.ForceGetTaskResult(
            report_computed_task=report_computed_task,
        )

    return force_get_task_result


@count_fails
def test_case_1_test_for_existing_file(cluster_consts: ProtocolConstants, cluster_url: str) -> None:
    current_time = get_current_utc_timestamp()

    file_content = 'test'
    file_size = len(file_content)
    file_check_sum = 'sha1:' + hashlib.sha1(file_content.encode()).hexdigest()

    force_get_task_result = get_force_get_task_result(
        current_time,
        size=file_size,
        package_hash=file_check_sum,
    )

    file_path = get_storage_result_file_path(
        task_id=force_get_task_result.task_id,
        subtask_id=force_get_task_result.subtask_id,
    )

    # Case 1 - test for existing file
    api_request(
        cluster_url,
        'send',
        REQUESTOR_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        force_get_task_result,
        headers = {
            'Content-Type': 'application/octet-stream',
            'Concent-Golem-Messages-Version': GOLEM_MESSAGES_VERSION,
        },
        expected_status=200,
        expected_message_type=message.concents.AckForceGetTaskResult,
        expected_content_type='application/octet-stream',
    )

    force_get_task_result_upload = api_request(
        cluster_url,
        'receive',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        create_client_auth_message(PROVIDER_PRIVATE_KEY, PROVIDER_PUBLIC_KEY, CONCENT_PUBLIC_KEY),
        headers = {
            'Content-Type': 'application/octet-stream',
            'Concent-Golem-Messages-Version': GOLEM_MESSAGES_VERSION,
        },
        expected_status=200,
        expected_message_type=message.concents.ForceGetTaskResultUpload,
        expected_content_type='application/octet-stream',
    )

    response = upload_file_to_storage_cluster(
        file_content,
        file_path,
        force_get_task_result_upload.file_transfer_token,  # type: ignore
        PROVIDER_PRIVATE_KEY,
        PROVIDER_PUBLIC_KEY,
        CONCENT_PUBLIC_KEY,
        STORAGE_CLUSTER_ADDRESS,
    )

    assert_condition(response.status_code, 200, 'File has not been stored on cluster')
    print('\nUploaded file with task_id {}. Checksum of this file is {}, and size of this file is {}.\n'.format(
        force_get_task_result.task_id,
        file_check_sum,
        file_size
    ))
    time.sleep(0.5)

    api_request(
        cluster_url,
        'receive',
        REQUESTOR_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        create_client_auth_message(REQUESTOR_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY, CONCENT_PUBLIC_KEY),
        headers = {
            'Content-Type': 'application/octet-stream',
            'Concent-Golem-Messages-Version': GOLEM_MESSAGES_VERSION,
        },
        expected_status=200,
        expected_message_type=message.concents.ForceGetTaskResultDownload,
        expected_content_type='application/octet-stream',
    )


@count_fails
def test_case_2_test_for_non_existing_file(cluster_consts: ProtocolConstants, cluster_url: str) -> None:
    current_time    = get_current_utc_timestamp()

    api_request(
        cluster_url,
        'send',
        REQUESTOR_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        get_force_get_task_result(
            current_time,
            size    = 1024,
            package_hash = 'sha1:b3ff7013c4644cdcbb6c7e4f1e5fdb10b9ceda5d'
        ),
        headers = {
            'Content-Type':                     'application/octet-stream',
            'Concent-Golem-Messages-Version': GOLEM_MESSAGES_VERSION,
        },
        expected_status=200,
        expected_message_type=message.concents.AckForceGetTaskResult,
        expected_content_type='application/octet-stream',
    )

    api_request(
        cluster_url,
        'receive',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        create_client_auth_message(PROVIDER_PRIVATE_KEY, PROVIDER_PUBLIC_KEY, CONCENT_PUBLIC_KEY),
        headers = {
            'Content-Type': 'application/octet-stream',
            'Concent-Golem-Messages-Version': GOLEM_MESSAGES_VERSION,
        },
        expected_status=200,
        expected_message_type=message.concents.ForceGetTaskResultUpload,
        expected_content_type='application/octet-stream',
    )

    api_request(
        cluster_url,
        'receive',
        REQUESTOR_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        create_client_auth_message(REQUESTOR_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY, CONCENT_PUBLIC_KEY),
        headers = {
            'Content-Type': 'application/octet-stream',
            'Concent-Golem-Messages-Version': GOLEM_MESSAGES_VERSION,
        },
        expected_status=204,
    )


if __name__ == '__main__':
    try:
        from concent_api.settings import CONCENT_PUBLIC_KEY
        from concent_api.settings import GOLEM_MESSAGES_VERSION
        from concent_api.settings import STORAGE_CLUSTER_ADDRESS
        run_tests(globals())
    except requests.exceptions.ConnectionError as exception:
        print("\nERROR: Failed connect to the server.\n", file=sys.stderr)
        sys.exit(str(exception))
