#!/usr/bin/env python3

import os
import sys
import time
from freezegun import freeze_time
from typing import Optional

from golem_messages import message

from common.helpers import get_current_utc_timestamp
from common.helpers import sign_message
from common.testing_helpers import generate_priv_and_pub_eth_account_key

from api_testing_common import api_request
from api_testing_common import count_fails
from api_testing_common import create_client_auth_message
from api_testing_common import create_signed_task_to_compute
from api_testing_common import PROVIDER_PRIVATE_KEY
from api_testing_common import PROVIDER_PUBLIC_KEY
from api_testing_common import REQUESTOR_PRIVATE_KEY
from api_testing_common import REQUESTOR_PUBLIC_KEY
from api_testing_common import run_tests
from api_testing_common import timestamp_to_isoformat
from protocol_constants import ProtocolConstants

import requests

from core.utils import calculate_maximum_download_time

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "concent_api.settings")


REPORT_COMPUTED_TASK_SIZE = 10

(DIFFERENT_REQUESTOR_ETHEREUM_PRIVATE_KEY, DIFFERENT_REQUESTOR_ETHEREUM_PUBLIC_KEY) = generate_priv_and_pub_eth_account_key()
(DIFFERENT_PROVIDER_ETHEREUM_PRIVATE_KEY, DIFFERENT_PROVIDER_ETHEREUM_PUBLIC_KEY) = generate_priv_and_pub_eth_account_key()


def force_subtask_results(
    timestamp: Optional[str]=None,
    ack_report_computed_task: Optional[message.tasks.AckReportComputedTask]=None,
) -> message.concents.ForceSubtaskResults:
    with freeze_time(timestamp):
        return message.concents.ForceSubtaskResults(
            ack_report_computed_task = ack_report_computed_task,
        )


def ack_report_computed_task(
    timestamp: Optional[str]=None,
    report_computed_task: Optional[message.tasks.AckReportComputedTask]=None,
) -> message.tasks.AckReportComputedTask:
    with freeze_time(timestamp):
        return sign_message(
            message.tasks.AckReportComputedTask(
                report_computed_task=report_computed_task,
            ),
            REQUESTOR_PRIVATE_KEY,
        )


def force_subtask_results_response(
    timestamp: Optional[str]=None,
    subtask_results_accepted: Optional[message.tasks.SubtaskResultsAccepted]=None,
    subtask_results_rejected: Optional[message.tasks.SubtaskResultsRejected]=None,
) -> message.concents.ForceSubtaskResultsResponse:
    with freeze_time(timestamp):
        return message.concents.ForceSubtaskResultsResponse(
            subtask_results_accepted = subtask_results_accepted,
            subtask_results_rejected = subtask_results_rejected,
        )


def subtask_results_accepted(
    timestamp: Optional[str]=None,
    payment_ts: Optional[str]=None,
    task_to_compute: Optional[message.tasks.TaskToCompute]=None,
) -> message.tasks.SubtaskResultsAccepted:
    with freeze_time(timestamp):
        return sign_message(
            message.tasks.SubtaskResultsAccepted(
                payment_ts = payment_ts,
                task_to_compute = task_to_compute,
            ),
            REQUESTOR_PRIVATE_KEY,
        )


def subtask_results_rejected(
    timestamp: Optional[str]=None,
    reason: Optional[message.tasks.SubtaskResultsRejected.REASON]=None,
    report_computed_task: Optional[message.tasks.ReportComputedTask]=None,
) -> message.tasks.SubtaskResultsRejected:
    with freeze_time(timestamp):
        return sign_message(
            message.tasks.SubtaskResultsRejected(
                reason                  = reason,
                report_computed_task    = report_computed_task,
            ),
            REQUESTOR_PRIVATE_KEY,
        )


def report_computed_task(
    timestamp: Optional[str]=None,
    task_to_compute: Optional[message.tasks.TaskToCompute]=None
) -> message.tasks.ReportComputedTask:
    with freeze_time(timestamp):
        return sign_message(
            message.tasks.ReportComputedTask(
                task_to_compute=task_to_compute,
                size=REPORT_COMPUTED_TASK_SIZE,
            ),
            PROVIDER_PRIVATE_KEY,
        )


