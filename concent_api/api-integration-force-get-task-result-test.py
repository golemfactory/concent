#!/usr/bin/env python3

import os
import sys
import hashlib
import time
import random
from base64 import b64encode

from golem_messages import message
from golem_messages import shortcuts

from utils.helpers import get_current_utc_timestamp
from utils.helpers import get_storage_file_path
from utils.helpers import sign_message
from utils.testing_helpers import generate_ecc_key_pair

from api_testing_common import api_request
from api_testing_common import create_client_auth_message
from api_testing_common import timestamp_to_isoformat

from freezegun import freeze_time

from protocol_constants import get_protocol_constants

import requests

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "concent_api.settings")

(PROVIDER_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY)  = generate_ecc_key_pair()
(REQUESTOR_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY) = generate_ecc_key_pair()


def parse_command_line(command_line):
    if len(command_line) <= 1:
        sys.exit('Not enough arguments')

    if len(command_line) >= 3:
        sys.exit('Too many arguments')

    cluster_url = command_line[1]
    return cluster_url


def upload_new_file_on_cluster(task_id, subtask_id, cluster_consts, current_time):

    file_content    = task_id
    file_size       = len(file_content)
    file_check_sum  = 'sha1:' + hashlib.sha1(file_content.encode()).hexdigest()
    file_path       = get_storage_file_path(task_id, subtask_id)

    file_transfer_token = message.FileTransferToken()
    file_transfer_token.token_expiration_deadline = int(
        current_time +
        (cluster_consts.concent_messaging_time * 3) +
        (cluster_consts.maximum_download_time * 2)
    )
    file_transfer_token.storage_cluster_address         = STORAGE_CLUSTER_ADDRESS
    file_transfer_token.authorized_client_public_key    = CONCENT_PUBLIC_KEY
    file_transfer_token.operation                       = 'upload'

    file_transfer_token.files                   = [message.FileTransferToken.FileInfo()]
    file_transfer_token.files[0]['path']        = file_path
    file_transfer_token.files[0]['checksum']    = file_check_sum
    file_transfer_token.files[0]['size']        = file_size

    upload_token    = shortcuts.dump(file_transfer_token, CONCENT_PRIVATE_KEY, CONCENT_PUBLIC_KEY)
    encrypted_token = b64encode(upload_token).decode()

    authorized_golem_transfer_token = 'Golem ' + encrypted_token

    headers = {
            'Authorization': authorized_golem_transfer_token,
            'Concent-Client-Public-Key': b64encode(CONCENT_PUBLIC_KEY).decode(),
            'Concent-upload-path': file_path,
            'Content-Type': 'application/octet-stream'
    }

    response = requests.post("{}".format(STORAGE_CLUSTER_ADDRESS + 'upload/'), headers = headers, data = file_content, verify = False)
    return (response.status_code, file_size, file_check_sum)


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


def main():
    cluster_url     = parse_command_line(sys.argv)
    current_time    = get_current_utc_timestamp()
    subtask_id      = str(random.randrange(1, 100000))
    task_id         = subtask_id + 'existing_file'
    cluster_consts  = get_protocol_constants(cluster_url)

    (response_status_code, file_size, file_check_sum) = upload_new_file_on_cluster(
        task_id,
        subtask_id,
        cluster_consts,
        current_time,
    )
    if response_status_code == 200:
        print('\nCreated file with task_id {}. Checksum of this file is {}, and size of this file is {}.\n'.format(task_id, file_check_sum, file_size))
    else:
        print('File has not been stored on cluster')
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
            'Content-Type':                     'application/octet-stream',
        },
        expected_status=200,
        expected_message_type=message.concents.AckForceGetTaskResult.TYPE,
        expected_content_type='application/octet-stream',
    )
    time.sleep(10)

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
    time.sleep(10)

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

    # Case 2 - test for non existing file
    subtask_id      = str(random.randrange(1, 100000))
    task_id = subtask_id + 'non_existing_file'
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
    time.sleep(10)

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
    time.sleep(10)

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
        from concent_api.settings import CONCENT_PUBLIC_KEY, CONCENT_PRIVATE_KEY, STORAGE_CLUSTER_ADDRESS
        main()
    except requests.exceptions.ConnectionError as exception:
        print("\nERROR: Failed connect to the server.\n", file = sys.stderr)
        sys.exit(str(exception))
