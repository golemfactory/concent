#!/usr/bin/env python3
from typing import Optional
from typing import Union
import datetime
import os
import sys
import time

from freezegun import freeze_time
from mock import Mock

from golem_messages import message

from common.helpers import get_current_utc_timestamp
from common.helpers import parse_timestamp_to_utc_datetime

from api_testing_common import api_request
from api_testing_common import count_fails
from api_testing_common import create_client_auth_message
from api_testing_common import create_signed_report_computed_task
from api_testing_common import create_signed_subtask_results_accepted
from api_testing_common import create_signed_task_to_compute
from api_testing_common import receive_pending_messages_for_requestor_and_provider
from api_testing_common import run_tests
from api_testing_common import timestamp_to_isoformat
from protocol_constants import ProtocolConstants

import requests


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "concent_api.settings")

"""
Average time for 2 blocks
Constans needed for test to get last 2 blocks
"""
AVERAGE_TIME_FOR_TWO_BLOCKS = 30


def force_payment(
    timestamp: Optional[Union[datetime.datetime, str]]=None,
    subtask_results_accepted_list: Optional[list]=None
) -> message.concents.ForcePayment:
    with freeze_time(timestamp):
        return message.concents.ForcePayment(
            subtask_results_accepted_list = subtask_results_accepted_list
        )


@count_fails
def test_case_2d_send_correct_force_payment(cluster_consts: ProtocolConstants, cluster_url: str) -> None:
    # Test CASE 2D - Send correct ForcePayment
    receive_pending_messages_for_requestor_and_provider(
        cluster_url,
        sci_base,
        CONCENT_PUBLIC_KEY
    )
    provider_gntb_balance = sci_base.get_provider_gntb_balance()
    current_time = get_current_utc_timestamp()
    correct_force_payment = force_payment(
        subtask_results_accepted_list=[
            create_signed_subtask_results_accepted(
                payment_ts=current_time - cluster_consts.payment_due_time - AVERAGE_TIME_FOR_TWO_BLOCKS,
                report_computed_task=create_signed_report_computed_task(
                    task_to_compute=create_signed_task_to_compute(
                        timestamp=parse_timestamp_to_utc_datetime(current_time),
                        deadline=current_time,
                        price=1000,
                        provider_public_key=sci_base.provider_public_key,
                        provider_private_key=sci_base.provider_private_key,
                        requestor_public_key=sci_base.requestor_public_key,
                        requestor_private_key=sci_base.requestor_private_key,
                    ),
                    provider_private_key=sci_base.provider_private_key
                ),
                requestor_private_key=sci_base.requestor_private_key,
            ),
            create_signed_subtask_results_accepted(
                payment_ts=current_time - cluster_consts.payment_due_time - AVERAGE_TIME_FOR_TWO_BLOCKS,
                report_computed_task=create_signed_report_computed_task(
                    task_to_compute=create_signed_task_to_compute(
                        timestamp=parse_timestamp_to_utc_datetime(current_time),
                        deadline=current_time,
                        price=1000,
                        provider_public_key=sci_base.provider_public_key,
                        provider_private_key=sci_base.provider_private_key,
                        requestor_public_key=sci_base.requestor_public_key,
                        requestor_private_key=sci_base.requestor_private_key,
                    ),
                    provider_private_key=sci_base.provider_private_key
                ),
                requestor_private_key=sci_base.requestor_private_key,
            ),
        ]
    )
    correct_force_payment.sig = None
    requestor_deposit_value = sci_base.get_requestor_deposit_value()
    api_request(
        cluster_url,
        'send',
        sci_base.provider_private_key,
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
        sci_base.requestor_private_key,
        CONCENT_PUBLIC_KEY,
        create_client_auth_message(sci_base.requestor_private_key, sci_base.requestor_public_key, CONCENT_PUBLIC_KEY),
        expected_status=200,
        expected_message_type=message.concents.ForcePaymentCommitted,
        expected_content_type='application/octet-stream',
    )
    sci_base.ensure_that_provider_has_specific_gntb_balance(value=provider_gntb_balance + 2000)
    sci_base.ensure_that_requestor_has_specific_deposit_balance(value=requestor_deposit_value - 2000)


@count_fails
def test_case_2c_send_force_payment_with_no_value_to_be_paid(cluster_consts: ProtocolConstants, cluster_url: str) -> None:
    #  Test CASE 2C - Send ForcePayment with no value to be paid
    receive_pending_messages_for_requestor_and_provider(
        cluster_url,
        sci_base,
        CONCENT_PUBLIC_KEY
    )
    current_time = get_current_utc_timestamp()
    api_request(
        cluster_url,
        'send',
        sci_base.provider_private_key,
        CONCENT_PUBLIC_KEY,
        force_payment(
            timestamp=timestamp_to_isoformat(current_time),
            subtask_results_accepted_list=[
                create_signed_subtask_results_accepted(
                    timestamp=timestamp_to_isoformat(current_time),
                    payment_ts=current_time - cluster_consts.payment_due_time - AVERAGE_TIME_FOR_TWO_BLOCKS,
                    report_computed_task=create_signed_report_computed_task(
                        task_to_compute=create_signed_task_to_compute(
                            timestamp=parse_timestamp_to_utc_datetime(current_time),
                            deadline=current_time,
                            price=0,
                            provider_public_key=sci_base.provider_public_key,
                            provider_private_key=sci_base.provider_private_key,
                            requestor_public_key=sci_base.requestor_public_key,
                            requestor_private_key=sci_base.requestor_private_key,
                        ),
                        provider_private_key=sci_base.provider_private_key
                    ),
                    requestor_private_key=sci_base.requestor_private_key,
                ),
                create_signed_subtask_results_accepted(
                    timestamp=timestamp_to_isoformat(current_time),
                    payment_ts=current_time - cluster_consts.payment_due_time - AVERAGE_TIME_FOR_TWO_BLOCKS,
                    report_computed_task=create_signed_report_computed_task(
                        task_to_compute=create_signed_task_to_compute(
                            timestamp=parse_timestamp_to_utc_datetime(current_time),
                            deadline=current_time,
                            price=0,
                            provider_public_key=sci_base.provider_public_key,
                            provider_private_key=sci_base.provider_private_key,
                            requestor_public_key=sci_base.requestor_public_key,
                            requestor_private_key=sci_base.requestor_private_key,
                        ),
                        provider_private_key=sci_base.provider_private_key
                    ),
                    requestor_private_key=sci_base.requestor_private_key,
                ),
            ]
        ),
        expected_status=400,
        expected_error_code='message.value_negative',
    )


