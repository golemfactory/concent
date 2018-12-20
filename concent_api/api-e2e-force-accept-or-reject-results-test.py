#!/usr/bin/env python3

import os
import sys
import time
from freezegun import freeze_time
from typing import Optional
from mock import Mock

from golem_messages import message

from common.helpers import get_current_utc_timestamp
from common.helpers import sign_message

from api_testing_common import api_request
from api_testing_common import count_fails
from api_testing_common import create_client_auth_message
from api_testing_common import create_signed_report_computed_task
from api_testing_common import create_signed_subtask_results_accepted
from api_testing_common import create_signed_task_to_compute
from api_testing_common import receive_pending_messages_for_requestor_and_provider
from api_testing_common import REPORT_COMPUTED_TASK_SIZE
from api_testing_common import run_tests
from api_testing_common import timestamp_to_isoformat
from protocol_constants import ProtocolConstants

import requests

from core.utils import calculate_maximum_download_time

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "concent_api.settings")


def create_force_subtask_results(
    timestamp: Optional[str]=None,
    ack_report_computed_task: Optional[message.tasks.AckReportComputedTask]=None,
) -> message.concents.ForceSubtaskResults:
    with freeze_time(timestamp):
        return message.concents.ForceSubtaskResults(
            ack_report_computed_task=ack_report_computed_task,
        )


def create_ack_report_computed_task(
    requestor_private_key: bytes,
    timestamp: Optional[str]=None,
    report_computed_task: Optional[message.tasks.ReportComputedTask]=None,
) -> message.tasks.AckReportComputedTask:
    with freeze_time(timestamp):
        signed_message: message.tasks.AckReportComputedTask = sign_message(
            message.tasks.AckReportComputedTask(
                report_computed_task=report_computed_task,
            ),
            requestor_private_key,
        )
        return signed_message


def create_force_subtask_results_response(
    timestamp: Optional[str]=None,
    subtask_results_accepted: Optional[message.tasks.SubtaskResultsAccepted]=None,
    subtask_results_rejected: Optional[message.tasks.SubtaskResultsRejected]=None,
) -> message.concents.ForceSubtaskResultsResponse:
    with freeze_time(timestamp):
        return message.concents.ForceSubtaskResultsResponse(
            subtask_results_accepted=subtask_results_accepted,
            subtask_results_rejected=subtask_results_rejected,
        )


