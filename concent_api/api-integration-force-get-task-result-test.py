#!/usr/bin/env python3

import os
import sys
import datetime
import hashlib
import random
import requests
import time
from base64                 import b64encode

from golem_messages         import message
from golem_messages         import shortcuts

from utils.helpers          import get_current_utc_timestamp
from utils.testing_helpers  import generate_ecc_key_pair

from api_testing_common     import api_request, parse_command_line, create_task_to_compute
from api_testing_common     import timestamp_to_isoformat

from freezegun              import freeze_time

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "concent_api.settings")

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


def get_force_get_task_result(task_id, current_time, size, package_hash):
    task_to_compute = create_task_to_compute(current_time, task_id)

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
        self.fun = fun
        self.failed = False
        count_fails.instances.append(self)

    def __call__(self, *args, **kwargs):
            def inner(*args, **kwargs):
                try:
                    self.fun(*args, **kwargs)
                except AssertionError as e:
                    print("{}: FAILED".format(self.fun.__name__))
                    print(e)
                    self.failed = True
            return inner(*args, **kwargs)

    @classmethod
    def get_failes(cls):
        return cls.instances.count(True)


def main():
    cluster_url     = parse_command_line(sys.argv)
    current_time    = get_current_utc_timestamp()
    task_id         = str(random.randrange(1, 100000))
    number_of_tests = 2

    case_1_test_for_existing_file(cluster_url, current_time, task_id)

    case_2_test_for_non_existing_file(cluster_url, current_time, task_id)

    total_fails = count_fails.get_failes()
    if total_fails > 0:
        print(f'Total failed tests : {total_fails} out of {number_of_tests}')
    print("END")


@count_fails
def case_1_test_for_existing_file(cluster_url, current_time, task_id):
    (response_status_code, file_size, file_check_sum) = upload_new_file_on_cluster(
        task_id=task_id,
        part_id='0',
        current_time=current_time,
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
            size         = file_size,
            package_hash = file_check_sum
        ),
        headers = {
            'Content-Type':                     'application/octet-stream',
            'concent-client-public-key':        b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            'concent-other-party-public-key':   b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
        }
    )
    time.sleep(10)
    api_request(
        cluster_url,
        'receive',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        headers = {
            'Content-Type': 'application/octet-stream',
            'concent-client-public-key': b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
        }
    )
    time.sleep(10)
    api_request(
        cluster_url,
        'receive',
        REQUESTOR_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        headers = {
            'Content-Type': 'application/octet-stream',
            'concent-client-public-key': b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
        }
    )


@count_fails
def case_2_test_for_non_existing_file(cluster_url, current_time, task_id):
    # Case 2 - test for non existing file
    api_request(
        cluster_url,
        'send',
        REQUESTOR_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        get_force_get_task_result(
            task_id + 'non_existing_file',
            current_time,
            size    = 1024,
            package_hash = '098f6bcd4621d373cade4e832627b4f6'
        ),
        headers = {
            'Content-Type':                     'application/octet-stream',
            'concent-client-public-key':        b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            'concent-other-party-public-key':   b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
        }
    )
    time.sleep(10)
    api_request(
        cluster_url,
        'receive',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        headers = {
            'Content-Type':                 'application/octet-stream',
            'concent-client-public-key':    b64encode(PROVIDER_PUBLIC_KEY).decode('ascii')
        }
    )
    time.sleep(10)
    api_request(
        cluster_url,
        'receive',
        REQUESTOR_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        headers = {
            'Content-Type':                 'application/octet-stream',
            'concent-client-public-key':    b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii')
        }
    )


if __name__ == '__main__':
    try:
        from concent_api.settings import CONCENT_PUBLIC_KEY, CONCENT_PRIVATE_KEY, STORAGE_CLUSTER_ADDRESS
        main()
    except requests.exceptions.ConnectionError as exception:
        print("\nERROR: Failed connect to the server.\n", file = sys.stderr)
        sys.exit(str(exception))
