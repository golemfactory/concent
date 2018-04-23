#!/usr/bin/env python3

import os
import sys
import random
import time
from freezegun              import freeze_time

from golem_messages         import message

from utils.helpers import get_current_utc_timestamp
from utils.helpers import sign_message
from utils.testing_helpers import generate_ecc_key_pair

from api_testing_common import api_request
from api_testing_common import get_task_id_and_subtask_id
from api_testing_common import create_client_auth_message
from api_testing_common import parse_command_line
from api_testing_common import timestamp_to_isoformat

from protocol_constants import get_protocol_constants

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
    provider_public_key             = None,
    requestor_public_key            = None,
    requestor_ethereum_public_key   = None,
    price                           = 1000
):
    with freeze_time(timestamp):
        task_to_compute = message.tasks.TaskToCompute(
            provider_public_key=provider_public_key if provider_public_key is not None else PROVIDER_PUBLIC_KEY,
            requestor_public_key=requestor_public_key if requestor_public_key is not None else REQUESTOR_PUBLIC_KEY,
            compute_task_def = compute_task_def,
            requestor_ethereum_public_key = requestor_ethereum_public_key,
            price=price,
        )
        sign_message(task_to_compute, REQUESTOR_PRIVATE_KEY)
        return task_to_compute


def compute_task_def(
    subtask_id  = None,
    task_id     = None,
    deadline    = None,
):
    compute_task_def = message.tasks.ComputeTaskDef()
    compute_task_def['subtask_id']  = subtask_id
    compute_task_def['task_id']     = task_id
    compute_task_def['deadline']    = deadline

    return compute_task_def


def main():
    cluster_url     = parse_command_line(sys.argv)
    test_id         = str(random.randrange(1, 100000))
    cluster_consts = get_protocol_constants(cluster_url)

    test_case_2_a_force_payment_with_subtask_result_accepted_where_ethereum_accounts_are_different(
        cluster_consts, cluster_url, test_id
    )

    test_case_2b_send_force_payment_beyond_payment_time(cluster_consts, cluster_url, test_id)

    test_case_2c_send_force_payment_with_no_value_to_be_paid(cluster_consts, cluster_url, test_id)

    test_case_2d_send_correct_force_payment(cluster_consts, cluster_url, test_id)


def test_case_2d_send_correct_force_payment(cluster_consts, cluster_url, test_id):
    # Test CASE 2D - Send correct ForcePayment
    current_time = get_current_utc_timestamp()
    (task_id, subtask_id) = get_task_id_and_subtask_id(test_id, '2D')
    correct_force_payment = force_payment(
        timestamp=timestamp_to_isoformat(current_time),
        subtask_results_accepted_list=[
            subtask_results_accepted(
                timestamp=timestamp_to_isoformat(current_time),
                payment_ts=current_time - cluster_consts.payment_due_time - 10,
                task_to_compute=task_to_compute(
                    timestamp=timestamp_to_isoformat(current_time),
                    requestor_ethereum_public_key="x" * 128,
                    compute_task_def=compute_task_def(
                        deadline=current_time,
                        task_id=task_id + 'a',
                        subtask_id=task_id + 'A'
                    )
                )
            ),
            subtask_results_accepted(
                timestamp=timestamp_to_isoformat(current_time),
                payment_ts=current_time - cluster_consts.payment_due_time - 10,
                task_to_compute=task_to_compute(
                    timestamp=timestamp_to_isoformat(current_time),
                    requestor_ethereum_public_key="x" * 128,
                    compute_task_def=compute_task_def(
                        deadline=current_time,
                        task_id=task_id + 'b',
                        subtask_id=task_id + 'B'
                    )
                )
            )
        ]
    )
    correct_force_payment.sig = None
    api_request(
        cluster_url,
        'send',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        correct_force_payment,

        headers={
            'Content-Type': 'application/octet-stream',
        },
        expected_status=200,
        expected_message_type=message.concents.ForcePaymentCommitted.TYPE,
        expected_content_type='application/octet-stream',
    )
    time.sleep(5)
    api_request(
        cluster_url,
        'receive-out-of-band',
        REQUESTOR_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        create_client_auth_message(REQUESTOR_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY, CONCENT_PUBLIC_KEY),
        headers={
            'Content-Type': 'application/octet-stream',
        },
        expected_status=200,
        expected_message_type=message.concents.ForcePaymentCommitted.TYPE,
        expected_content_type='application/octet-stream',
    )