def create_subtask_results_rejected(
    requestor_private_key: bytes,
    timestamp: Optional[str]=None,
    reason: Optional[message.tasks.SubtaskResultsRejected.REASON]=None,
    report_computed_task: Optional[message.tasks.ReportComputedTask]=None,
) -> message.tasks.SubtaskResultsRejected:
    with freeze_time(timestamp):
        signed_message: message.tasks.SubtaskResultsRejected = sign_message(
            message.tasks.SubtaskResultsRejected(
                reason=reason,
                report_computed_task=report_computed_task,
            ),
            requestor_private_key,
        )
        return signed_message


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
def test_case_2d_requestor_rejects_subtask_results(cluster_consts: ProtocolConstants, cluster_url: str) -> None:
    # Test CASE 2D + 3 + 4B + 5. Requestor sends ForceSubtaskResultsResponse with SubtaskResultsRejected
    receive_pending_messages_for_requestor_and_provider(
        cluster_url,
        sci_base,
        CONCENT_PUBLIC_KEY
    )
    current_time = get_current_utc_timestamp()
    signed_task_to_compute = create_signed_task_to_compute(
        timestamp=calculate_timestamp(current_time, cluster_consts.concent_messaging_time, cluster_consts.minimum_upload_rate),
        deadline=calculate_deadline(current_time, cluster_consts.concent_messaging_time, cluster_consts.minimum_upload_rate),
        price=1000,
        provider_public_key=sci_base.provider_public_key,
        provider_private_key=sci_base.provider_private_key,
        requestor_public_key=sci_base.requestor_public_key,
        requestor_private_key=sci_base.requestor_private_key
    )
    api_request(
        cluster_url,
        'send',
        sci_base.provider_private_key,
        CONCENT_PUBLIC_KEY,
        create_force_subtask_results(
            timestamp=timestamp_to_isoformat(current_time),
            ack_report_computed_task=create_ack_report_computed_task(
                timestamp=timestamp_to_isoformat(current_time),
                report_computed_task=create_signed_report_computed_task(
                    task_to_compute=signed_task_to_compute,
                    provider_private_key=sci_base.provider_private_key,
                ),
                requestor_private_key=sci_base.requestor_private_key
            )
        ),
        expected_status=202,
    )
    api_request(
        cluster_url,
        'receive',
        sci_base.requestor_private_key,
        CONCENT_PUBLIC_KEY,
        create_client_auth_message(sci_base.requestor_private_key, sci_base.requestor_public_key, CONCENT_PUBLIC_KEY),
        expected_status=200,
        expected_message_type=message.concents.ForceSubtaskResults,
        expected_content_type='application/octet-stream',
    )
    api_request(
        cluster_url,
        'send',
        sci_base.requestor_private_key,
        CONCENT_PUBLIC_KEY,
        create_force_subtask_results_response(
            timestamp=timestamp_to_isoformat(current_time),
            subtask_results_rejected=create_subtask_results_rejected(
                timestamp=timestamp_to_isoformat(current_time),
                report_computed_task=create_signed_report_computed_task(
                    task_to_compute=signed_task_to_compute,
                    timestamp=timestamp_to_isoformat(current_time),
                    provider_private_key=sci_base.provider_private_key,
                ),
                requestor_private_key=sci_base.requestor_private_key
            )
        ),
        expected_status=202,
    )
    api_request(
        cluster_url,
        'receive',
        sci_base.provider_private_key,
        CONCENT_PUBLIC_KEY,
        create_client_auth_message(sci_base.provider_private_key, sci_base.provider_public_key, CONCENT_PUBLIC_KEY),
        expected_status=200,
        expected_message_type=message.concents.ForceSubtaskResultsResponse,
        expected_content_type='application/octet-stream',
    )


@count_fails
def test_case_4b_requestor_accepts_subtaks_results(cluster_consts: ProtocolConstants, cluster_url: str) -> None:
    # Test CASE 4B + 5. Requestor sends ForceSubtaskResultsResponse with SubtaskResultsAccepted
    #  Step 1. Provider sends ForceSubtaskResults
    receive_pending_messages_for_requestor_and_provider(
        cluster_url,
        sci_base,
        CONCENT_PUBLIC_KEY
    )
    current_time = get_current_utc_timestamp()
    signed_task_to_compute = create_signed_task_to_compute(
        timestamp=calculate_timestamp(current_time, cluster_consts.concent_messaging_time, cluster_consts.minimum_upload_rate),
        deadline=calculate_deadline(current_time, cluster_consts.concent_messaging_time, cluster_consts.minimum_upload_rate),
        price=1000,
        provider_public_key=sci_base.provider_public_key,
        provider_private_key=sci_base.provider_private_key,
        requestor_public_key=sci_base.requestor_public_key,
        requestor_private_key=sci_base.requestor_private_key
    )
    signed_report_computed_task = create_signed_report_computed_task(
        task_to_compute=signed_task_to_compute,
        provider_private_key=sci_base.provider_private_key,
    )
    api_request(
        cluster_url,
        'send',
        sci_base.provider_private_key,
        CONCENT_PUBLIC_KEY,
        create_force_subtask_results(
            timestamp=timestamp_to_isoformat(current_time),
            ack_report_computed_task=create_ack_report_computed_task(
                timestamp=timestamp_to_isoformat(current_time),
                report_computed_task=signed_report_computed_task,
                requestor_private_key=sci_base.requestor_private_key
            )
        ),
        expected_status=202,
    )
    time.sleep(1)
    #  Step 2. Requestor receives ForceSubtaskResults
    api_request(
        cluster_url,
        'receive',
        sci_base.requestor_private_key,
        CONCENT_PUBLIC_KEY,
        create_client_auth_message(sci_base.requestor_private_key, sci_base.requestor_public_key, CONCENT_PUBLIC_KEY),
        expected_status=200,
        expected_message_type=message.concents.ForceSubtaskResults,
        expected_content_type='application/octet-stream',
    )
    #  Step 3. Requestor sends ForceSubtaskResultsResponse
    api_request(
        cluster_url,
        'send',
        sci_base.requestor_private_key,
        CONCENT_PUBLIC_KEY,
        create_force_subtask_results_response(
            timestamp=timestamp_to_isoformat(current_time),
            subtask_results_accepted=create_signed_subtask_results_accepted(
                payment_ts=current_time + 1,
                report_computed_task=signed_report_computed_task,
                requestor_private_key=sci_base.requestor_private_key,
            )
        ),
        expected_status=202,
    )
    #  Step 4. Provider receives ForceSubtaskResultsResponse
    api_request(
        cluster_url,
        'receive',
        sci_base.provider_private_key,
        CONCENT_PUBLIC_KEY,
        create_client_auth_message(sci_base.provider_private_key, sci_base.provider_public_key, CONCENT_PUBLIC_KEY),
        expected_status=200,
        expected_message_type=message.concents.ForceSubtaskResultsResponse,
        expected_content_type='application/octet-stream',
    )


