#!/usr/bin/env python3

import os
import sys

from golem_messages.message.tasks import AckReportComputedTask
from golem_messages.message         import ComputeTaskDef
from golem_messages.message         import ForceReportComputedTask
from golem_messages.message         import TaskToCompute
from golem_messages.message.concents import ForceReportComputedTaskResponse
from golem_messages.message.tasks   import ReportComputedTask

from utils.helpers import get_current_utc_timestamp
from utils.helpers import sign_message
from utils.testing_helpers import generate_ecc_key_pair

from api_testing_common import api_request
from api_testing_common import count_fails
from api_testing_common import create_client_auth_message
from api_testing_common import get_task_id_and_subtask_id
from api_testing_common import run_tests

import requests

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "concent_api.settings")

(PROVIDER_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY)  = generate_ecc_key_pair()
(REQUESTOR_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY) = generate_ecc_key_pair()


def create_signed_task_to_compute(
    task_id,
    subtask_id,
    deadline,
    provider_public_key=None,
    requestor_public_key=None
):
    compute_task_def = ComputeTaskDef()
    compute_task_def['task_id'] = task_id
    compute_task_def['subtask_id'] = subtask_id
    compute_task_def['deadline'] = deadline
    task_to_compute = TaskToCompute(
        provider_public_key=provider_public_key if provider_public_key is not None else PROVIDER_PUBLIC_KEY,
        requestor_public_key=requestor_public_key if requestor_public_key is not None else REQUESTOR_PUBLIC_KEY,
        compute_task_def=compute_task_def,
        price=0,
    )
    sign_message(task_to_compute, REQUESTOR_PRIVATE_KEY)
    return task_to_compute


def force_report_computed_task(task_to_compute):
    report_computed_task = ReportComputedTask()
    report_computed_task.task_to_compute = task_to_compute
    sign_message(report_computed_task, PROVIDER_PRIVATE_KEY)

    force_report_computed_task  = ForceReportComputedTask()
    force_report_computed_task.report_computed_task = report_computed_task
    return force_report_computed_task


def ack_report_computed_task(task_to_compute):
    ack_report_computed_task = AckReportComputedTask()
    ack_report_computed_task.report_computed_task = ReportComputedTask()
    ack_report_computed_task.report_computed_task.task_to_compute = task_to_compute
    return ack_report_computed_task


@count_fails
def test_case_1_provider_forces_report_computed_task_and_gets_accepted(cluster_consts, cluster_url, test_id):
    current_time = get_current_utc_timestamp()
    (task_id, subtask_id) = get_task_id_and_subtask_id(test_id, '1')
    task_to_compute = create_signed_task_to_compute(
        task_id=task_id,
        subtask_id=subtask_id,
        deadline=current_time + (cluster_consts.subtask_verification_time * 2)
    )
    api_request(
        cluster_url,
        'send',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        force_report_computed_task(
            task_to_compute=task_to_compute
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
        expected_message_type=ForceReportComputedTask.TYPE,
        expected_content_type='application/octet-stream',
    )
    api_request(cluster_url,
                'send',
                REQUESTOR_PRIVATE_KEY,
                CONCENT_PUBLIC_KEY,
                ack_report_computed_task(
                    task_to_compute=task_to_compute
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
        expected_message_type=ForceReportComputedTaskResponse.TYPE,
        expected_content_type='application/octet-stream',
    )


if __name__ == '__main__':
    try:
        from concent_api.settings import CONCENT_PUBLIC_KEY

        run_tests(globals())
    except requests.exceptions.ConnectionError as exception:
        print("\nERROR: Failed connect to the server.\n", file = sys.stderr)
        sys.exit(str(exception))
