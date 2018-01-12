#!/usr/bin/env python3

import os
import sys
import datetime
import random

from base64                         import b64encode

from golem_messages.message         import AckReportComputedTask
from golem_messages.message         import CannotComputeTask
from golem_messages.message         import ComputeTaskDef
from golem_messages.message         import ForceReportComputedTask
from golem_messages.message         import TaskToCompute
from golem_messages.message         import RejectReportComputedTask
from golem_messages.shortcuts       import dump
from golem_messages.shortcuts       import load

from utils.testing_helpers          import generate_ecc_key_pair

from api_testing_helpers            import api_request

import requests

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "concent_api.settings")

(PROVIDER_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY)  = generate_ecc_key_pair()
(REQUESTOR_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY) = generate_ecc_key_pair()


def create_data(message_type, task_id):
    assert task_id >= 0
    assert isinstance(task_id, int)

    current_time = int(datetime.datetime.now().timestamp())

    compute_task_def = ComputeTaskDef()
    compute_task_def['task_id']     = task_id
    compute_task_def['deadline']    = current_time + 6000
    task_to_compute = TaskToCompute(
        timestamp = current_time,
        compute_task_def = compute_task_def
    )

    serialized_task_to_compute      = dump(task_to_compute,             REQUESTOR_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY)
    deserialized_task_to_compute    = load(serialized_task_to_compute,  PROVIDER_PRIVATE_KEY,   REQUESTOR_PUBLIC_KEY, check_time = False)

    if message_type == 'ForceReportComputedTask':
        force_report_computed_task = ForceReportComputedTask(
            timestamp = current_time,
            task_to_compute = deserialized_task_to_compute
        )

        return force_report_computed_task

    elif message_type == 'AckReportComputedTask':
        ack_report_computed_task = AckReportComputedTask(
            timestamp = current_time,
            task_to_compute = deserialized_task_to_compute
        )

        return ack_report_computed_task

    else:
        assert False, 'Invalid message type'

    return None


def create_reject_data(task_id):
    assert task_id >= 0
    assert isinstance(task_id, int)

    cannot_compute_task = CannotComputeTask()
    cannot_compute_task.task_to_compute = TaskToCompute()
    cannot_compute_task.task_to_compute.compute_task_def = ComputeTaskDef()
    cannot_compute_task.task_to_compute.compute_task_def['task_id'] = task_id
    cannot_compute_task.reason = CannotComputeTask.REASON.WrongKey

    serialized_cannot_compute_task      = dump(cannot_compute_task,             PROVIDER_PRIVATE_KEY,   REQUESTOR_PUBLIC_KEY)
    deserialized_cannot_compute_task    = load(serialized_cannot_compute_task,  REQUESTOR_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY, check_time=False)

    reject_report_computed_task = RejectReportComputedTask()
    reject_report_computed_task.cannot_compute_task = deserialized_cannot_compute_task
    reject_report_computed_task.reason              = RejectReportComputedTask.Reason.TASK_TIME_LIMIT_EXCEEDED
    reject_report_computed_task.task_to_compute     = None
    reject_report_computed_task.task_failure        = None

    return reject_report_computed_task


def parse_command_line(command_line):
    if len(command_line) <= 1:
        sys.exit('Not enough arguments')

    if len(command_line) >= 3:
        sys.exit('Too many arguments')

    cluster_url = command_line[1]
    return cluster_url


def main():
    cluster_url = parse_command_line(sys.argv)
    task_id     = random.randrange(1, 100000)
    api_request(
        cluster_url,
        'send',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        create_data('ForceReportComputedTask', task_id), {
            'Content-Type': 'application/octet-stream',
            'concent-client-public-key':    b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            'concent-requestor-public-key': b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii')
        },
    )

    api_request(
        cluster_url,
        'receive',
        REQUESTOR_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        headers = {
            'Content-Type': 'application/octet-stream',
            'concent-client-public-key':    b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
        }
    )

    api_request(
        cluster_url,
        'send',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        create_data('AckReportComputedTask', task_id), {
            'Content-Type': 'application/octet-stream',
            'concent-client-public-key':    b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            'concent-requestor-public-key': b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii')
        }
    )

    api_request(
        cluster_url,
        'receive',
        REQUESTOR_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        headers = {
            'Content-Type': 'application/octet-stream',
            'concent-client-public-key':    b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
        }
    )

    api_request(
        cluster_url,
        'send',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        create_data('ForceReportComputedTask', task_id + 1), {
            'Content-Type': 'application/octet-stream',
            'concent-client-public-key':    b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            'concent-requestor-public-key': b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii')
        }
    )

    api_request(
        cluster_url,
        'receive',
        REQUESTOR_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        headers = {
            'Content-Type': 'application/octet-stream',
            'concent-client-public-key':    b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
        }
    )

    api_request(
        cluster_url,
        'send',
        REQUESTOR_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        create_reject_data(task_id + 1), {
            'Content-Type': 'application/octet-stream',
            'concent-client-public-key':    b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            'concent-requestor-public-key': b64encode(PROVIDER_PUBLIC_KEY).decode('ascii')
        }
    )

    api_request(
        cluster_url,
        'receive',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        headers = {
            'Content-Type': 'application/octet-stream',
            'concent-client-public-key':    b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            'concent-requestor-public-key': b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
        }
    )


if __name__ == '__main__':
    try:
        from concent_api.settings import CONCENT_PUBLIC_KEY
        main()
    except requests.exceptions.ConnectionError as exception:
        print("\nERROR: Failed connect to the server.\n", file = sys.stderr)
        sys.exit(str(exception))