@count_fails
def test_case_2c_wrong_timestamps(cluster_consts: ProtocolConstants, cluster_url: str) -> None:
    # Test CASE 2C - Send ForceSubtaskResults with wrong timestamps
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
        create_force_subtask_results(
            timestamp=timestamp_to_isoformat(current_time),
            ack_report_computed_task=create_ack_report_computed_task(
                timestamp=timestamp_to_isoformat(current_time),
                report_computed_task=create_signed_report_computed_task(
                    task_to_compute=create_signed_task_to_compute(
                        timestamp=calculate_timestamp(
                            current_time,
                            cluster_consts.concent_messaging_time,
                            cluster_consts.minimum_upload_rate
                        ),
                        deadline=calculate_deadline_too_far_in_the_future(
                            current_time,
                            cluster_consts.concent_messaging_time,
                            cluster_consts.minimum_upload_rate
                        ),
                        price=1000,
                        provider_public_key=sci_base.provider_public_key,
                        provider_private_key=sci_base.provider_private_key,
                        requestor_public_key=sci_base.requestor_public_key,
                        requestor_private_key=sci_base.requestor_private_key
                    ),
                    provider_private_key=sci_base.provider_private_key,
                ),
                requestor_private_key=sci_base.requestor_private_key
            )
        ),
        expected_status=200,
        expected_message_type=message.concents.ForceSubtaskResultsRejected,
        expected_content_type='application/octet-stream',
    )


@count_fails
def test_case_2b_not_enough_funds(cluster_consts: ProtocolConstants, cluster_url: str) -> None:
    #  Test CASE 2B - Send ForceSubtaskResults with not enough amount of funds on account
    receive_pending_messages_for_requestor_and_provider(
        cluster_url,
        sci_base,
        CONCENT_PUBLIC_KEY
    )
    current_time = get_current_utc_timestamp()
    api_request(
        cluster_url,
        'send',
        sci_base.provider_empty_account_private_key,
        CONCENT_PUBLIC_KEY,
        create_force_subtask_results(
            timestamp=timestamp_to_isoformat(current_time),
            ack_report_computed_task=create_ack_report_computed_task(
                timestamp=timestamp_to_isoformat(current_time),
                report_computed_task=create_signed_report_computed_task(
                    task_to_compute=create_signed_task_to_compute(
                        timestamp=calculate_timestamp(current_time, cluster_consts.concent_messaging_time,
                                                      cluster_consts.minimum_upload_rate),
                        deadline=calculate_deadline(current_time, cluster_consts.concent_messaging_time,
                                                    cluster_consts.minimum_upload_rate),
                        price=10000,
                        provider_public_key=sci_base.provider_empty_account_public_key,
                        provider_private_key=sci_base.provider_empty_account_private_key,
                        requestor_public_key=sci_base.requestor_empty_account_public_key,
                        requestor_private_key=sci_base.requestor_empty_account_private_key
                    ),
                    provider_private_key=sci_base.provider_empty_account_private_key,
                ),
                requestor_private_key=sci_base.requestor_empty_account_private_key,
            )
        ),
        expected_status=200,
        expected_message_type=message.concents.ServiceRefused,
        expected_content_type='application/octet-stream',
    )


