#!/usr/bin/env python3

import os
import sys
import datetime
import hashlib
import random
import requests
import time

from base64                          import b64encode
from golem_messages                  import message
from golem_messages                  import shortcuts
from golem_messages.message.concents import AckForceGetTaskResult, ForceGetTaskResultUpload, ForceGetTaskResultFailed

from utils.helpers                   import get_current_utc_timestamp
from utils.testing_helpers           import generate_ecc_key_pair

from api_testing_common              import api_request, parse_command_line, create_task_to_compute, get_protocol_constants, \
    print_protocol_constants
from api_testing_common              import timestamp_to_isoformat

from freezegun                       import freeze_time

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "concent_api.settings")

DEADLINE_OFFSET        = 5
CONCENT_MESSAGING_TIME = 30
FORCE_ACCEPTANCE_TIME  = 30

WAIT_TIME_1            = DEADLINE_OFFSET + FORCE_ACCEPTANCE_TIME

(PROVIDER_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY)  = generate_ecc_key_pair()
(REQUESTOR_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY) = generate_ecc_key_pair()


def upload_new_file_on_cluster(task_id = '0', part_id = '0', current_time = 0):

    file_content    = task_id
    file_size       = len(file_content)
    file_check_sum  = 'sha1:' + hashlib.sha1(file_content.encode()).hexdigest()
    file_path       = '{}/{}/result'.format(task_id, part_id)

    file_transfer_token = message.FileTransferToken()
    file_transfer_token.token_expiration_deadline       = int(datetime.datetime.now().timestamp()) + 3600
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
            'Authorization':                authorized_golem_transfer_token,
            'Concent-Client-Public-Key':    b64encode(CONCENT_PUBLIC_KEY).decode(),
            'Concent-upload-path':          '{}/{}/result'.format(task_id, part_id),
            'Content-Type':                 'application/x-www-form-urlencoded'
    }

    response = requests.post("{}".format(STORAGE_CLUSTER_ADDRESS + 'upload/'), headers = headers, data = file_content)
    return (response.status_code, file_size, file_check_sum)


def get_force_get_task_result(task_id, current_time, size, package_hash, task_deadline_offset=60):
    task_to_compute      = create_task_to_compute(current_time, task_id, task_deadline_offset)

    report_computed_task = message.ReportComputedTask(
        task_to_compute = task_to_compute,
        size            = size,
        package_hash    = package_hash,
    )

    with freeze_time(timestamp_to_isoformat(current_time)):
        force_get_task_result = message.concents.ForceGetTaskResult(
            report_computed_task = report_computed_task,
        )

    return force_get_task_result


class count_fails(object):
    instances = []

    def __init__(self, fun):
        self._fun     = fun
        self._name    = fun.__name__
        self._failed  = False
        count_fails.instances.append(self)

    def __call__(self, *args, **kwargs):
                try:
                    print("Running TC: " + self._name)
                    return self._fun(*args, **kwargs)
                except AssertionError as e:
                    print("{}: FAILED".format(self._name))
                    print(e)
                    self._failed = True

    @classmethod
    def get_fails(cls):
        return cls.instances.count(True)


@count_fails
def case_1_test_for_existing_file(cluster_url, current_time, task_id):
    (response_status_code, file_size, file_check_sum) = upload_new_file_on_cluster(
            task_id      = task_id,
            part_id      = '0',
            current_time = current_time,
    )
    assert response_status_code == 200, 'File has not been stored on cluster'
    print('\nCreated file with task_id {}. Checksum of this file is {}, and size of this file is {}.\n'.format(task_id,
                                                                                                               file_check_sum,
                                                                                                               file_size))
    # Case 1 - test for existing file
    api_request(
        cluster_url,
        'send',
        REQUESTOR_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        get_force_get_task_result(
            task_id,
            current_time,
            size=file_size,
            package_hash=file_check_sum),

        headers={
            'Content-Type': 'application/octet-stream',
            'concent-client-public-key': b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            'concent-other-party-public-key': b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
        },
        expected_status  = 200,
        expected_message = AckForceGetTaskResult
    )
    print(f"Waiting {WAIT_TIME_1} seconds...")
    time.sleep(WAIT_TIME_1)  # TaskToCompute.deadline + FORCE_ACCEPTANCE_TIME < current time <= TaskToCompute.deadline + FORCE_ACCEPTANCE_TIME + CONCENT_MESSAGING_TIME
    api_request(
        cluster_url,
        'receive',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        headers = {
            'Content-Type': 'application/octet-stream',
            'concent-client-public-key': b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
        },
        expected_status  = 200,
        expected_message = ForceGetTaskResultUpload
    )
    print(f"Waiting {CONCENT_MESSAGING_TIME} seconds...")
    time.sleep(CONCENT_MESSAGING_TIME)  # TaskToCompute.deadline + FORCE_ACCEPTANCE_TIME + CONCENT_MESSAGING_TIME < current time <= TaskToCompute.deadline + FORCE_ACCEPTANCE_TIME + 2 * CONCENT_MESSAGING_TIME.
    api_request(
        cluster_url,
        'receive',
        REQUESTOR_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        headers = {
            'Content-Type': 'application/octet-stream',
            'concent-client-public-key': b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
        },
        expected_status  = 200,
        expected_message = ForceGetTaskResultUpload
    )