def calculate_timestamp(current_time: int, concent_messaging_time: int, minimum_upload_rate: int) -> str:
    return timestamp_to_isoformat(
        current_time - (2 * concent_messaging_time + _precalculate_subtask_verification_time(minimum_upload_rate, concent_messaging_time))
    )


def calculate_deadline(current_time: int, concent_messaging_time: int, minimum_upload_rate: int) -> int:
    return current_time - (concent_messaging_time + _precalculate_subtask_verification_time(minimum_upload_rate, concent_messaging_time))


def calculate_deadline_too_far_in_the_future(current_time: int, minimum_upload_rate: int, concent_messaging_time: int) -> int:
    return current_time - (1 + (20 * _precalculate_subtask_verification_time(minimum_upload_rate, concent_messaging_time)))


def _precalculate_subtask_verification_time(minimum_upload_rate: int, concent_messaging_time: int) -> int:
    maxiumum_download_time = calculate_maximum_download_time(
        size=REPORT_COMPUTED_TASK_SIZE,
        rate=minimum_upload_rate,
    )
    return (
        (4 * concent_messaging_time) +
        (3 * maxiumum_download_time)
    )


@count_fails
def test_case_2d_requestor_rejects_subtask_results(
    cluster_consts: ProtocolConstants,
    cluster_url: str,
    task_id: str,
    subtask_id: str,
) -> None:
    # Test CASE 2D + 3 + 4B + 5. Requestor sends ForceSubtaskResultsResponse with SubtaskResultsRejected
    current_time = get_current_utc_timestamp()
    signed_task_to_compute = create_signed_task_to_compute(
        timestamp=calculate_timestamp(current_time, cluster_consts.concent_messaging_time, cluster_consts.minimum_upload_rate),
        task_id=task_id,
        subtask_id=subtask_id,
        deadline=calculate_deadline(current_time, cluster_consts.concent_messaging_time, cluster_consts.minimum_upload_rate),
        price=10000,
    )
    api_request(
        cluster_url,
        'send',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        force_subtask_results(
            timestamp=timestamp_to_isoformat(current_time),
            ack_report_computed_task=ack_report_computed_task(
                timestamp=timestamp_to_isoformat(current_time),
                report_computed_task=report_computed_task(
                    task_to_compute=signed_task_to_compute,
                )
            )
        ),
        headers={
            'Content-Type': 'application/octet-stream',
        },
        expected_status=202,
    )
    api_request(
        cluster_url,
        'receive',
        REQUESTOR_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        create_client_auth_message(REQUESTOR_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY, CONCENT_PUBLIC_KEY),
        headers={
            'Content-Type': 'application/octet-stream',
        },
        expected_status=200,
        expected_message_type=message.concents.ForceSubtaskResults,
        expected_content_type='application/octet-stream',
    )
    api_request(
        cluster_url,
        'send',
        REQUESTOR_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        force_subtask_results_response(
            timestamp=timestamp_to_isoformat(current_time),
            subtask_results_rejected=subtask_results_rejected(
                timestamp=timestamp_to_isoformat(current_time),
                report_computed_task=report_computed_task(
                    timestamp=timestamp_to_isoformat(current_time),
                    task_to_compute=signed_task_to_compute,
                )
            )
        ),
        headers={
            'Content-Type': 'application/octet-stream',
        },
        expected_status=202,
    )
    api_request(
        cluster_url,
        'receive',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        create_client_auth_message(PROVIDER_PRIVATE_KEY, PROVIDER_PUBLIC_KEY, CONCENT_PUBLIC_KEY),
        headers={
            'Content-Type': 'application/octet-stream',
        },
        expected_status=200,
        expected_message_type=message.concents.ForceSubtaskResultsResponse,
        expected_content_type='application/octet-stream',
    )