@count_fails
def test_case_2b_send_force_payment_beyond_payment_time(cluster_consts: ProtocolConstants, cluster_url: str) -> None:
    #  Test CASE 2B - Send ForcePayment beyond payment time
    receive_pending_messages_for_requestor_and_provider(
        cluster_url,
        sci_base,
        CONCENT_PUBLIC_KEY
    )
    current_time = get_current_utc_timestamp()
    api_request(
        cluster_url,
        'send',
        sci_base.provider_private_key,
        CONCENT_PUBLIC_KEY,
        force_payment(
            timestamp=timestamp_to_isoformat(current_time),
            subtask_results_accepted_list=[
                create_signed_subtask_results_accepted(
                    timestamp=timestamp_to_isoformat(current_time),
                    payment_ts=current_time,
                    report_computed_task=create_signed_report_computed_task(
                        task_to_compute=create_signed_task_to_compute(
                            timestamp=parse_timestamp_to_utc_datetime(current_time),
                            deadline=current_time,
                            price=15000,
                            provider_public_key=sci_base.provider_public_key,
                            provider_private_key=sci_base.provider_private_key,
                            requestor_public_key=sci_base.requestor_public_key,
                            requestor_private_key=sci_base.requestor_private_key,
                        ),
                        provider_private_key=sci_base.provider_private_key,
                    ),
                    requestor_private_key=sci_base.requestor_private_key
                ),

                create_signed_subtask_results_accepted(
                    timestamp=timestamp_to_isoformat(current_time),
                    payment_ts=current_time - cluster_consts.payment_due_time - AVERAGE_TIME_FOR_TWO_BLOCKS,
                    report_computed_task=create_signed_report_computed_task(
                        task_to_compute=create_signed_task_to_compute(
                            timestamp=parse_timestamp_to_utc_datetime(current_time),
                            deadline=current_time,
                            price=15000,
                            provider_public_key=sci_base.provider_public_key,
                            provider_private_key=sci_base.provider_private_key,
                            requestor_public_key=sci_base.requestor_public_key,
                            requestor_private_key=sci_base.requestor_private_key,
                        ),
                        provider_private_key=sci_base.provider_private_key,
                    ),
                    requestor_private_key=sci_base.requestor_private_key
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
    receive_pending_messages_for_requestor_and_provider(
        cluster_url,
        sci_base,
        CONCENT_PUBLIC_KEY
    )
    current_time = get_current_utc_timestamp()
    api_request(
        cluster_url,
        'send',
        sci_base.provider_private_key,
        CONCENT_PUBLIC_KEY,
        force_payment(
            timestamp=timestamp_to_isoformat(current_time),
            subtask_results_accepted_list=[
                create_signed_subtask_results_accepted(
                    timestamp=timestamp_to_isoformat(current_time),
                    payment_ts=current_time - cluster_consts.payment_due_time - AVERAGE_TIME_FOR_TWO_BLOCKS,
                    report_computed_task=create_signed_report_computed_task(
                        task_to_compute=create_signed_task_to_compute(
                            timestamp=parse_timestamp_to_utc_datetime(current_time),
                            deadline=current_time,
                            price=15000,
                            provider_public_key=sci_base.provider_public_key,
                            provider_private_key=sci_base.provider_private_key,
                            requestor_public_key=sci_base.requestor_public_key,
                            requestor_private_key=sci_base.requestor_private_key,
                        ),
                        provider_private_key=sci_base.provider_private_key,
                    ),
                    requestor_private_key=sci_base.requestor_private_key
                ),

                create_signed_subtask_results_accepted(
                    timestamp=timestamp_to_isoformat(current_time),
                    payment_ts=current_time - cluster_consts.payment_due_time - AVERAGE_TIME_FOR_TWO_BLOCKS,
                    report_computed_task=create_signed_report_computed_task(
                        task_to_compute=create_signed_task_to_compute(
                            timestamp=parse_timestamp_to_utc_datetime(current_time),
                            deadline=current_time,
                            price=15000,
                            provider_public_key=sci_base.provider_empty_account_public_key,
                            provider_private_key=sci_base.provider_empty_account_private_key,
                            requestor_public_key=sci_base.requestor_empty_account_public_key,
                            requestor_private_key=sci_base.requestor_empty_account_private_key,
                        ),
                        provider_private_key=sci_base.provider_private_key,
                    ),
                    requestor_private_key=sci_base.requestor_private_key
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
        # Dirty workaround for init `sci_base` variable to hide errors in IDE.
        # sci_base is initiated in `run_tests` function
        sci_base = Mock()
        status = run_tests(globals())
        exit(status)
    except requests.exceptions.ConnectionError as exception:
        print("\nERROR: Failed connect to the server.\n", file = sys.stderr)
        sys.exit(str(exception))
