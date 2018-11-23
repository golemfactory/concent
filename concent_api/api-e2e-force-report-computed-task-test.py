#!/usr/bin/env python3

import os
import sys

from golem_messages.factories.tasks import ReportComputedTaskFactory
from golem_messages.message.tasks import AckReportComputedTask
from golem_messages.message.tasks import TaskToCompute
from golem_messages.message.concents import ForceReportComputedTask
from golem_messages.message.concents import ForceReportComputedTaskResponse

from common.helpers import get_current_utc_timestamp
from common.helpers import sign_message

from api_testing_common import api_request
from api_testing_common import count_fails
from api_testing_common import create_client_auth_message
from api_testing_common import create_signed_task_to_compute
from api_testing_common import PROVIDER_PRIVATE_KEY
from api_testing_common import PROVIDER_PUBLIC_KEY
from api_testing_common import REQUESTOR_PRIVATE_KEY
from api_testing_common import REQUESTOR_PUBLIC_KEY
from api_testing_common import run_tests
from protocol_constants import ProtocolConstants

import requests

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "concent_api.settings")


def force_report_computed_task(task_to_compute: TaskToCompute) -> ForceReportComputedTask:
    report_computed_task = ReportComputedTaskFactory()
    report_computed_task.task_to_compute = task_to_compute
    sign_message(report_computed_task, PROVIDER_PRIVATE_KEY)

    force_report_computed_task  = ForceReportComputedTask()
    force_report_computed_task.report_computed_task = report_computed_task
    return force_report_computed_task


def ack_report_computed_task(task_to_compute: TaskToCompute) -> AckReportComputedTask:
    ack_report_computed_task = AckReportComputedTask()
    ack_report_computed_task.report_computed_task = ReportComputedTaskFactory()
    ack_report_computed_task.report_computed_task.task_to_compute = task_to_compute
    sign_message(ack_report_computed_task.report_computed_task, PROVIDER_PRIVATE_KEY)
    return ack_report_computed_task


@count_fails
def test_case_1_provider_forces_report_computed_task_and_gets_accepted(
    cluster_consts: ProtocolConstants,
    cluster_url: str,

) -> None:
    current_time = get_current_utc_timestamp()
    task_to_compute = create_signed_task_to_compute(
        deadline=current_time + 1
    )
    api_request(
        cluster_url,
        'send',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        force_report_computed_task(
            task_to_compute=task_to_compute
        ),
        expected_status=202,
    )
    api_request(
        cluster_url,
        'receive',
        REQUESTOR_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        create_client_auth_message(REQUESTOR_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY, CONCENT_PUBLIC_KEY),
        expected_status=200,
        expected_message_type=ForceReportComputedTask,
        expected_content_type='application/octet-stream',
    )
    api_request(
        cluster_url,
        'send',
        REQUESTOR_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        ack_report_computed_task(
            task_to_compute=task_to_compute
        ),
        expected_status=202,
    )
    api_request(
        cluster_url,
        'receive',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        create_client_auth_message(PROVIDER_PRIVATE_KEY, PROVIDER_PUBLIC_KEY, CONCENT_PUBLIC_KEY),
        expected_status=200,
        expected_message_type=ForceReportComputedTaskResponse,
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