@count_fails
def test_case_4b_requestor_accepts_subtaks_results(
    cluster_consts: ProtocolConstants,
    cluster_url: str,
    task_id: str,
    subtask_id: str,
) -> None:
    # Test CASE 4B + 5. Requestor sends ForceSubtaskResultsResponse with SubtaskResultsAccepted
    #  Step 1. Provider sends ForceSubtaskResults
    current_time = get_current_utc_timestamp()
    signed_task_to_compute = create_signed_task_to_compute(
        timestamp=calculate_timestamp(current_time, cluster_consts.concent_messaging_time, cluster_consts.minimum_upload_rate),
        task_id=task_id,
        subtask_id=subtask_id,
        deadline=calculate_deadline(current_time, cluster_consts.concent_messaging_time, cluster_consts.minimum_upload_rate),
        price=10000,
    )
    api_request(
        cluster_url,
        'send',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        force_subtask_results(
            timestamp=timestamp_to_isoformat(current_time),
            ack_report_computed_task=ack_report_computed_task(
                timestamp=timestamp_to_isoformat(current_time),
                report_computed_task=report_computed_task(
                    task_to_compute=signed_task_to_compute
                )
            )
        ),
        headers={
            'Content-Type': 'application/octet-stream',
        },
        expected_status=202,
    )
    time.sleep(1)
    #  Step 2. Requestor receives ForceSubtaskResults
    api_request(
        cluster_url,
        'receive',
        REQUESTOR_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        create_client_auth_message(REQUESTOR_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY, CONCENT_PUBLIC_KEY),
        headers={
            'Content-Type': 'application/octet-stream',
        },
        expected_status=200,
        expected_message_type=message.concents.ForceSubtaskResults,
        expected_content_type='application/octet-stream',
    )
    #  Step 3. Requestor sends ForceSubtaskResultsResponse
    api_request(
        cluster_url,
        'send',
        REQUESTOR_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        force_subtask_results_response(
            timestamp=timestamp_to_isoformat(current_time),
            subtask_results_accepted=subtask_results_accepted(
                timestamp=timestamp_to_isoformat(current_time),
                payment_ts=timestamp_to_isoformat(current_time + 1),
                task_to_compute=signed_task_to_compute
            )
        ),
        headers={
            'Content-Type': 'application/octet-stream',
        },
        expected_status=202,
    )
    #  Step 4. Provider receives ForceSubtaskResultsResponse
    api_request(
        cluster_url,
        'receive',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        create_client_auth_message(PROVIDER_PRIVATE_KEY, PROVIDER_PUBLIC_KEY, CONCENT_PUBLIC_KEY),
        headers={
            'Content-Type': 'application/octet-stream',
        },
        expected_status=200,
        expected_message_type=message.concents.ForceSubtaskResultsResponse,
        expected_content_type='application/octet-stream',
    )


@count_fails
def test_case_2c_wrong_timestamps(
    cluster_consts: ProtocolConstants,
    cluster_url: str,
    task_id: str,
    subtask_id: str,
) -> None:
    # Test CASE 2C - Send ForceSubtaskResults with wrong timestamps
    current_time = get_current_utc_timestamp()
    api_request(
        cluster_url,
        'send',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        force_subtask_results(
            timestamp=timestamp_to_isoformat(current_time),
            ack_report_computed_task=ack_report_computed_task(
                timestamp=timestamp_to_isoformat(current_time),
                report_computed_task=report_computed_task(
                    task_to_compute=create_signed_task_to_compute(
                        timestamp=calculate_timestamp(current_time, cluster_consts.concent_messaging_time, cluster_consts.minimum_upload_rate),
                        task_id=task_id,
                        subtask_id=subtask_id,
                        deadline=calculate_deadline_too_far_in_the_future(current_time, cluster_consts.concent_messaging_time, cluster_consts.minimum_upload_rate),
                        price=10000,
                    )
                )
            )
        ),
        headers={
            'Content-Type': 'application/octet-stream',
        },
        expected_status=200,
        expected_message_type=message.concents.ForceSubtaskResultsRejected,
        expected_content_type='application/octet-stream',
    )