@count_fails
def test_case_2a_send_duplicated_force_subtask_results(cluster_consts: ProtocolConstants, cluster_url: str) -> None:
    #  Test CASE 2A + 2D + 3 - Send ForceSubtaskResults with same task_id as stored by Concent before
    #  Step 1. Send ForceSubtaskResults first time
    receive_pending_messages_for_requestor_and_provider(
        cluster_url,
        sci_base,
        CONCENT_PUBLIC_KEY
    )
    current_time = get_current_utc_timestamp()
    signed_task_to_compute = create_signed_task_to_compute(
        timestamp=calculate_timestamp(current_time, cluster_consts.concent_messaging_time, cluster_consts.minimum_upload_rate),
        deadline=calculate_deadline(current_time, cluster_consts.concent_messaging_time, cluster_consts.minimum_upload_rate),
        price=1000,
        provider_public_key=sci_base.provider_public_key,
        provider_private_key=sci_base.provider_private_key,
        requestor_public_key=sci_base.requestor_public_key,
        requestor_private_key=sci_base.requestor_private_key
    )
    force_subtask_results = create_force_subtask_results(
        timestamp=timestamp_to_isoformat(current_time),
        ack_report_computed_task=create_ack_report_computed_task(
            timestamp=timestamp_to_isoformat(current_time),
            report_computed_task=create_signed_report_computed_task(
                task_to_compute=signed_task_to_compute,
                provider_private_key=sci_base.provider_private_key,
            ),
            requestor_private_key=sci_base.requestor_private_key,
        )
    )
    api_request(
        cluster_url,
        'send',
        sci_base.provider_private_key,
        CONCENT_PUBLIC_KEY,
        force_subtask_results,
        expected_status=202,
    )
    time.sleep(1)
    #  Step 2. Send ForceSubtaskResults second time with same task_id
    # Signature must be set to None, because msg will be signed again in api_request()
    force_subtask_results.sig = None
    api_request(
        cluster_url,
        'send',
        sci_base.provider_private_key,
        CONCENT_PUBLIC_KEY,
        force_subtask_results,
        expected_status=200,
        expected_message_type=message.concents.ServiceRefused,
        expected_content_type='application/octet-stream',
    )
    #  Step 3. Requestor wants to receive ForceSubtaskResults from Concent
    api_request(
        cluster_url,
        'receive',
        sci_base.requestor_private_key,
        CONCENT_PUBLIC_KEY,
        create_client_auth_message(sci_base.requestor_private_key, sci_base.requestor_public_key, CONCENT_PUBLIC_KEY),
        expected_status=200,
        expected_message_type=message.concents.ForceSubtaskResults,
        expected_content_type='application/octet-stream',
    )


if __name__ == '__main__':
    try:
        from concent_api.settings import CONCENT_PUBLIC_KEY
        # Dirty workaround for init `sci_base` variable to hide errors in IDE.
        # sci_base is initiated in `run_tests` function
        sci_base = Mock()
        run_tests(globals())
    except requests.exceptions.ConnectionError as exception:
        print("\nERROR: Failed connect to the server.\n", file = sys.stderr)
        sys.exit(str(exception))
