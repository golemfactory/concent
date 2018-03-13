#!/usr/bin/env python3

import os
import random
import requests
import sys
import time
from base64                 import b64encode
from freezegun              import freeze_time

from golem_messages         import message

from utils.helpers          import get_current_utc_timestamp
from utils.testing_helpers  import generate_ecc_key_pair

from api_testing_common     import api_request, parse_command_line, get_protocol_constants, print_protocol_constants
from api_testing_common     import timestamp_to_isoformat

HOUR = 3600
TIME_GUARD = 10

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "concent_api.settings")

(PROVIDER_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY)  = generate_ecc_key_pair()
(REQUESTOR_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY) = generate_ecc_key_pair()


def force_subtask_results(timestamp = None, ack_report_computed_task = None):
    with freeze_time(timestamp):
        return message.concents.ForceSubtaskResults(
            ack_report_computed_task = ack_report_computed_task,
        )


def ack_report_computed_task(timestamp = None, subtask_id = None, task_to_compute = None):
    with freeze_time(timestamp):
        return message.concents.AckReportComputedTask(
            task_to_compute = task_to_compute,
            subtask_id      = subtask_id,
        )


def task_to_compute(timestamp = None, compute_task_def = None):
    with freeze_time(timestamp):
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


def force_subtask_results_response(timestamp = None, subtask_results_accepted = None, subtask_results_rejected = None):
    with freeze_time(timestamp):
        return message.concents.ForceSubtaskResultsResponse(
            subtask_results_accepted = subtask_results_accepted,
            subtask_results_rejected = subtask_results_rejected,
        )


def subtask_results_accepted(timestamp = None, task_to_compute = None, payment_ts = None):
    with freeze_time(timestamp):
        return message.tasks.SubtaskResultsAccepted(
            task_to_compute = task_to_compute,
            payment_ts      = payment_ts,
        )


def subtask_results_rejected(timestamp = None, reason = None, report_computed_task = None):
    with freeze_time(timestamp):
        return message.tasks.SubtaskResultsRejected(
            reason                  = reason,
            report_computed_task    = report_computed_task,
        )


def report_computed_task(timestamp = None, subtask_id = None, task_to_compute = None):
    with freeze_time(timestamp):
        return message.tasks.ReportComputedTask(
            subtask_id      = subtask_id,
            task_to_compute = task_to_compute
        )


def create_task(task_to_compute_timestamp, task_id, compute_task_def_deadline):
    return task_to_compute(
            timestamp           = task_to_compute_timestamp,
            compute_task_def    = compute_task_def(
                    task_id     = task_id,
                    subtask_id  = "subtask_" + task_id,
                    deadline    = compute_task_def_deadline,
        )
    )