def test_case_2c_send_force_payment_with_no_value_to_be_paid(cluster_consts, cluster_url, test_id):
    #  Test CASE 2C - Send ForcePayment with no value to be paid
    current_time = get_current_utc_timestamp()
    (task_id, subtask_id) = get_task_id_and_subtask_id(test_id, '2C')
    api_request(
        cluster_url,
        'send',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        force_payment(
            timestamp=timestamp_to_isoformat(current_time),
            subtask_results_accepted_list=[
                subtask_results_accepted(
                    timestamp=timestamp_to_isoformat(current_time),
                    payment_ts=current_time,
                    task_to_compute=task_to_compute(
                        timestamp=timestamp_to_isoformat(current_time),
                        requestor_ethereum_public_key="x" * 128,
                        price=0,
                        compute_task_def=compute_task_def(
                            deadline=current_time,
                            task_id=task_id + 'a',
                            subtask_id=task_id + 'A'
                        )
                    )
                ),
                subtask_results_accepted(
                    timestamp=timestamp_to_isoformat(current_time),
                    payment_ts=current_time,
                    task_to_compute=task_to_compute(
                        timestamp=timestamp_to_isoformat(current_time),
                        requestor_ethereum_public_key="x" * 128,
                        price=0,
                        compute_task_def=compute_task_def(
                            deadline=current_time,
                            task_id=task_id + 'b',
                            subtask_id=task_id + 'B'
                        )
                    )
                )
            ]
        ),

        headers={
            'Content-Type': 'application/octet-stream',
        },
        expected_status=200,
        expected_message_type=message.concents.ForcePaymentRejected.TYPE,
        expected_content_type='application/octet-stream',
    )


def test_case_2b_send_force_payment_beyond_payment_time(cluster_consts, cluster_url, test_id):
    #  Test CASE 2B - Send ForcePayment beyond payment time
    current_time = get_current_utc_timestamp()
    (task_id, subtask_id) = get_task_id_and_subtask_id(test_id, '2B')
    api_request(
        cluster_url,
        'send',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        force_payment(
            timestamp=timestamp_to_isoformat(current_time),
            subtask_results_accepted_list=[
                subtask_results_accepted(
                    timestamp=timestamp_to_isoformat(current_time),
                    payment_ts=current_time,
                    task_to_compute=task_to_compute(
                        timestamp=timestamp_to_isoformat(current_time),
                        requestor_ethereum_public_key="x" * 128,
                        compute_task_def=compute_task_def(
                            deadline=current_time,
                            task_id=task_id + 'a',
                            subtask_id=task_id + 'A'
                        )
                    )
                ),
                subtask_results_accepted(
                    timestamp=timestamp_to_isoformat(current_time),
                    payment_ts=current_time,
                    task_to_compute=task_to_compute(
                        timestamp=timestamp_to_isoformat(current_time),
                        requestor_ethereum_public_key="x" * 128,
                        compute_task_def=compute_task_def(
                            deadline=current_time,
                            task_id=task_id + 'b',
                            subtask_id=task_id + 'B'
                        )
                    )
                )
            ]
        ),

        headers={
            'Content-Type': 'application/octet-stream',
        },
        expected_status=200,
        expected_message_type=message.concents.ForcePaymentRejected.TYPE,
        expected_content_type='application/octet-stream',
    )


def test_case_2_a_force_payment_with_subtask_result_accepted_where_ethereum_accounts_are_different(
    cluster_consts,
    cluster_url,
    test_id
):
    # Test CASE 2A - Send ForcePayment with SubtaskResultsAccepted where ethereum accounts are different
    current_time = get_current_utc_timestamp()
    (task_id, subtask_id) = get_task_id_and_subtask_id(test_id, '2A')
    api_request(
        cluster_url,
        'send',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        force_payment(
            timestamp=timestamp_to_isoformat(current_time),
            subtask_results_accepted_list=[
                subtask_results_accepted(
                    timestamp=timestamp_to_isoformat(current_time),
                    payment_ts=current_time - cluster_consts.payment_due_time - 10,
                    task_to_compute=task_to_compute(
                        timestamp=timestamp_to_isoformat(current_time),
                        requestor_ethereum_public_key="x" * 128,
                        compute_task_def=compute_task_def(
                            deadline=current_time,
                            task_id=task_id + 'a',
                            subtask_id=task_id + 'A'
                        )
                    )
                ),
                subtask_results_accepted(
                    timestamp=timestamp_to_isoformat(current_time),
                    payment_ts=current_time - cluster_consts.payment_due_time - 10,
                    task_to_compute=task_to_compute(
                        timestamp=timestamp_to_isoformat(current_time),
                        requestor_ethereum_public_key="y" * 128,
                        compute_task_def=compute_task_def(
                            deadline=current_time,
                            task_id=task_id + 'b',
                            subtask_id=task_id + 'B'
                        )
                    )
                )
            ]
        ),

        headers={
            'Content-Type': 'application/octet-stream',
        },
        expected_status=200,
        expected_message_type=message.concents.ServiceRefused.TYPE,
        expected_content_type='application/octet-stream',
    )


if __name__ == '__main__':
    try:
        from concent_api.settings import CONCENT_PUBLIC_KEY
        main()
    except requests.exceptions.ConnectionError as exception:
        print("\nERROR: Failed connect to the server.\n", file = sys.stderr)
        sys.exit(str(exception))
