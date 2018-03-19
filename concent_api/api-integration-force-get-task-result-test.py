#!/usr/bin/env python3
import argparse
import os
import sys
import datetime
import hashlib
import random
import requests
import time

from base64                             import b64encode
from golem_messages                     import message
from golem_messages                     import shortcuts
from golem_messages.message.concents    import AckForceGetTaskResult
from golem_messages.message.concents    import ForceGetTaskResultFailed
from golem_messages.message.concents    import ForceGetTaskResultUpload

from utils.helpers                      import get_current_utc_timestamp
from utils.testing_helpers              import generate_ecc_key_pair

from api_testing_common                 import api_request
from api_testing_common                 import assert_condition
from api_testing_common                 import count_fails
from api_testing_common                 import DEFAULT_DEADLINE_OFFSET
from api_testing_common                 import create_task_to_compute
from api_testing_common                 import get_protocol_constants
from api_testing_common                 import print_protocol_constants

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "concent_api.settings")

DEFAULT_TASK_DURATION  = 5
CONCENT_MESSAGING_TIME = 30
FORCE_ACCEPTANCE_TIME  = 30
TOKEN_EXPIRATION_TIME  = 3600

WAIT_TIME_FOR_CONCENT  = DEFAULT_TASK_DURATION + FORCE_ACCEPTANCE_TIME

(PROVIDER_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY)  = generate_ecc_key_pair()
(REQUESTOR_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY) = generate_ecc_key_pair()


def upload_new_file_on_cluster(task_id = '0', part_id = '0', time_offset = TOKEN_EXPIRATION_TIME):
    (file_check_sum, file_content, file_size, headers)  = prepare_file_for_transfer(part_id, task_id, time_offset)
    response                                            = upload_file(file_content, headers)
    return (response.status_code, file_size, file_check_sum)


def prepare_file_for_transfer(part_id, task_id, time_offset):
    file_content                                        = task_id
    file_size = len(file_content)
    file_check_sum                                      = 'sha1:' + hashlib.sha1(file_content.encode()).hexdigest()
    file_path                                           = '{}/{}/result'.format(task_id, part_id)
    file_transfer_token = message.FileTransferToken()
    file_transfer_token.subtask_id                      = "sub_" + task_id
    file_transfer_token.token_expiration_deadline       = int(datetime.datetime.now().timestamp()) + time_offset
    file_transfer_token.storage_cluster_address         = STORAGE_CLUSTER_ADDRESS
    file_transfer_token.authorized_client_public_key    = CONCENT_PUBLIC_KEY
    file_transfer_token.operation                       = 'upload'
    file_transfer_token.files                           = [message.FileTransferToken.FileInfo()]
    file_transfer_token.files[0]['path']                = file_path
    file_transfer_token.files[0]['checksum']            = file_check_sum  # prepare_hash(file_check_sum, wrong_hash)
    file_transfer_token.files[0]['size']                = file_size
    upload_token                                        = shortcuts.dump(file_transfer_token,
                                                                         CONCENT_PRIVATE_KEY,
                                                                         CONCENT_PUBLIC_KEY
                                                                         )
    encrypted_token                                     = b64encode(upload_token).decode()
    authorized_golem_transfer_token                     = 'Golem ' + encrypted_token
    headers = {
        'Authorization'            : authorized_golem_transfer_token,
        'Concent-Client-Public-Key': b64encode(CONCENT_PUBLIC_KEY).decode(),
        'Concent-upload-path'      : '{}/{}/result'.format(task_id, part_id),
        'Content-Type'             : 'application/x-www-form-urlencoded'
    }
    return (file_check_sum, file_content, file_size, headers)


def upload_file(file_content, headers):
    response    = requests.post(
                    "{}".format(
                        STORAGE_CLUSTER_ADDRESS + 'upload/'
                    ),
                    headers = headers,
                    data    = file_content,
                    verify  = False,
                  )
    return response


