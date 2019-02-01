#!/usr/bin/env python3
import os
import sys
import time
from typing import Optional

import requests
from golem_messages import message
from golem_messages.factories.tasks import ReportComputedTaskFactory
from golem_messages.message.concents import ForceGetTaskResult
from golem_messages.message.concents import ForceReportComputedTask
from golem_messages.message.tasks import AckReportComputedTask
from golem_messages.message.tasks import ReportComputedTask

from api_testing_common import PROVIDER_PRIVATE_KEY
from api_testing_common import REQUESTOR_PRIVATE_KEY
from api_testing_common import api_request
from api_testing_common import assert_content_equal
from api_testing_common import calculate_deadline
from api_testing_common import calculate_timestamp
from api_testing_common import call_function_in_threads
from api_testing_common import count_fails
from api_testing_common import create_ack_report_computed_task
from api_testing_common import create_force_subtask_results
from api_testing_common import create_signed_report_computed_task
from api_testing_common import create_signed_task_to_compute
from api_testing_common import run_tests
from api_testing_common import timestamp_to_isoformat
from common.helpers import get_current_utc_timestamp
from common.helpers import sign_message
from common.testing_helpers import generate_ecc_key_pair
from protocol_constants import ProtocolConstants

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "concent_api.settings")

REPORT_COMPUTED_TASK_SIZE = 10

NUMBER_OF_TESTING_THREADS = 3  # changing this variable remember to correct number of expected responses
MAXIMUM_WAITING_TIME_FOR_ALL_RESPONSES = 6  # seconds

responses_global = []  # type: list


def clear_responses() -> None:
    global responses_global
    responses_global.clear()


def get_ack_report_computed_task(report_computed_task: ReportComputedTask) -> AckReportComputedTask:
    return AckReportComputedTask(report_computed_task=report_computed_task)


def get_force_get_task_result(report_computed_task: ReportComputedTask) -> ForceGetTaskResult:
    return message.concents.ForceGetTaskResult(report_computed_task=report_computed_task)


def get_force_report_computed_task(report_computed_task: ReportComputedTask) -> ForceReportComputedTask:
    return ForceReportComputedTask(report_computed_task = report_computed_task)


def create_report_computed_task() -> ReportComputedTask:
    current_time = get_current_utc_timestamp()

    task_to_compute = create_signed_task_to_compute(
        timestamp=timestamp_to_isoformat(current_time),
        deadline=(current_time + 100),
        price=10000,
    )

    report_computed_task = ReportComputedTaskFactory(
        task_to_compute=task_to_compute,
    )
    sign_message(report_computed_task, PROVIDER_PRIVATE_KEY)
    return report_computed_task


def send_correct_force_report_computed_task(
    cluster_url: str,
    report_computed_task: ReportComputedTask,
    expected_status: Optional[int] = None
) -> None:
    response = api_request(
        cluster_url,
        'send',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        get_force_report_computed_task(
            report_computed_task=report_computed_task,
        ),
        expected_status=expected_status,
    )
    responses_global.append(response['error_code'] if isinstance(response, dict) else response)


def send_correct_ack_report_computed_task(
    cluster_url: str,
    report_computed_task: ReportComputedTask,
    expected_status: Optional[int] = None
) -> None:
    api_request(
        cluster_url,
        'send',
        REQUESTOR_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        get_ack_report_computed_task(
            report_computed_task=report_computed_task
        ),
        expected_status=expected_status,
    )


def send_correct_force_get_task_result(
    cluster_url: str,
    report_computed_task: ReportComputedTask,
    expected_status: Optional[int] = None,
) -> None:
    response = api_request(
        cluster_url,
        'send',
        REQUESTOR_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        get_force_get_task_result(
            report_computed_task=report_computed_task,
        ),
        expected_status=expected_status,
    )
    responses_global.append(response.__class__.__name__)


def send_correct_force_subtask_results(
    cluster_url: str,
    report_computed_task: ReportComputedTask,
    current_time: int,
    provider_private_key: bytes,
    requestor_private_key: bytes,
    expected_status: Optional[int] = None,
) -> None:
    response = api_request(
        cluster_url,
        'send',
        provider_private_key,
        CONCENT_PUBLIC_KEY,
        create_force_subtask_results(
            timestamp=timestamp_to_isoformat(current_time),
            ack_report_computed_task=create_ack_report_computed_task(
                timestamp=timestamp_to_isoformat(current_time),
                report_computed_task=report_computed_task,
                requestor_private_key=requestor_private_key
            )
        ),
        expected_status=expected_status,
    )
    responses_global.append(response.__class__.__name__)