@count_fails
def test_case_2b_not_enough_funds(
    cluster_consts: ProtocolConstants,
    cluster_url: str,
    task_id: str,
    subtask_id: str,
) -> None:
    #  Test CASE 2B - Send ForceSubtaskResults with not enough amount of funds on account
    current_time = get_current_utc_timestamp()
    api_request(
        cluster_url,
        'send',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        force_subtask_results(
            timestamp=timestamp_to_isoformat(current_time),
            ack_report_computed_task=ack_report_computed_task(
                timestamp=timestamp_to_isoformat(current_time),
                report_computed_task=report_computed_task(
                    task_to_compute=create_signed_task_to_compute(
                        timestamp=calculate_timestamp(current_time, cluster_consts.concent_messaging_time, cluster_consts.minimum_upload_rate),
                        task_id=task_id,
                        subtask_id=subtask_id,
                        deadline=calculate_deadline(current_time, cluster_consts.concent_messaging_time, cluster_consts.minimum_upload_rate),
                        requestor_ethereum_public_key=DIFFERENT_REQUESTOR_ETHEREUM_PUBLIC_KEY,
                        requestor_ethereum_private_key=DIFFERENT_REQUESTOR_ETHEREUM_PRIVATE_KEY,
                        provider_ethereum_public_key=DIFFERENT_PROVIDER_ETHEREUM_PUBLIC_KEY,
                        price=0,
                    )
                )
            )
        ),
        headers={
            'Content-Type': 'application/octet-stream',
        },
        expected_status=200,
        expected_message_type=message.concents.ServiceRefused,
        expected_content_type='application/octet-stream',
    )


@count_fails
def test_case_2a_send_duplicated_force_subtask_results(
    cluster_consts: ProtocolConstants,
    cluster_url: str,
    task_id: str,
    subtask_id: str,
) -> None:
    #  Test CASE 2A + 2D + 3 - Send ForceSubtaskResults with same task_id as stored by Concent before
    #  Step 1. Send ForceSubtaskResults first time
    current_time = get_current_utc_timestamp()
    signed_task_to_compute = create_signed_task_to_compute(
        timestamp=calculate_timestamp(current_time, cluster_consts.concent_messaging_time, cluster_consts.minimum_upload_rate),
        task_id=task_id,
        subtask_id=subtask_id,
        deadline=calculate_deadline(current_time, cluster_consts.concent_messaging_time, cluster_consts.minimum_upload_rate),
        price=10000,
    )
    api_request(
        cluster_url,
        'send',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        force_subtask_results(
            timestamp=timestamp_to_isoformat(current_time),
            ack_report_computed_task=ack_report_computed_task(
                timestamp=timestamp_to_isoformat(current_time),
                report_computed_task=report_computed_task(
                    task_to_compute=signed_task_to_compute
                )
            )
        ),
        headers={
            'Content-Type': 'application/octet-stream',
        },
        expected_status=202,
    )
    time.sleep(1)
    #  Step 2. Send ForceSubtaskResults second time with same task_id
    api_request(
        cluster_url,
        'send',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        force_subtask_results(
            timestamp=timestamp_to_isoformat(current_time),
            ack_report_computed_task=ack_report_computed_task(
                timestamp=timestamp_to_isoformat(current_time),
                report_computed_task=report_computed_task(
                    task_to_compute=signed_task_to_compute
                )
            )
        ),
        headers={
            'Content-Type': 'application/octet-stream',
        },
        expected_status=200,
        expected_message_type=message.concents.ServiceRefused,
        expected_content_type='application/octet-stream',
    )
    #  Step 3. Requestor wants to receive ForceSubtaskResults from Concent
    api_request(
        cluster_url,
        'receive',
        REQUESTOR_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        create_client_auth_message(REQUESTOR_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY, CONCENT_PUBLIC_KEY),
        headers={
            'Content-Type': 'application/octet-stream',
        },
        expected_status=200,
        expected_message_type=message.concents.ForceSubtaskResults,
        expected_content_type='application/octet-stream',
    )


if __name__ == '__main__':
    try:
        from concent_api.settings import CONCENT_PUBLIC_KEY
        run_tests(globals())
    except requests.exceptions.ConnectionError as exception:
        print("\nERROR: Failed connect to the server.\n", file = sys.stderr)
        sys.exit(str(exception))
