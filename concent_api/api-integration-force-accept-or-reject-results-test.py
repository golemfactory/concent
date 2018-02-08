#!/usr/bin/env python3

import os
import sys
import datetime
import random
import time
from base64                 import b64encode

from golem_messages         import message

from utils.testing_helpers  import generate_ecc_key_pair

from api_testing_helpers    import api_request

import requests

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "concent_api.settings")

(PROVIDER_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY)  = generate_ecc_key_pair()
(REQUESTOR_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY) = generate_ecc_key_pair()


def parse_command_line(command_line):
    if len(command_line) <= 1:
        sys.exit('Not enough arguments')

    if len(command_line) >= 3:
        sys.exit('Too many arguments')

    cluster_url = command_line[1]
    return cluster_url


def force_subtask_results(ack_report_computed_task = None):
    return message.concents.ForceSubtaskResults(
        ack_report_computed_task = ack_report_computed_task,
    )


def ack_report_computed_task(subtask_id = None, task_to_compute = None):
    return message.concents.AckReportComputedTask(
        task_to_compute = task_to_compute,
        subtask_id      = subtask_id,
    )


def task_to_compute(compute_task_def = None):
    return message.tasks.TaskToCompute(
        compute_task_def = compute_task_def,
    )


def compute_task_def(
    task_id     = None,
    subtask_id  = None,
    deadline    = None,
):
    compute_task_def = message.tasks.ComputeTaskDef()
    compute_task_def['task_id']     = task_id
    compute_task_def['deadline']    = deadline
    compute_task_def['subtask_id']  = subtask_id

    return compute_task_def


def force_subtask_results_response(subtask_results_accepted = None, subtask_results_rejected = None):
    return message.concents.ForceSubtaskResultsResponse(
        subtask_results_accepted = subtask_results_accepted,
        subtask_results_rejected = subtask_results_rejected,
    )


def subtask_results_accepted(subtask_id = None, payment_ts = None):
    return message.tasks.SubtaskResultsAccepted(
        subtask_id = subtask_id,
        payment_ts = payment_ts,
    )


def subtask_results_rejected(reason = None, report_computed_task = None):
    return message.tasks.SubtaskResultsRejected(
        reason                  = reason,
        report_computed_task    = report_computed_task,
    )


def report_computed_task(subtask_id = None, task_to_compute = None):
    return message.tasks.ReportComputedTask(
        subtask_id      = subtask_id,
        task_to_compute = task_to_compute
    )