@count_fails
def test_case_multiple_requests_concerning_one_subtask_will_be_processed_one_by_one_if_subtask_exists_in_database(
    cluster_consts: str,
    cluster_url: str,
) -> None:
    report_computed_task = create_report_computed_task()

    # send messages to save subtask in database and change state to REPORTED. Next message ForceGetTaskResult
    # requires REPORTED state and this is the simplest way to get it
    send_correct_force_report_computed_task(
        cluster_url=cluster_url,
        report_computed_task=report_computed_task,
        expected_status=202,
    )  # Subtask state changed to: FORCING_REPORT
    send_correct_ack_report_computed_task(
        cluster_url=cluster_url,
        report_computed_task=report_computed_task,
        expected_status=202,
    )  # Subtask state changed to: REPORTED

    clear_responses()
    # this is test- sending some messages in one time
    call_function_in_threads(
        func=send_correct_force_get_task_result,  # Subtask state changed to: FORCING_RESULT_TRANSFER
        number_of_threads=NUMBER_OF_TESTING_THREADS,
        cluster_url=cluster_url,
        report_computed_task=report_computed_task,
    )
    # waiting for responses from all threads
    end_time = time.time() + MAXIMUM_WAITING_TIME_FOR_ALL_RESPONSES
    while len(responses_global) != NUMBER_OF_TESTING_THREADS:
        time.sleep(0.1)
        if time.time() >= end_time:
            break

    expected_responses = ['AckForceGetTaskResult', 'ServiceRefused', 'ServiceRefused']
    assert len(expected_responses) == NUMBER_OF_TESTING_THREADS, 'Did you changed number of testing threads and forgot to change expected_responses?'

    print('Responses = ' + str(responses_global))
    assert_content_equal(actual=responses_global, expected=expected_responses)
    print('Single test passed successfully')


@count_fails
def test_case_multiple_force_get_task_result_concerning_one_subtask_will_be_processed_one_by_one_if_subtask_does_not_exists_in_database(
    cluster_consts: str,
    cluster_url: str,
) -> None:
    report_computed_task = create_report_computed_task()

    clear_responses()
    # this is test- sending some messages in one time
    call_function_in_threads(
        func=send_correct_force_get_task_result,  # Subtask state changed to: FORCING_RESULT_TRANSFER
        number_of_threads=NUMBER_OF_TESTING_THREADS,
        cluster_url=cluster_url,
        report_computed_task=report_computed_task,
    )
    # waiting for responses from all threads
    end_time = time.time() + MAXIMUM_WAITING_TIME_FOR_ALL_RESPONSES
    while len(responses_global) != NUMBER_OF_TESTING_THREADS:
        time.sleep(0.1)
        if time.time() >= end_time:
            break

    expected_responses = ['AckForceGetTaskResult', 'ServiceRefused', 'ServiceRefused']
    assert len(expected_responses) == NUMBER_OF_TESTING_THREADS, 'Did you change number of testing threads and forget to change expected_responses?'

    print('Responses = ' + str(responses_global))
    assert_content_equal(actual=responses_global, expected=expected_responses)
    print('Single test passed successfully')


@count_fails
def test_case_multiple_force_subtask_results_does_not_cause_integrity_errors(
    cluster_consts: ProtocolConstants,
    cluster_url: str
) -> None:
    clear_responses()
    provider_private_key, provider_public_key = generate_ecc_key_pair()
    requestor_private_key, requestor_public_key = generate_ecc_key_pair()
    current_time = get_current_utc_timestamp()
    signed_task_to_compute = create_signed_task_to_compute(
        timestamp=calculate_timestamp(current_time, cluster_consts.concent_messaging_time, cluster_consts.minimum_upload_rate),
        deadline=calculate_deadline(current_time, cluster_consts.concent_messaging_time, cluster_consts.minimum_upload_rate),
        price=1000,
        provider_public_key=provider_public_key,
        provider_private_key=provider_private_key,
        requestor_public_key=requestor_public_key,
        requestor_private_key=requestor_private_key
    )
    report_computed_task = create_signed_report_computed_task(
        task_to_compute=signed_task_to_compute,
        provider_private_key=provider_private_key,
    )

    call_function_in_threads(
        func=send_correct_force_subtask_results,
        number_of_threads=NUMBER_OF_TESTING_THREADS,
        cluster_url=cluster_url,
        report_computed_task=report_computed_task,
        current_time=current_time,
        provider_private_key=provider_private_key,
        requestor_private_key=requestor_private_key,
    )

    end_time = time.time() + MAXIMUM_WAITING_TIME_FOR_ALL_RESPONSES
    while len(responses_global) != NUMBER_OF_TESTING_THREADS:
        time.sleep(0.1)
        if time.time() >= end_time:
            break

    expected_responses = ['ServiceRefused', 'ServiceRefused', 'ServiceRefused']
    assert len(expected_responses) == NUMBER_OF_TESTING_THREADS, 'Did you change number of testing threads and forget to change expected_responses?'

    print('Responses = ' + str(responses_global))
    assert_content_equal(actual=responses_global, expected=expected_responses)
    print('Single test passed successfully')


if __name__ == '__main__':
    try:
        from concent_api.settings import CONCENT_PUBLIC_KEY
        status = run_tests(globals())
        exit(status)
    except requests.exceptions.ConnectionError as exception:
        print("\nERROR: Failed connect to the server.\n", file=sys.stderr)
        sys.exit(exception)
