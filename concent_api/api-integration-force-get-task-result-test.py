#!/usr/bin/env python3

import os
import sys
import hashlib
import random
from base64 import b64encode

from golem_messages import message
from golem_messages import shortcuts

from utils.helpers import get_current_utc_timestamp
from utils.helpers import get_storage_file_path
from utils.helpers import sign_message
from utils.testing_helpers import generate_ecc_key_pair

from api_testing_common import api_request
from api_testing_common import assert_condition
from api_testing_common import create_client_auth_message
from api_testing_common import count_fails
from api_testing_common import execute_tests
from api_testing_common import get_task_id_and_subtask_id
from api_testing_common import get_tests_list
from api_testing_common import parse_arguments
from api_testing_common import timestamp_to_isoformat

from freezegun import freeze_time

from protocol_constants import get_protocol_constants
from protocol_constants import print_protocol_constants

import requests

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "concent_api.settings")

(PROVIDER_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY)  = generate_ecc_key_pair()
(REQUESTOR_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY) = generate_ecc_key_pair()


def get_force_get_task_result(task_id, subtask_id, current_time, cluster_consts, size, package_hash, provider_public_key = None, requestor_public_key = None):

    compute_task_def = message.ComputeTaskDef()
    compute_task_def['task_id'] = task_id
    compute_task_def['subtask_id'] = subtask_id
    compute_task_def['deadline'] = current_time + cluster_consts.subtask_verification_time
    task_to_compute = message.TaskToCompute(
        provider_public_key=provider_public_key if provider_public_key is not None else PROVIDER_PUBLIC_KEY,
        requestor_public_key=requestor_public_key if requestor_public_key is not None else REQUESTOR_PUBLIC_KEY,
        compute_task_def = compute_task_def,
        price=0,
    )
    sign_message(task_to_compute, REQUESTOR_PRIVATE_KEY)

    report_computed_task = message.ReportComputedTask(
        task_to_compute = task_to_compute,
        size            = size,
        package_hash    = package_hash,
        subtask_id = subtask_id,
    )

    with freeze_time(timestamp_to_isoformat(current_time)):
        force_get_task_result = message.concents.ForceGetTaskResult(
            report_computed_task = report_computed_task,
        )

    return force_get_task_result


def upload_file_to_storage_cluster(file_content, file_path, upload_token):
    dumped_upload_token = shortcuts.dump(upload_token, None, CONCENT_PUBLIC_KEY)
    b64_encoded_token = b64encode(dumped_upload_token).decode()
    headers = {
        'Authorization': 'Golem ' + b64_encoded_token,
        'Concent-Auth': b64encode(
            create_client_auth_message(PROVIDER_PRIVATE_KEY, PROVIDER_PUBLIC_KEY, CONCENT_PUBLIC_KEY)).decode(),
        'Concent-upload-path': file_path,
        'Content-Type': 'application/octet-stream'
    }
    return requests.post(
        "{}upload/".format(STORAGE_CLUSTER_ADDRESS),
        headers=headers,
        data=file_content,
        verify=False
    )


def main():
    (cluster_url, patterns) = parse_arguments()
    cluster_consts  = get_protocol_constants(cluster_url)
    print_protocol_constants(cluster_consts)
    test_id = str(random.randrange(1, 100000))

    tests_to_execute = get_tests_list(patterns, list(globals().keys()))
    execute_tests(
        tests_to_execute=tests_to_execute,
        objects=globals(),
        cluster_consts=cluster_consts,
        cluster_url=cluster_url,
        test_id=test_id,
    )

    if count_fails.get_fails() > 0:
        count_fails.print_fails()
    print("END")


@count_fails
def test_case_1_test_for_existing_file(cluster_consts, cluster_url, test_id):
    current_time    = get_current_utc_timestamp()
    (subtask_id, task_id) = get_task_id_and_subtask_id(test_id, 'existing_file')

    file_content = task_id
    file_size = len(file_content)
    file_check_sum = 'sha1:' + hashlib.sha1(file_content.encode()).hexdigest()
    file_path = get_storage_file_path(task_id, subtask_id)

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
        force_get_task_result_upload.file_transfer_token
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
            package_hash = '098f6bcd4621d373cade4e832627b4f6'
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
        from concent_api.settings import CONCENT_PUBLIC_KEY, STORAGE_CLUSTER_ADDRESS
        main()
    except requests.exceptions.ConnectionError as exception:
        print("\nERROR: Failed connect to the server.\n", file = sys.stderr)
        sys.exit(str(exception))