def get_force_get_task_result(task_id, current_time, size, package_hash, task_deadline_offset = DEFAULT_DEADLINE_OFFSET):
    task_to_compute      = create_task_to_compute(current_time, task_id, task_deadline_offset)

    report_computed_task = message.ReportComputedTask(
        subtask_id          = "sub_" + task_id,
        task_to_compute     = task_to_compute,
        size                = size,
        package_hash        = package_hash,
    )

    force_get_task_result = message.concents.ForceGetTaskResult(
        report_computed_task = report_computed_task,
    )

    return force_get_task_result


@count_fails
def case_4d_concent_notifies_the_provider_that_task_results_are_ready(cluster_url, current_time, task_id):
    file_check_sum, file_content, file_size, headers = prepare_file_for_transfer('0', task_id, TOKEN_EXPIRATION_TIME)

    response = upload_file(file_content, headers)

    assert_condition(response.status_code, 200, 'File has not been stored on cluster')
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
            'Content-Type'                  : 'application/octet-stream',
            'concent-client-public-key'     : b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            'concent-other-party-public-key': b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
        },
        expected_status  = 200,
        expected_message = AckForceGetTaskResult
    )
    print(f"Waiting {WAIT_TIME_FOR_CONCENT} seconds...")
    time.sleep(WAIT_TIME_FOR_CONCENT)  # TaskToCompute.deadline + FORCE_ACCEPTANCE_TIME < current time <= TaskToCompute.deadline + FORCE_ACCEPTANCE_TIME + CONCENT_MESSAGING_TIME
    api_request(
        cluster_url,
        'receive',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        headers = {
            'Content-Type'             : 'application/octet-stream',
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
            'Content-Type'             : 'application/octet-stream',
            'concent-client-public-key': b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
        },
        expected_status  = 200,
        expected_message = ForceGetTaskResultUpload
    )


@count_fails
def case_4c_concent_reports_a_failure_to_get_task_results_if_file_has_bad_hash(cluster_url, current_time, task_id):
    """
    Requestor -> Concent:    ForceGetTaskResult
    Concent   -> Requestor:  ForceGetTaskResultAck
    Concent   -> Provider:   ForceGetTaskResult + FileTransferToken
    Provider  -> Concent:    Upload is done with bad file
    Concent   -> Requestor:  ForceGetTaskResultFailed (Any of the files had a hash or size that did not match ReportComputedTask)
    """
    file_check_sum, file_content, file_size, headers = prepare_file_for_transfer('0', task_id, TOKEN_EXPIRATION_TIME)

    api_request(
        cluster_url,
        'send',
        REQUESTOR_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        get_force_get_task_result(task_id, current_time, size = file_size, checksum = file_check_sum),
        headers = {
            'Content-Type'                  : 'application/octet-stream',
            'concent-client-public-key'     : b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            'concent-other-party-public-key': b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
        },
        expected_status  = 200,
        expected_message = AckForceGetTaskResult
    )
    print(f"Waiting {WAIT_TIME_FOR_CONCENT} seconds...")
    time.sleep(WAIT_TIME_FOR_CONCENT)  # TaskToCompute.deadline + FORCE_ACCEPTANCE_TIME < current time <= TaskToCompute.deadline + FORCE_ACCEPTANCE_TIME + CONCENT_MESSAGING_TIME
    api_request(
        cluster_url,
        'receive',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        headers = {
            'Content-Type'             : 'application/octet-stream',
            'concent-client-public-key': b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
        },
        expected_status  = 200,
        expected_message = ForceGetTaskResultUpload
    )
    response = upload_file(file_content + "random_data", headers)
    print(f"UPLOAD STATUS = {response.status_code}")

    assert_condition(response.status_code, 400, "File has been approved but it shouldn't have")

    print(f"Waiting {CONCENT_MESSAGING_TIME} seconds...")
    time.sleep(CONCENT_MESSAGING_TIME)  # TaskToCompute.deadline + FORCE_ACCEPTANCE_TIME + CONCENT_MESSAGING_TIME < current time <= TaskToCompute.deadline + FORCE_ACCEPTANCE_TIME + 2 * CONCENT_MESSAGING_TIME.
    api_request(
        cluster_url,
        'receive',
        REQUESTOR_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        headers = {
            'Content-Type'             : 'application/octet-stream',
            'concent-client-public-key': b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
        },
        expected_status  = 200,
        expected_message = ForceGetTaskResultFailed
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
        get_force_get_task_result(task_id + '4A',
          current_time,
          size                  = 1024,
          package_hash          = '098f6bcd4621d373cade4e832627b4f6',
          task_deadline_offset  = DEFAULT_TASK_DURATION
        ),
        headers = {
            'Content-Type'                  : 'application/octet-stream',
            'concent-client-public-key'     : b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            'concent-other-party-public-key': b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
        },
        expected_status  = 200,
        expected_message = AckForceGetTaskResult
    )
    print(f"Waiting {WAIT_TIME_FOR_CONCENT} seconds...")
    time.sleep(WAIT_TIME_FOR_CONCENT)  # TaskToCompute.deadline + FORCE_ACCEPTANCE_TIME < current time <= TaskToCompute.deadline + FORCE_ACCEPTANCE_TIME + CONCENT_MESSAGING_TIME
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


