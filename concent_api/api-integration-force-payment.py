#!/usr/bin/env python3

import os
import sys
import random
import time
from base64                 import b64encode
from freezegun              import freeze_time

from golem_messages         import message

from utils.helpers          import get_current_utc_timestamp
from utils.testing_helpers  import generate_ecc_key_pair

from api_testing_common import api_request, parse_command_line
from api_testing_common    import timestamp_to_isoformat

import requests

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "concent_api.settings")

(PROVIDER_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY)  = generate_ecc_key_pair()
(REQUESTOR_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY) = generate_ecc_key_pair()
(DIFFERENT_PROVIDER_PRIVATE_KEY, DIFFERENT_PROVIDER_PUBLIC_KEY)     = generate_ecc_key_pair()
(DIFFERENT_REQUESTOR_PRIVATE_KEY, DIFFERENT_REQUESTOR_PUBLIC_KEY)   = generate_ecc_key_pair()


def force_payment(timestamp = None, subtask_results_accepted_list = None):
    with freeze_time(timestamp):
        return message.concents.ForcePayment(
            subtask_results_accepted_list = subtask_results_accepted_list
        )


def subtask_results_accepted(timestamp = None, payment_ts = None, task_to_compute = None):
    with freeze_time(timestamp):
        return message.tasks.SubtaskResultsAccepted(
            payment_ts      = payment_ts,
            task_to_compute = task_to_compute
        )


def task_to_compute(
    timestamp                       = None,
    compute_task_def                = None,
    requestor_public_key            = None,
    requestor_ethereum_public_key   = None
):
    with freeze_time(timestamp):
        return message.tasks.TaskToCompute(
            compute_task_def = compute_task_def,
            requestor_public_key = requestor_public_key,
            requestor_ethereum_public_key = requestor_ethereum_public_key
        )


def compute_task_def(
    task_id     = None,
    deadline    = None,
):
    compute_task_def = message.tasks.ComputeTaskDef()
    compute_task_def['task_id']     = task_id
    compute_task_def['deadline']    = deadline

    return compute_task_def


def main():
    cluster_url     = parse_command_line(sys.argv)
    task_id         = str(random.randrange(1, 100000))
    current_time    = get_current_utc_timestamp()

    correct_force_payment = force_payment(
        timestamp = timestamp_to_isoformat(current_time),
        subtask_results_accepted_list = [
            subtask_results_accepted(
                timestamp       = timestamp_to_isoformat(current_time),
                payment_ts      = current_time - PAYMENT_DUE_TIME - PAYMENT_GRACE_PERIOD - 1,
                task_to_compute = task_to_compute(
                    timestamp                       = timestamp_to_isoformat(current_time),
                    requestor_public_key            = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
                    requestor_ethereum_public_key   = "0x" + b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
                    compute_task_def                = compute_task_def(
                        deadline = current_time,
                        task_id  = task_id + 'a'
                    )
                )
            ),
            subtask_results_accepted(
                timestamp       = timestamp_to_isoformat(current_time),
                payment_ts      = current_time - PAYMENT_DUE_TIME - PAYMENT_GRACE_PERIOD - 1,
                task_to_compute = task_to_compute(
                    timestamp                       = timestamp_to_isoformat(current_time),
                    requestor_public_key            = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
                    requestor_ethereum_public_key   = "0x" + b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
                    compute_task_def                = compute_task_def(
                        deadline = current_time,
                        task_id  = task_id + 'b'
                    )
                )
            )
        ]
    )

    # Test CASE 2A - Send ForcePayment with SubtaskResultsAccepted where ethereum accounts are different
    api_request(
        cluster_url,
        'send',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        force_payment(
            timestamp = timestamp_to_isoformat(current_time),
            subtask_results_accepted_list = [
                subtask_results_accepted(
                    timestamp       = timestamp_to_isoformat(current_time),
                    payment_ts      = current_time - PAYMENT_DUE_TIME - PAYMENT_GRACE_PERIOD - 1,
                    task_to_compute = task_to_compute(
                        timestamp                       = timestamp_to_isoformat(current_time),
                        requestor_public_key            = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
                        requestor_ethereum_public_key   = "0x" + b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
                        compute_task_def                = compute_task_def(
                            deadline = current_time,
                            task_id  = task_id + 'a'
                        )
                    )
                ),
                subtask_results_accepted(
                    timestamp       = timestamp_to_isoformat(current_time),
                    payment_ts      = current_time - PAYMENT_DUE_TIME - PAYMENT_GRACE_PERIOD - 1,
                    task_to_compute = task_to_compute(
                        timestamp                       = timestamp_to_isoformat(current_time),
                        requestor_public_key            = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
                        requestor_ethereum_public_key   = "0x" + b64encode(DIFFERENT_REQUESTOR_PUBLIC_KEY).decode('ascii'),
                        compute_task_def                = compute_task_def(
                            deadline = current_time,
                            task_id  = task_id + 'b'
                        )
                    )
                )
            ]
        ),

        headers = {
            'Content-Type':                     'application/octet-stream',
            'concent-client-public-key':        b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            'concent-other-party-public-key':   b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            'temporary-list-of-transactions':   'True',
            'temporary-v':                      '1',
            'temporary-eth-block':              '1'
        }
    )

    #  Test CASE 2B - Send ForcePayment beyond payment time
    api_request(
        cluster_url,
        'send',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        correct_force_payment,

        headers = {
            'Content-Type':                     'application/octet-stream',
            'concent-client-public-key':        b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            'concent-other-party-public-key':   b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            'temporary-list-of-transactions':   '',
            'temporary-v':                      '-1',
            'temporary-eth-block':              '-1'
        }
    )

    #  Test CASE 2C - Send ForcePayment with no value to be paid
    api_request(
        cluster_url,
        'send',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        correct_force_payment,

        headers = {
            'Content-Type':                     'application/octet-stream',
            'concent-client-public-key':        b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            'concent-other-party-public-key':   b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            'temporary-list-of-transactions':   'True',
            'temporary-v':                      '-1',
            'temporary-eth-block':              '-1'
        }
    )

    # Test CASE 2D - Send correct ForcePayment
    api_request(
        cluster_url,
        'send',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        correct_force_payment,

        headers = {
            'Content-Type':                     'application/octet-stream',
            'concent-client-public-key':        b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            'concent-other-party-public-key':   b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            'temporary-list-of-transactions':   'True',
            'temporary-v':                      '1',
            'temporary-eth-block':              '1'
        }
    )

    time.sleep(5)

    api_request(
        cluster_url,
        'receive-out-of-band',
        REQUESTOR_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        headers = {
            'Content-Type': 'application/octet-stream',
            'concent-client-public-key': b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
        }
    )


if __name__ == '__main__':
    try:
        from concent_api.settings import CONCENT_PUBLIC_KEY
        from concent_api.settings import PAYMENT_DUE_TIME
        from concent_api.settings import PAYMENT_GRACE_PERIOD
        main()
    except requests.exceptions.ConnectionError as exception:
        print("\nERROR: Failed connect to the server.\n", file = sys.stderr)
        sys.exit(str(exception))