def main():
    cluster_url     = parse_command_line(sys.argv)
    task_id         = random.randrange(1, 100000)
    current_time    = int(datetime.datetime.now().timestamp())

    #  Test CASE 2A + 2D + 3 - Send ForceSubtaskResults with same task_id as stored by Concent before
    #  Step 1. Send ForceSubtaskResults first time
    message_force_subtask_results = force_subtask_results(
        ack_report_computed_task(
            subtask_id = str(task_id) + '2A',
            task_to_compute = task_to_compute(
                compute_task_def = compute_task_def(
                    task_id     = str(task_id) + '2A',
                    subtask_id  = str(task_id) + '2A',
                    deadline    = current_time + 5,
                )
            )
        )
    )
    time.sleep(2)
    api_request(
        cluster_url,
        'send',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        message_force_subtask_results,
        headers = {
            'Content-Type':                     'application/octet-stream',
            'concent-client-public-key':        b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            'concent-other-party-public-key':   b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            'temporary-account-funds':          'True'
        }
    )

    #  Step 2. Send ForceSubtaskResults second time with same task_id
    api_request(
        cluster_url,
        'send',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        force_subtask_results(
            ack_report_computed_task(
                subtask_id = str(task_id) + '2A',
                task_to_compute = task_to_compute(
                    compute_task_def = compute_task_def(
                        task_id     = str(task_id) + '2A',
                        subtask_id  = str(task_id) + '2A',
                        deadline    = current_time + 10,
                    )
                )
            )
        ),
        headers = {
            'Content-Type':                     'application/octet-stream',
            'concent-client-public-key':        b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            'concent-other-party-public-key':   b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            'temporary-account-funds':          'True'
        }
    )

    #  Step 3. Requestor wants to receive ForceSubtaskResults from Concent
    api_request(
        cluster_url,
        'receive',
        REQUESTOR_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        headers = {
            'Content-Type': 'application/octet-stream',
            'concent-client-public-key': b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
        }
    )

    #  Test CASE 2B - Send ForceSubtaskResults with not enough amount of funds on account
    api_request(
        cluster_url,
        'send',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        force_subtask_results(
            ack_report_computed_task(
                subtask_id = str(task_id),
                task_to_compute = task_to_compute(
                    compute_task_def = compute_task_def(
                        task_id     = str(task_id),
                        subtask_id  = str(task_id),
                        deadline    = current_time + 10,
                    )
                )
            )
        ),
        headers = {
            'Content-Type':                     'application/octet-stream',
            'concent-client-public-key':        b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            'concent-other-party-public-key':   b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            'temporary-account-funds':          ''
        }
    )

    #  Test CASE 2C - Send ForceSubtaskResults with wrong timestamps
    force_subtask_result_too_old = force_subtask_results(
        ack_report_computed_task(
            subtask_id = str(task_id) + '2C',
            task_to_compute = task_to_compute(
                compute_task_def = compute_task_def(
                    task_id     = str(task_id) + '2C',
                    subtask_id  = str(task_id) + '2C',
                    deadline    = current_time + 10,
                )
            )
        )
    )
    time.sleep(9)
    api_request(
        cluster_url,
        'send',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        force_subtask_result_too_old,
        headers = {
            'Content-Type':                     'application/octet-stream',
            'concent-client-public-key':        b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            'concent-other-party-public-key':   b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            'temporary-account-funds':          'True'
        }
    )

    # Test CASE 4B + 5. Requestor sends ForceSubtaskResultsResponse with SubtaskResultsAccepted
    message_force_subtask_results_response = force_subtask_results_response(
        subtask_results_accepted = subtask_results_accepted(
            subtask_id = str(task_id) + '2A',
            payment_ts = current_time + 1,
        )
    )
    api_request(
        cluster_url,
        'send',
        REQUESTOR_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        message_force_subtask_results_response,
        headers = {
            'Content-Type':                 'application/octet-stream',
            'concent-client-public-key':    b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            'temporary-account-funds':      'True'
        }
    )

    api_request(
        cluster_url,
        'receive',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        headers = {
            'Content-Type': 'application/octet-stream',
            'concent-client-public-key': b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
        }
    )

    # Test CASE 2D + 3 + 4B + 5. Requestor sends ForceSubtaskResultsResponse with SubtaskResultsRejected
    message_force_subtask_results = force_subtask_results(
        ack_report_computed_task(
            subtask_id = str(task_id) + '2D',
            task_to_compute = task_to_compute(
                compute_task_def = compute_task_def(
                    task_id     = str(task_id) + '2D',
                    subtask_id  = str(task_id) + '2D',
                    deadline    = current_time + 5,
                )
            )
        )
    )
    time.sleep(2)
    api_request(
        cluster_url,
        'send',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        message_force_subtask_results,
        headers = {
            'Content-Type':                     'application/octet-stream',
            'concent-client-public-key':        b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            'concent-other-party-public-key':   b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            'temporary-account-funds':          'True'
        }
    )

    api_request(
        cluster_url,
        'receive',
        REQUESTOR_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        headers = {
            'Content-Type': 'application/octet-stream',
            'concent-client-public-key': b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
        }
    )

    api_request(
        cluster_url,
        'send',
        REQUESTOR_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        force_subtask_results_response(
            subtask_results_rejected = subtask_results_rejected(
                report_computed_task = report_computed_task(
                    subtask_id      = str(task_id) + '2D',
                    task_to_compute = task_to_compute(
                        compute_task_def = compute_task_def(
                            deadline    = current_time + 1,
                            task_id     = str(task_id) + '2D',
                            subtask_id  = str(task_id) + '2D',
                        )
                    )
                )
            )
        ),
        headers = {
            'Content-Type':                 'application/octet-stream',
            'concent-client-public-key':    b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            'temporary-account-funds':      'True'
        }
    )

    api_request(
        cluster_url,
        'receive',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        headers = {
            'Content-Type':                     'application/octet-stream',
            'concent-client-public-key':        b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            'concent-other-party-public-key':   b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
        }
    )


if __name__ == '__main__':
    try:
        from concent_api.settings import CONCENT_PUBLIC_KEY
        main()
    except requests.exceptions.ConnectionError as exception:
        print("\nERROR: Failed connect to the server.\n", file = sys.stderr)
        sys.exit(str(exception))
