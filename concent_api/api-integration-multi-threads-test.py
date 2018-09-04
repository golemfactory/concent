# !/usr/bin/env python3
import os
import sys
import time
from threading import Thread
from typing import Optional
import requests

from golem_messages import message
from golem_messages.factories.tasks import ReportComputedTaskFactory
from golem_messages.message import Message
from golem_messages.message.concents import ForceGetTaskResult
from golem_messages.message.concents import ForceReportComputedTask
from golem_messages.message.tasks import AckReportComputedTask
from golem_messages.message.tasks import ReportComputedTask

from api_testing_common import compare_lists_regardless_of_order
from api_testing_common import count_fails
from api_testing_common import PROVIDER_PRIVATE_KEY
from api_testing_common import REQUESTOR_PRIVATE_KEY
from api_testing_common import api_request
from api_testing_common import create_signed_task_to_compute
from api_testing_common import run_tests
from api_testing_common import timestamp_to_isoformat
from common.helpers import get_current_utc_timestamp
from common.helpers import sign_message

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "concent_api.settings")

REPORT_COMPUTED_TASK_SIZE = 10

NUMBER_OF_TESTING_THREADS = 3  # changing this variable remember to correct number of expected responses
MAXIMUM_WAITING_TIME_FOR_ALL_RESPONSES = 3  # seconds

responses_global = []  # type: list


def clear_responses():
    global responses_global
    responses_global.clear()


def call_function_in_treads(
    func,
    number_of_threads: int,
    cluster_url: str,
    golem_message: Message,
) -> None:
    for i in range(number_of_threads):
        thread = Thread(target=func, args=(cluster_url, golem_message,))
        thread.start()


def create_ack_report_computed_task(report_computed_task: ReportComputedTask) -> AckReportComputedTask:
    return AckReportComputedTask(report_computed_task=report_computed_task)


def create_force_get_task_result(report_computed_task: ReportComputedTask) -> ForceGetTaskResult:
    return message.concents.ForceGetTaskResult(report_computed_task=report_computed_task)


def create_force_report_computed_task(report_computed_task: ReportComputedTask) -> ForceReportComputedTask:
    return ForceReportComputedTask(report_computed_task = report_computed_task)


def create_report_computed_task(
    task_id: str,
    subtask_id: str
) -> ReportComputedTask:
    current_time = get_current_utc_timestamp()

    task_to_compute = create_signed_task_to_compute(
        timestamp=timestamp_to_isoformat(current_time),
        task_id=task_id,
        subtask_id=subtask_id,
        deadline=(current_time + CONCENT_MESSAGING_TIME),
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
        create_force_report_computed_task(
            report_computed_task=report_computed_task,
        ),
        headers={
            'Content-Type': 'application/octet-stream',
        },
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
        create_ack_report_computed_task(
            report_computed_task=report_computed_task
        ),
        headers={
            'Content-Type': 'application/octet-stream',
        },
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
        create_force_get_task_result(
            report_computed_task=report_computed_task,
        ),
        headers={
            'Content-Type': 'application/octet-stream',
        },
        expected_status=expected_status,
    )
    responses_global.append(response.__class__.__name__)


@count_fails
def test_case_multiple_requests_concerning_one_subtask_will_be_processed_one_by_one_if_subtask_exists_in_database(
    cluster_consts: str,
    cluster_url: str,
    task_id: str,
    subtask_id: str
) -> None:
    report_computed_task = create_report_computed_task(task_id=task_id, subtask_id=subtask_id)

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
    call_function_in_treads(
        func=send_correct_force_get_task_result,  # Subtask state changed to: FORCING_RESULT_TRANSFER
        number_of_threads=NUMBER_OF_TESTING_THREADS,
        cluster_url=cluster_url,
        golem_message=report_computed_task,
    )
    # waiting for responses from all threads
    end_time = time.time() + MAXIMUM_WAITING_TIME_FOR_ALL_RESPONSES
    while len(responses_global) != NUMBER_OF_TESTING_THREADS:
        time.sleep(0.1)
        if time.time() >= end_time:
            break

    expected_responses = ['AckForceGetTaskResult', 'ServiceRefused', 'ServiceRefused']
    assert len(expected_responses) == NUMBER_OF_TESTING_THREADS,'Did you changed number of testing threads and forgot to change expected_responses?'

    print('Responses = ' + str(responses_global))
    error_message = f"Responses should be: {expected_responses}."
    assert compare_lists_regardless_of_order(actual=responses_global, expected=expected_responses), error_message
    print('Single test passed successfully')


if __name__ == '__main__':
    try:
        from concent_api.settings import CONCENT_PUBLIC_KEY, CONCENT_MESSAGING_TIME

        run_tests(globals())
    except requests.exceptions.ConnectionError as exception:
        print("\nERROR: Failed connect to the server.\n", file=sys.stderr)
        sys.exit(exception)