def parse_arguments():
    parser  = argparse.ArgumentParser()
    parser.add_argument("cluster_url")
    parser.add_argument("tc_patterns", nargs='*')
    args    = parser.parse_args()
    return (args.cluster_url, args.tc_patterns)


def get_tests_list(patterns, all_objects):
    def _is_a_test(x):
        return "case_" in x

    tests = list(filter(lambda x: _is_a_test(x), all_objects))
    if len(patterns) > 0:
        safe_patterns   = [pattern for pattern in patterns if _is_a_test(pattern)]
        tests           = [test for pattern in safe_patterns for test in tests if pattern in test]
    return sorted(tests)


def execute_tests(tests_to_execute, **kwargs):
    objects = globals()
    tests = [objects[name] for name in tests_to_execute]
    for test in tests:
        task_id = kwargs['task_id'] + test.__name__
        kw = {k: v for k, v in kwargs.items() if k != 'task_id'}
        test(task_id=task_id, **kw)
        print("-" * 80)


def main():
    global CONCENT_MESSAGING_TIME
    global FORCE_ACCEPTANCE_TIME
    global TOKEN_EXPIRATION_TIME
    global WAIT_TIME_FOR_CONCENT

    cluster_url, patterns   = parse_arguments()
    current_time            = get_current_utc_timestamp()
    task_id                 = str(random.randrange(1, 100000))
    tests_to_execute        = get_tests_list(patterns, list(globals().keys()))
    print("Tests to be executed: \n * " + "\n * ".join(tests_to_execute))
    print()

    cluster_consts         = get_protocol_constants(cluster_url)
    print_protocol_constants(cluster_consts)
    # GLOBALS should be recalculated as it could change due to cluster_consts
    CONCENT_MESSAGING_TIME = cluster_consts.concent_messaging_time
    FORCE_ACCEPTANCE_TIME  = cluster_consts.force_acceptance_time
    TOKEN_EXPIRATION_TIME  = cluster_consts.token_expiration_time
    WAIT_TIME_FOR_CONCENT  = DEFAULT_TASK_DURATION + FORCE_ACCEPTANCE_TIME

    execute_tests(tests_to_execute, cluster_url=cluster_url, current_time=current_time, task_id=task_id)

    if count_fails.get_fails() > 0:
        count_fails.print_fails()
    print("END")


if __name__ == '__main__':
    try:
        from concent_api.settings import CONCENT_PUBLIC_KEY, CONCENT_PRIVATE_KEY, STORAGE_CLUSTER_ADDRESS
        main()
    except requests.exceptions.ConnectionError as exception:
        print("\nERROR: Failed connect to the server.\n", file = sys.stderr)
        sys.exit(str(exception))