def main():
    cluster_url     = parse_command_line(sys.argv)
    task_id         = str(random.randrange(1, 100000))
    current_time    = get_current_utc_timestamp()

    cluster_consts = get_protocol_constants(cluster_url)
    print_protocol_constants(cluster_consts)

    current_timestamp                   = timestamp_to_isoformat(current_time)
    ack_report_computed_task_timestamp  = timestamp_to_isoformat(current_time - cluster_consts.subtask_verification_time - TIME_GUARD)  # now - SVT - TIME_GUARD (~4:00:10)
    report_computed_task_timestamp      = ack_report_computed_task_timestamp   # now - SVT - TIME_GUARD (~4:00:10)
    task_to_compute_timestamp           = timestamp_to_isoformat(current_time - cluster_consts.subtask_verification_time - 2 * TIME_GUARD)  # now - SVT - 2* TIME_GUARD (~4:00:20)
    compute_task_def_deadline           = current_time + HOUR

    #  Test CASE 2A + 2D + 3 - Send ForceSubtaskResults with same task_id as stored by Concent before
    #  Step 1. Send ForceSubtaskResults first time
    task_1 = create_task(task_to_compute_timestamp, task_id + "2A", compute_task_def_deadline)

    api_request(
        cluster_url,
        'send',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        force_subtask_results(
                timestamp                   = current_timestamp,  # current_time
                ack_report_computed_task    = ack_report_computed_task(
                        timestamp           = ack_report_computed_task_timestamp,  # current_time - 4:00:10
                        subtask_id          = task_id + '2A',
                        task_to_compute     = task_1
                )
        ),
        headers = {
            'Content-Type'                  : 'application/octet-stream',
            'concent-client-public-key'     : b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            'concent-other-party-public-key': b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            'temporary-account-funds'       : 'True'
        },
        expected_status = 202
    )

    time.sleep(1)
    #  Step 2. Send ForceSubtaskResults second time with same task_id
    api_request(
        cluster_url,
        'send',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        force_subtask_results(
                timestamp                   = current_timestamp,  # current_time
                ack_report_computed_task    = ack_report_computed_task(
                        timestamp           = ack_report_computed_task_timestamp,  # current_time - 4:00:10
                        subtask_id          = task_id + '2A',
                        task_to_compute     = task_1
                )
        ),
        headers = {
            'Content-Type'                  : 'application/octet-stream',
            'concent-client-public-key'     : b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            'concent-other-party-public-key': b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            'temporary-account-funds'       : 'True'
        },
        expected_status = 200
    )

    #  Step 3. Requestor wants to receive ForceSubtaskResults from Concent
    api_request(
        cluster_url,
        'receive',
        REQUESTOR_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        headers = {
            'Content-Type'             : 'application/octet-stream',
            'concent-client-public-key': b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
        },
        expected_status = 200
    )


    #  Test CASE 2B - Send ForceSubtaskResults with not enough amount of funds on account
    api_request(
        cluster_url,
        'send',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        force_subtask_results(
            timestamp = current_timestamp,  # current_time
            ack_report_computed_task    = ack_report_computed_task(
                    timestamp           = ack_report_computed_task_timestamp,  # current_time - 4:00:10
                    subtask_id          = task_id,
                    task_to_compute     = create_task(task_to_compute_timestamp, task_id, compute_task_def_deadline)
            )
        ),
        headers = {
            'Content-Type'                  : 'application/octet-stream',
            'concent-client-public-key'     : b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            'concent-other-party-public-key': b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            'temporary-account-funds'       :          ''
        },
        expected_status = 200
    )

    #  Test CASE 2C - Send ForceSubtaskResults with wrong timestamps
    api_request(
        cluster_url,
        'send',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        force_subtask_results(
            timestamp                   = timestamp_to_isoformat(current_time),
            ack_report_computed_task    = ack_report_computed_task(
                timestamp               = timestamp_to_isoformat(current_time - 2 * cluster_consts.subtask_verification_time - TIME_GUARD),  # current_time - 08:00:10
                subtask_id              = task_id + '2C',
                task_to_compute         = create_task(timestamp_to_isoformat(current_time - 28802), task_id + '2C', current_time)
            )
        ),
        headers = {
            'Content-Type'                  : 'application/octet-stream',
            'concent-client-public-key'     : b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            'concent-other-party-public-key': b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            'temporary-account-funds'       : 'True'
        },
        expected_status = 200
    )

    # Test CASE 4B + 5. Requestor sends ForceSubtaskResultsResponse with SubtaskResultsAccepted
    api_request(
        cluster_url,
        'send',
        REQUESTOR_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        force_subtask_results_response(
            timestamp = current_timestamp,
                subtask_results_accepted    = subtask_results_accepted(
                        timestamp           = current_timestamp,
                        task_to_compute     = task_1,
                        payment_ts          = current_time + 1,
                )
        ),
        headers = {
            'Content-Type'             : 'application/octet-stream',
            'concent-client-public-key': b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            'temporary-account-funds'  : 'True'
        },
        expected_status = 202
    )

    api_request(
        cluster_url,
        'receive',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        headers = {
            'Content-Type'             : 'application/octet-stream',
            'concent-client-public-key': b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
        },
        expected_status = 200
    )

    # Test CASE 2D + 3 + 4B + 5. Requestor sends ForceSubtaskResultsResponse with SubtaskResultsRejected
    task_2 = create_task(task_to_compute_timestamp, task_id + '2D', compute_task_def_deadline)

    api_request(
        cluster_url,
        'send',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        force_subtask_results(
                timestamp                   = current_timestamp,
                ack_report_computed_task    = ack_report_computed_task(
                        timestamp           = ack_report_computed_task_timestamp,  # current_time - 04:00:10
                        subtask_id          = task_id + '2D',
                        task_to_compute     = task_2
                )
        ),
        headers = {
            'Content-Type'                  : 'application/octet-stream',
            'concent-client-public-key'     : b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            'concent-other-party-public-key': b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            'temporary-account-funds'       : 'True'
        },
        expected_status = 202
    )

    api_request(
        cluster_url,
        'receive',
        REQUESTOR_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        headers = {
            'Content-Type'             : 'application/octet-stream',
            'concent-client-public-key': b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
        },
        expected_status = 200
    )

    api_request(
        cluster_url,
        'send',
        REQUESTOR_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        force_subtask_results_response(
                timestamp                       = current_timestamp,
                subtask_results_rejected        = subtask_results_rejected(
                        timestamp               = current_timestamp,
                        report_computed_task    = report_computed_task(
                                timestamp       = report_computed_task_timestamp,  # current_time - 04:00:10
                                subtask_id      = task_id + '2D',
                                task_to_compute = task_2
                        )
                )
        ),
        headers = {
            'Content-Type'             : 'application/octet-stream',
            'concent-client-public-key': b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            'temporary-account-funds'  : 'True'
        },
        expected_status = 202
    )

    api_request(
        cluster_url,
        'receive',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        headers = {
            'Content-Type'                  : 'application/octet-stream',
            'concent-client-public-key'     : b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            'concent-other-party-public-key': b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
        },
        expected_status = 200
    )


if __name__ == '__main__':
    try:
        from concent_api.settings import CONCENT_PUBLIC_KEY
        main()
    except requests.exceptions.ConnectionError as exception:
        print("\nERROR: Failed connect to the server.\n", file = sys.stderr)
        sys.exit(str(exception))
