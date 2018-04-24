#!/usr/bin/env python3

import os
import sys
import hashlib
from freezegun import freeze_time

from golem_messages import message

from utils.helpers import get_current_utc_timestamp
from utils.helpers import get_storage_result_file_path
from utils.helpers import upload_file_to_storage_cluster
from api_testing_common import api_request
from api_testing_common import assert_condition
from api_testing_common import count_fails
from api_testing_common import create_client_auth_message
from api_testing_common import create_signed_task_to_compute
from api_testing_common import get_task_id_and_subtask_id
from api_testing_common import PROVIDER_PRIVATE_KEY
from api_testing_common import PROVIDER_PUBLIC_KEY
from api_testing_common import REQUESTOR_PRIVATE_KEY
from api_testing_common import REQUESTOR_PUBLIC_KEY
from api_testing_common import run_tests
from api_testing_common import timestamp_to_isoformat
from api_testing_common import upload_file_to_storage_cluster

import requests

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "concent_api.settings")


def get_force_get_task_result(task_id, subtask_id, current_time, cluster_consts, size, package_hash):
    task_to_compute = create_signed_task_to_compute(
        task_id=task_id,
        subtask_id=subtask_id,
        deadline=current_time,
        price=0,
    )

    with freeze_time(timestamp_to_isoformat(current_time - 1)):
        report_computed_task = message.ReportComputedTask(
            task_to_compute=task_to_compute,
            size=size,
            package_hash=package_hash,
            subtask_id=subtask_id,
        )

    with freeze_time(timestamp_to_isoformat(current_time)):
        force_get_task_result = message.concents.ForceGetTaskResult(
            report_computed_task=report_computed_task,
        )

    return force_get_task_result


@count_fails
def test_case_1_test_for_existing_file(cluster_consts, cluster_url, test_id):
    current_time    = get_current_utc_timestamp()
    (subtask_id, task_id) = get_task_id_and_subtask_id(test_id, 'existing_file')

    file_content = task_id
    file_size = len(file_content)
    file_check_sum = 'sha1:' + hashlib.sha1(file_content.encode()).hexdigest()
    file_path = get_storage_result_file_path(
        task_id=task_id,
        subtask_id=subtask_id,
    )

    # Case 1 - test for existing file
    api_request(
        cluster_url,
        'send',
        REQUESTOR_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        get_force_get_task_result(
            task_id,
            subtask_id,
            current_time,
            cluster_consts,
            size         = file_size,
            package_hash = file_check_sum,
        ),
        headers = {
            'Content-Type': 'application/octet-stream',
        },
        expected_status=200,
        expected_message_type=message.concents.AckForceGetTaskResult.TYPE,
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
        },
        expected_status=200,
        expected_message_type=message.concents.ForceGetTaskResultUpload.TYPE,
        expected_content_type='application/octet-stream',
    )

    response = upload_file_to_storage_cluster(
        file_content,
        file_path,
        force_get_task_result_upload.file_transfer_token,
        PROVIDER_PRIVATE_KEY,
        PROVIDER_PUBLIC_KEY,
    )

    assert_condition(response.status_code, 200, 'File has not been stored on cluster')
    print('\nUploaded file with task_id {}. Checksum of this file is {}, and size of this file is {}.\n'.format(
        task_id,
        file_check_sum,
        file_size
    ))

    api_request(
        cluster_url,
        'receive',
        REQUESTOR_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        create_client_auth_message(REQUESTOR_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY, CONCENT_PUBLIC_KEY),
        headers = {
            'Content-Type': 'application/octet-stream',
        },
        expected_status=200,
        expected_message_type=message.concents.ForceGetTaskResultDownload.TYPE,
        expected_content_type='application/octet-stream',
    )


@count_fails
def test_case_2_test_for_non_existing_file(cluster_consts, cluster_url, test_id):
    current_time    = get_current_utc_timestamp()
    (subtask_id, task_id) = get_task_id_and_subtask_id(test_id, 'non_existing_file')

    api_request(
        cluster_url,
        'send',
        REQUESTOR_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        get_force_get_task_result(
            task_id,
            subtask_id,
            current_time,
            cluster_consts,
            size    = 1024,
            package_hash = 'sha1:b3ff7013c4644cdcbb6c7e4f1e5fdb10b9ceda5d'
        ),
        headers = {
            'Content-Type':                     'application/octet-stream',
        },
        expected_status=200,
        expected_message_type=message.concents.AckForceGetTaskResult.TYPE,
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
        },
        expected_status=200,
        expected_message_type=message.concents.ForceGetTaskResultUpload.TYPE,
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
        },
        expected_status=204,
    )


if __name__ == '__main__':
    try:
        from concent_api.settings import CONCENT_PUBLIC_KEY
        run_tests(globals())
    except requests.exceptions.ConnectionError as exception:
        print("\nERROR: Failed connect to the server.\n", file=sys.stderr)
        sys.exit(str(exception))