@count_fails
def case_4a_concent_reports_a_failure_to_get_task_results_if_the_provider_does_not_submit_anything(cluster_url,
                                                                                                   current_time,
                                                                                                   task_id):
    """
    Case 4A:
    Requestor -> Concent:    ForceGetTaskResult
    Concent   -> Requestor:  ForceGetTaskResultAck
    Concent   -> Provider:   ForceGetTaskResult + FileTransferToken
    Concent   -> Requestor:  ForceGetTaskResultFailed (provider does not submit anything)
    """
    api_request(    # Requestor -> Concent:    ForceGetTaskResult
        cluster_url,
        'send',
        REQUESTOR_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        get_force_get_task_result(
            task_id + '4A',
            current_time,
            size=1024,
            package_hash='098f6bcd4621d373cade4e832627b4f6',
        task_deadline_offset = DEADLINE_OFFSET),
        headers={
            'Content-Type': 'application/octet-stream',
            'concent-client-public-key': b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            'concent-other-party-public-key': b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
        },
        expected_status  = 200,
        expected_message = AckForceGetTaskResult
    )
    print(f"Waiting {WAIT_TIME_1} seconds...")
    time.sleep(WAIT_TIME_1)  # TaskToCompute.deadline + FORCE_ACCEPTANCE_TIME < current time <= TaskToCompute.deadline + FORCE_ACCEPTANCE_TIME + CONCENT_MESSAGING_TIME
    api_request(    # Concent   -> Provider:   ForceGetTaskResult + FileTransferToken
        cluster_url,
        'receive',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        headers = {
            'Content-Type':                 'application/octet-stream',
            'concent-client-public-key':    b64encode(PROVIDER_PUBLIC_KEY).decode('ascii')
        },
        expected_status  = 200,
        expected_message = ForceGetTaskResultUpload
    )
    print(f"Waiting {CONCENT_MESSAGING_TIME} seconds...")
    time.sleep(CONCENT_MESSAGING_TIME)  # TaskToCompute.deadline + FORCE_ACCEPTANCE_TIME + CONCENT_MESSAGING_TIME < current time <= TaskToCompute.deadline + FORCE_ACCEPTANCE_TIME + 2 * CONCENT_MESSAGING_TIME.
    api_request(  # Concent   -> Requestor:  ForceGetTaskResultFailed (provider does not submit anything)
        cluster_url,
        'receive',
        REQUESTOR_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        headers = {
            'Content-Type':                 'application/octet-stream',
            'concent-client-public-key':    b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii')
        },
        expected_status  = 200,
        expected_message = ForceGetTaskResultFailed
    )


def main():
    global CONCENT_MESSAGING_TIME
    global FORCE_ACCEPTANCE_TIME
    global WAIT_TIME_1

    cluster_url     = parse_command_line(sys.argv)
    current_time    = get_current_utc_timestamp()
    task_id         = str(random.randrange(1, 100000))
    number_of_tests = 2

    cluster_consts         = get_protocol_constants(cluster_url)
    print_protocol_constants(cluster_consts)
    CONCENT_MESSAGING_TIME = cluster_consts.concent_messaging_time
    FORCE_ACCEPTANCE_TIME  = cluster_consts.force_acceptance_time
    WAIT_TIME_1            = DEADLINE_OFFSET + FORCE_ACCEPTANCE_TIME  # recalculated as it could change due to cluster_consts

    case_1_test_for_existing_file(cluster_url, current_time, task_id)

    print("-" * 80)

    case_4a_concent_reports_a_failure_to_get_task_results_if_the_provider_does_not_submit_anything(cluster_url,
                                                                                                   current_time,
                                                                                                   task_id)

    total_fails = count_fails.get_fails()
    if total_fails > 0:
        print(f'Total failed tests : {total_fails} out of {number_of_tests}')
    print("END")


if __name__ == '__main__':
    try:
        from concent_api.settings import CONCENT_PUBLIC_KEY, CONCENT_PRIVATE_KEY, STORAGE_CLUSTER_ADDRESS
        main()
    except requests.exceptions.ConnectionError as exception:
        print("\nERROR: Failed connect to the server.\n", file = sys.stderr)
        sys.exit(str(exception))
