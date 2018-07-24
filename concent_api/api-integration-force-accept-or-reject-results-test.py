#!/usr/bin/env python3

import os
import sys
import time
from freezegun import freeze_time

from golem_messages import message
from golem_messages.utils import encode_hex

from common.helpers import get_current_utc_timestamp
from common.helpers import sign_message

from api_testing_common import api_request
from api_testing_common import count_fails
from api_testing_common import create_client_auth_message
from api_testing_common import create_signed_task_to_compute
from api_testing_common import get_task_id_and_subtask_id
from api_testing_common import PROVIDER_PRIVATE_KEY
from api_testing_common import PROVIDER_PUBLIC_KEY
from api_testing_common import REQUESTOR_PRIVATE_KEY
from api_testing_common import REQUESTOR_PUBLIC_KEY
from api_testing_common import run_tests
from api_testing_common import timestamp_to_isoformat

import requests

from core.utils import calculate_maximum_download_time

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "concent_api.settings")


REPORT_COMPUTED_TASK_SIZE = 10


def force_subtask_results(timestamp = None, ack_report_computed_task = None):
    with freeze_time(timestamp):
        return message.concents.ForceSubtaskResults(
            ack_report_computed_task = ack_report_computed_task,
        )


def ack_report_computed_task(timestamp = None, report_computed_task = None):
    with freeze_time(timestamp):
        return sign_message(
            message.AckReportComputedTask(
                report_computed_task=report_computed_task,
            ),
            REQUESTOR_PRIVATE_KEY,
        )


def force_subtask_results_response(timestamp = None, subtask_results_accepted = None, subtask_results_rejected = None):
    with freeze_time(timestamp):
        return message.concents.ForceSubtaskResultsResponse(
            subtask_results_accepted = subtask_results_accepted,
            subtask_results_rejected = subtask_results_rejected,
        )


def subtask_results_accepted(timestamp = None, payment_ts = None, task_to_compute = None):
    with freeze_time(timestamp):
        return sign_message(
            message.tasks.SubtaskResultsAccepted(
                payment_ts = payment_ts,
                task_to_compute = task_to_compute,
            ),
            REQUESTOR_PRIVATE_KEY,
        )


def subtask_results_rejected(timestamp = None, reason = None, report_computed_task = None):
    with freeze_time(timestamp):
        return sign_message(
            message.tasks.SubtaskResultsRejected(
                reason                  = reason,
                report_computed_task    = report_computed_task,
            ),
            REQUESTOR_PRIVATE_KEY,
        )


def report_computed_task(timestamp = None, task_to_compute = None):
    with freeze_time(timestamp):
        return sign_message(
            message.tasks.ReportComputedTask(
                task_to_compute=task_to_compute,
                size=REPORT_COMPUTED_TASK_SIZE,
            ),
            PROVIDER_PRIVATE_KEY,
        )


def calculate_timestamp(current_time, concent_messaging_time, minimum_upload_rate):
    return timestamp_to_isoformat(
        current_time - (2 * concent_messaging_time + _precalculate_subtask_verification_time(minimum_upload_rate, concent_messaging_time))
    )


def calculate_deadline(current_time, concent_messaging_time, minimum_upload_rate):
    return current_time - (concent_messaging_time + _precalculate_subtask_verification_time(minimum_upload_rate, concent_messaging_time))


def calculate_deadline_too_far_in_the_future(current_time, minimum_upload_rate, concent_messaging_time):
    return current_time - (1 + (20 * _precalculate_subtask_verification_time(minimum_upload_rate, concent_messaging_time)))


def _precalculate_subtask_verification_time(minimum_upload_rate, concent_messaging_time):
    maxiumum_download_time = calculate_maximum_download_time(
        size=REPORT_COMPUTED_TASK_SIZE,
        rate=minimum_upload_rate,
    )
    return (
        (4 * concent_messaging_time) +
        (3 * maxiumum_download_time)
    )


@count_fails
def test_case_2d_requestor_rejects_subtask_results(cluster_consts, cluster_url, test_id):
    # Test CASE 2D + 3 + 4B + 5. Requestor sends ForceSubtaskResultsResponse with SubtaskResultsRejected
    current_time = get_current_utc_timestamp()
    (subtask_id, task_id) = get_task_id_and_subtask_id(test_id, '2D')
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
        expected_message_type=message.concents.ForceSubtaskResults.TYPE,
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
        expected_message_type=message.concents.ForceSubtaskResultsResponse.TYPE,
        expected_content_type='application/octet-stream',
    )


@count_fails
def test_case_4b_requestor_accepts_subtaks_results(cluster_consts, cluster_url, test_id):
    # Test CASE 4B + 5. Requestor sends ForceSubtaskResultsResponse with SubtaskResultsAccepted
    #  Step 1. Provider sends ForceSubtaskResults
    current_time = get_current_utc_timestamp()
    (task_id, subtask_id) = get_task_id_and_subtask_id(test_id, '4B')
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
        expected_message_type=message.concents.ForceSubtaskResults.TYPE,
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
        expected_message_type=message.concents.ForceSubtaskResultsResponse.TYPE,
        expected_content_type='application/octet-stream',
    )


@count_fails
def test_case_2c_wrong_timestamps(cluster_consts, cluster_url, test_id):
    # Test CASE 2C - Send ForceSubtaskResults with wrong timestamps
    current_time = get_current_utc_timestamp()
    (task_id, subtask_id) = get_task_id_and_subtask_id(test_id, '2C')
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
        expected_message_type=message.concents.ForceSubtaskResultsRejected.TYPE,
        expected_content_type='application/octet-stream',
    )


@count_fails
def test_case_2b_not_enough_funds(cluster_consts, cluster_url, test_id):
    #  Test CASE 2B - Send ForceSubtaskResults with not enough amount of funds on account
    current_time = get_current_utc_timestamp()
    (task_id, subtask_id) = get_task_id_and_subtask_id(test_id, '2B')
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
                        requestor_ethereum_public_key=encode_hex(b'0' * GOLEM_PUBLIC_KEY_LENGTH),
                        provider_ethereum_public_key=encode_hex(b'1' * GOLEM_PUBLIC_KEY_LENGTH),
                        price=0,
                    )
                )
            )
        ),
        headers={
            'Content-Type': 'application/octet-stream',
        },
        expected_status=200,
        expected_message_type=message.concents.ServiceRefused.TYPE,
        expected_content_type='application/octet-stream',
    )


@count_fails
def test_case_2a_send_duplicated_force_subtask_results(cluster_consts, cluster_url, test_id):
    #  Test CASE 2A + 2D + 3 - Send ForceSubtaskResults with same task_id as stored by Concent before
    #  Step 1. Send ForceSubtaskResults first time
    current_time = get_current_utc_timestamp()
    (task_id, subtask_id) = get_task_id_and_subtask_id(test_id, '2A')
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
        expected_message_type=message.concents.ServiceRefused.TYPE,
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
        expected_message_type=message.concents.ForceSubtaskResults.TYPE,
        expected_content_type='application/octet-stream',
    )


if __name__ == '__main__':
    try:
        from concent_api.settings import CONCENT_PUBLIC_KEY
        from core.constants import GOLEM_PUBLIC_KEY_LENGTH
        run_tests(globals())
    except requests.exceptions.ConnectionError as exception:
        print("\nERROR: Failed connect to the server.\n", file = sys.stderr)
        sys.exit(str(exception))
