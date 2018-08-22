#!/usr/bin/env python3
import os
import sys
import time
from datetime import datetime
from threading import Thread
from typing import Optional

import requests
from golem_messages import message
from golem_messages.factories.tasks import ReportComputedTaskFactory
from golem_messages.message.concents import ForceGetTaskResult
from golem_messages.message.concents import ForceReportComputedTask
from golem_messages.message.tasks import AckReportComputedTask
from golem_messages.message.tasks import ReportComputedTask
from golem_messages.message.tasks import TaskToCompute

from api_testing_common import PROVIDER_PRIVATE_KEY
from api_testing_common import REQUESTOR_PRIVATE_KEY
from api_testing_common import api_request
from api_testing_common import assert_condition
from api_testing_common import create_signed_task_to_compute
from api_testing_common import run_tests
from api_testing_common import timestamp_to_isoformat
from common.helpers import get_current_utc_timestamp
from common.helpers import sign_message

"""
Important: to correctly run this tests and create your own tests like this please remember:
1. TestApi should be in all class names
2. test_that should be in all test methods in classes names
"""

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "concent_api.settings")

REPORT_COMPUTED_TASK_SIZE = 10

responses = []  # type: list

NUMBER_OF_TESTING_THREADS = 3  # changing this variable remember to correct number of expected responses
MAXIMUM_WAITING_TIME_FOR_ALL_RESPONSES = 3  # seconds


def get_unique_subtask_id_for_tests() -> str:
    now = datetime.now()
    return str(now.year) + str(now.month) + str(now.day) + str(now.hour) + str(now.minute) + str(now.second) + str(
        now.microsecond)


def call_function_in_treads(
        func,
        number_of_threads: int,
        *args,
        **kwargs,
) -> None:
    for i in range(number_of_threads):
        t = Thread(target=func, args=(*args,), kwargs={**kwargs})
        t.start()


def get_force_report_computed_task(
    task_to_compute: TaskToCompute,
    report_computed_task: ReportComputedTask,
) -> ForceReportComputedTask:
    force_report_computed_task = ForceReportComputedTask()
    force_report_computed_task.report_computed_task = report_computed_task
    force_report_computed_task.report_computed_task.task_to_compute = task_to_compute

    return force_report_computed_task


def get_ack_report_computed_task(
    task_to_compute: TaskToCompute,
    report_computed_task: ReportComputedTask,
) -> AckReportComputedTask:
    ack_report_computed_task = AckReportComputedTask()
    ack_report_computed_task.report_computed_task = report_computed_task
    ack_report_computed_task.report_computed_task.task_to_compute = task_to_compute

    return ack_report_computed_task


def get_force_get_task_result(report_computed_task: ReportComputedTask) -> ForceGetTaskResult:
    force_get_task_result = message.concents.ForceGetTaskResult(
        report_computed_task=report_computed_task,
    )
    return force_get_task_result


class TestApiMultipleRequestsWithExistingSubtask:

    def __init__(self, cluster_consts, cluster_url, test_id):
        self.cluster_consts = cluster_consts
        self.cluster_url = cluster_url
        self.test_id = test_id
        self.task_id = '310'

        """ run all tests in class """
        for x in self.__dir__():
            if 'test_that' in x:
                self.__getattribute__(x)()

    def create_required_messages_with_unique_subtask_id(self):
        self.current_time = get_current_utc_timestamp()
        self.subtask_id = get_unique_subtask_id_for_tests()

        self._signed_task_to_compute = create_signed_task_to_compute(
            timestamp=timestamp_to_isoformat(self.current_time),
            task_id=self.task_id,
            subtask_id=self.subtask_id,
            deadline=(self.current_time + 100),
            price=10000,
        )

        self.report_computed_task = ReportComputedTaskFactory()
        self.report_computed_task.task_to_compute = self._signed_task_to_compute
        sign_message(self.report_computed_task, PROVIDER_PRIVATE_KEY)

    def test_that_multiple_requests_by_one_subtask_will_be_processed_one_by_one_if_subtask_exists_in_database(self):

        """prepare unique objects and variables for test"""
        self.create_required_messages_with_unique_subtask_id()

        """send messages to save subtask in database and change state to REPORTED. Next message ForceGetTaskResult
           requires REPORTED state and this is the simplest way to get it """
        self.send_correct_force_report_computed_task(202)  # Subtask state changed to: FORCING_REPORT
        self.send_correct_ack_report_computed_task(202)  # Subtask state changed to: REPORTED

        """this is test- sending some messages in one time """
        call_function_in_treads(
            func=self.send_correct_force_get_task_result,  # Subtask state changed to: FORCING_RESULT_TRANSFER
            number_of_threads=NUMBER_OF_TESTING_THREADS
        )

        end_time = time.time() + MAXIMUM_WAITING_TIME_FOR_ALL_RESPONSES
        while len(responses) != NUMBER_OF_TESTING_THREADS:
            time.sleep(0.1)
            if time.time() >= end_time:
                break

        print('Responses = ' + str(responses))

        assert_condition(
            actual=responses,
            expected=['AckForceGetTaskResult', 'ServiceRefused', 'ServiceRefused'],
            error_message="Responses should be: 'AckForceGetTaskResult', 'ServiceRefused', 'ServiceRefused'"
        )
        print('Test passed successfully')

    def send_correct_force_report_computed_task(self, expected_status: Optional[int]=None) -> None:
        api_request(
            self.cluster_url,
            'send',
            PROVIDER_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY,
            get_force_report_computed_task(
                task_to_compute=self._signed_task_to_compute,
                report_computed_task=self.report_computed_task
            ),
            headers={
                'Content-Type': 'application/octet-stream',
            },
            expected_status=expected_status,
        )

    def send_correct_ack_report_computed_task(self, expected_status: Optional[int]=None) -> None:
        api_request(
            self.cluster_url,
            'send',
            REQUESTOR_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY,
            get_ack_report_computed_task(
                task_to_compute=self._signed_task_to_compute,
                report_computed_task=self.report_computed_task
            ),
            headers={
                'Content-Type': 'application/octet-stream',
            },
            expected_status=expected_status,
        )

    def send_correct_force_get_task_result(self, expected_status: Optional[int]=None) -> None:
        response = api_request(
            self.cluster_url,
            'send',
            REQUESTOR_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY,
            get_force_get_task_result(
                report_computed_task=self.report_computed_task,
            ),
            headers={
                'Content-Type': 'application/octet-stream',
            },
            expected_status=expected_status,
        )
        responses.append(response.__class__.__name__)


if __name__ == '__main__':
    try:
        from concent_api.settings import CONCENT_PUBLIC_KEY

        run_tests(globals())
    except requests.exceptions.ConnectionError as exception:
        print("\nERROR: Failed connect to the server.\n", file=sys.stderr)
        sys.exit(str(exception))
