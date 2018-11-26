#!/usr/bin/env python3

from typing import Optional
from typing import Union
import datetime
import os
import sys
import time

from freezegun import freeze_time

from golem_messages import message

from common.helpers import get_current_utc_timestamp
from common.helpers import parse_timestamp_to_utc_datetime
from common.helpers import sign_message
from common.testing_helpers import generate_priv_and_pub_eth_account_key

from api_testing_common import api_request
from api_testing_common import count_fails
from api_testing_common import create_client_auth_message
from api_testing_common import create_signed_task_to_compute
from api_testing_common import run_tests
from api_testing_common import PROVIDER_PRIVATE_KEY
from api_testing_common import REQUESTOR_PRIVATE_KEY
from api_testing_common import REQUESTOR_PUBLIC_KEY
from api_testing_common import timestamp_to_isoformat
from protocol_constants import ProtocolConstants

import requests

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "concent_api.settings")

"""
Average time for 2 blocks
Constans needed for test to get last 2 blocks
"""
AVERAGE_TIME_FOR_TWO_BLOCKS = 30

(DIFFERENT_REQUESTOR_ETHEREUM_PRIVATE_KEY, DIFFERENT_REQUESTOR_ETHEREUM_PUBLIC_KEY) = generate_priv_and_pub_eth_account_key()


def force_payment(
    timestamp: Optional[Union[datetime.datetime, str]]=None,
    subtask_results_accepted_list: Optional[list]=None
) -> message.concents.ForcePayment:
    with freeze_time(timestamp):
        return message.concents.ForcePayment(
            subtask_results_accepted_list = subtask_results_accepted_list
        )


def subtask_results_accepted(
    timestamp: Optional[Union[datetime.datetime, str]]=None,
    payment_ts: Optional[int]=None,
    task_to_compute: Optional[message.TaskToCompute]=None
) -> message.tasks.SubtaskResultsAccepted:
    with freeze_time(timestamp):
        signed_message: message.tasks.SubtaskResultsAccepted = sign_message(
            message.tasks.SubtaskResultsAccepted(
                payment_ts=payment_ts,
                task_to_compute=task_to_compute
            ),
            REQUESTOR_PRIVATE_KEY,
        )
        return signed_message


@count_fails
def test_case_2d_send_correct_force_payment(cluster_consts: ProtocolConstants, cluster_url: str) -> None:
    # Test CASE 2D - Send correct ForcePayment
    current_time = get_current_utc_timestamp()
    correct_force_payment = force_payment(
        subtask_results_accepted_list=[
            subtask_results_accepted(
                payment_ts=current_time - cluster_consts.payment_due_time - AVERAGE_TIME_FOR_TWO_BLOCKS,
                task_to_compute=create_signed_task_to_compute(
                    timestamp=parse_timestamp_to_utc_datetime(current_time),
                    deadline=current_time,
                    price=1000,
                )
            ),
            subtask_results_accepted(
                payment_ts=current_time - cluster_consts.payment_due_time - AVERAGE_TIME_FOR_TWO_BLOCKS,
                task_to_compute=create_signed_task_to_compute(
                    timestamp=parse_timestamp_to_utc_datetime(current_time),
                    deadline=current_time,
                    price=1000,
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
        expected_status=200,
        expected_message_type=message.concents.ForcePaymentCommitted,
        expected_content_type='application/octet-stream',
    )
    time.sleep(5)
    api_request(
        cluster_url,
        'receive',
        REQUESTOR_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        create_client_auth_message(REQUESTOR_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY, CONCENT_PUBLIC_KEY),
        expected_status=200,
        expected_message_type=message.concents.ForcePaymentCommitted,
        expected_content_type='application/octet-stream',
    )


@count_fails
def test_case_2c_send_force_payment_with_no_value_to_be_paid(cluster_consts: ProtocolConstants, cluster_url: str) -> None:
    #  Test CASE 2C - Send ForcePayment with no value to be paid
    current_time = get_current_utc_timestamp()
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
                    payment_ts=current_time - cluster_consts.payment_due_time - AVERAGE_TIME_FOR_TWO_BLOCKS,
                    task_to_compute=create_signed_task_to_compute(
                        timestamp=parse_timestamp_to_utc_datetime(current_time),
                        deadline=current_time,
                        price=0,
                    )
                ),
                subtask_results_accepted(
                    timestamp=timestamp_to_isoformat(current_time),
                    payment_ts=current_time - cluster_consts.payment_due_time - AVERAGE_TIME_FOR_TWO_BLOCKS,
                    task_to_compute=create_signed_task_to_compute(
                        timestamp=parse_timestamp_to_utc_datetime(current_time),
                        deadline=current_time,
                        price=0,
                    )
                )
            ]
        ),
        expected_status=400,
        expected_error_code='message.value_negative',
    )


@count_fails
def test_case_2b_send_force_payment_beyond_payment_time(cluster_consts: ProtocolConstants, cluster_url: str) -> None:
    #  Test CASE 2B - Send ForcePayment beyond payment time
    current_time = get_current_utc_timestamp()
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
                    task_to_compute=create_signed_task_to_compute(
                        timestamp=parse_timestamp_to_utc_datetime(current_time),
                        deadline=current_time,
                        price=15000,
                    )
                ),
                subtask_results_accepted(
                    timestamp=timestamp_to_isoformat(current_time),
                    payment_ts=current_time - cluster_consts.payment_due_time - AVERAGE_TIME_FOR_TWO_BLOCKS,
                    task_to_compute=create_signed_task_to_compute(
                        timestamp=parse_timestamp_to_utc_datetime(current_time),
                        deadline=current_time,
                        price=15000,
                    )
                )
            ]
        ),
        expected_status=200,
        expected_message_type=message.concents.ForcePaymentRejected,
        expected_content_type='application/octet-stream',
    )


@count_fails
def test_case_2_a_force_payment_with_subtask_result_accepted_where_ethereum_accounts_are_different(
    cluster_consts: ProtocolConstants,
    cluster_url: str,
) -> None:
    # Test CASE 2A - Send ForcePayment with SubtaskResultsAccepted where ethereum accounts are different
    current_time = get_current_utc_timestamp()
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
                    payment_ts=current_time - cluster_consts.payment_due_time - AVERAGE_TIME_FOR_TWO_BLOCKS,
                    task_to_compute=create_signed_task_to_compute(
                        timestamp=parse_timestamp_to_utc_datetime(current_time),
                        deadline=current_time,
                        price=15000,
                    )
                ),
                subtask_results_accepted(
                    timestamp=timestamp_to_isoformat(current_time),
                    payment_ts=current_time - cluster_consts.payment_due_time - AVERAGE_TIME_FOR_TWO_BLOCKS,
                    task_to_compute=create_signed_task_to_compute(
                        timestamp=parse_timestamp_to_utc_datetime(current_time),
                        deadline=current_time,
                        price=15000,
                        requestor_ethereum_public_key=DIFFERENT_REQUESTOR_ETHEREUM_PUBLIC_KEY,
                        requestor_ethereum_private_key=DIFFERENT_REQUESTOR_ETHEREUM_PRIVATE_KEY,
                    )
                )
            ]
        ),
        expected_status=200,
        expected_message_type=message.concents.ServiceRefused,
        expected_content_type='application/octet-stream',
    )


if __name__ == '__main__':
    try:
        from concent_api.settings import CONCENT_PUBLIC_KEY
        status = run_tests(globals())
        exit(status)
    except requests.exceptions.ConnectionError as exception:
        print("\nERROR: Failed connect to the server.\n", file = sys.stderr)
        sys.exit(str(exception))
