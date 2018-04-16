#!/usr/bin/env python3

import os
import sys
import random
import time
from freezegun              import freeze_time

from golem_messages         import message

from utils.helpers import get_current_utc_timestamp
from utils.helpers import sign_message
from utils.testing_helpers import generate_ecc_key_pair

from api_testing_common import api_request
from api_testing_common import create_client_auth_message
from api_testing_common import get_task_id_and_subtask_id
from api_testing_common import parse_command_line
from api_testing_common import timestamp_to_isoformat

from protocol_constants import get_protocol_constants

import requests

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "concent_api.settings")

(PROVIDER_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY)  = generate_ecc_key_pair()
(REQUESTOR_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY) = generate_ecc_key_pair()


def force_subtask_results(timestamp = None, ack_report_computed_task = None):
    with freeze_time(timestamp):
        return message.concents.ForceSubtaskResults(
            ack_report_computed_task = ack_report_computed_task,
        )


def ack_report_computed_task(timestamp = None, report_computed_task = None):
    with freeze_time(timestamp):
        return message.AckReportComputedTask(
            report_computed_task=report_computed_task,
        )


def task_to_compute(timestamp = None, compute_task_def = None, provider_public_key = None, requestor_public_key = None):
    with freeze_time(timestamp):
        task_to_compute = message.tasks.TaskToCompute(
            provider_public_key = provider_public_key if provider_public_key is not None else PROVIDER_PUBLIC_KEY,
            requestor_public_key = requestor_public_key if requestor_public_key is not None else REQUESTOR_PUBLIC_KEY,
            compute_task_def = compute_task_def,
            price=0,
        )
        sign_message(task_to_compute, REQUESTOR_PRIVATE_KEY)
        return task_to_compute


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


def subtask_results_accepted(timestamp = None, payment_ts = None, task_to_compute = None):
    with freeze_time(timestamp):
        return message.tasks.SubtaskResultsAccepted(
            payment_ts = payment_ts,
            task_to_compute = task_to_compute,
        )


def subtask_results_rejected(timestamp = None, reason = None, report_computed_task = None):
    with freeze_time(timestamp):
        return message.tasks.SubtaskResultsRejected(
            reason                  = reason,
            report_computed_task    = report_computed_task,
        )


def report_computed_task(timestamp = None, task_to_compute = None):
    with freeze_time(timestamp):
        return message.tasks.ReportComputedTask(
            task_to_compute = task_to_compute
        )


def main():
    cluster_url     = parse_command_line(sys.argv)
    cluster_consts  = get_protocol_constants(cluster_url)

    test_id = str(random.randrange(1, 100000))
    test_case_2a_send_duplicated_force_subtask_results(cluster_consts, cluster_url, test_id)

    test_case_2b_not_enough_funds(cluster_consts, cluster_url, test_id)

    test_case_2c_wrong_timestamps(cluster_consts, cluster_url, test_id)

    test_case_4b_requestor_accepts_subtaks_results(cluster_consts, cluster_url, test_id)

    test_case_2d_requestor_rejects_subtask_results(cluster_consts, cluster_url, test_id)


def test_case_2d_requestor_rejects_subtask_results(cluster_consts, cluster_url, id):
    # Test CASE 2D + 3 + 4B + 5. Requestor sends ForceSubtaskResultsResponse with SubtaskResultsRejected
    current_time = get_current_utc_timestamp()
    (subtask_id, task_id) = get_task_id_and_subtask_id(id, '2D')
    api_request(
        cluster_url,
        'send',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        force_subtask_results(
            timestamp=timestamp_to_isoformat(current_time),
            ack_report_computed_task=ack_report_computed_task(
                timestamp=timestamp_to_isoformat(current_time - (cluster_consts.subtask_verification_time)),
                report_computed_task=report_computed_task(
                    task_to_compute=task_to_compute(
                        timestamp=timestamp_to_isoformat(current_time - cluster_consts.subtask_verification_time * 1.5),
                        compute_task_def=compute_task_def(
                            task_id=task_id,
                            subtask_id=subtask_id,
                            deadline=current_time - (cluster_consts.subtask_verification_time),
                        )
                    )
                )
            )
        ),
        headers={
            'Content-Type': 'application/octet-stream',
            'temporary-account-funds': 'True'
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
                    timestamp=timestamp_to_isoformat(current_time - (cluster_consts.subtask_verification_time)),
                    task_to_compute=task_to_compute(
                        timestamp=timestamp_to_isoformat(current_time - cluster_consts.subtask_verification_time * 1.5),
                        compute_task_def=compute_task_def(
                            deadline=current_time - (cluster_consts.subtask_verification_time),
                            task_id=task_id,
                            subtask_id=subtask_id,
                        )
                    )
                )
            )
        ),
        headers={
            'Content-Type': 'application/octet-stream',
            'temporary-account-funds': 'True'
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


def test_case_4b_requestor_accepts_subtaks_results(cluster_consts, cluster_url, test_id):
    # Test CASE 4B + 5. Requestor sends ForceSubtaskResultsResponse with SubtaskResultsAccepted
    #  Step 1. Send ForceSubtaskResults
    current_time = get_current_utc_timestamp()
    (task_id, subtask_id) = get_task_id_and_subtask_id(test_id, '4B')
    api_request(
        cluster_url,
        'send',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        force_subtask_results(
            timestamp=timestamp_to_isoformat(current_time),
            ack_report_computed_task=ack_report_computed_task(
                timestamp=timestamp_to_isoformat(current_time - (cluster_consts.subtask_verification_time * 1.4)),
                report_computed_task=report_computed_task(
                    task_to_compute=task_to_compute(
                        timestamp=timestamp_to_isoformat(current_time - cluster_consts.subtask_verification_time * 1.5),
                        compute_task_def=compute_task_def(
                            task_id=task_id,
                            subtask_id=subtask_id,
                            deadline=current_time - (cluster_consts.subtask_verification_time),
                        )
                    )
                )
            )
        ),
        headers={
            'Content-Type': 'application/octet-stream',
            'temporary-account-funds': 'True'
        },
        expected_status=202,
    )
    time.sleep(1)
    #  Step 2. Send ForceSubtaskResultsResponse
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
                task_to_compute=task_to_compute(
                    timestamp=timestamp_to_isoformat(current_time - cluster_consts.subtask_verification_time * 1.5),
                    compute_task_def=compute_task_def(
                        task_id=task_id,
                        subtask_id=subtask_id,
                        deadline=current_time - (cluster_consts.subtask_verification_time),
                    )
                )
            )
        ),
        headers={
            'Content-Type': 'application/octet-stream',
            'temporary-account-funds': 'True'
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
                timestamp=timestamp_to_isoformat(current_time - (cluster_consts.subtask_verification_time * 1.4)),
                report_computed_task=report_computed_task(
                    task_to_compute=task_to_compute(
                        timestamp=timestamp_to_isoformat(current_time - cluster_consts.subtask_verification_time * 1.5),
                        compute_task_def=compute_task_def(
                            task_id=task_id,
                            subtask_id=subtask_id,
                            deadline=current_time - (cluster_consts.subtask_verification_time * 20),
                        )
                    )
                )
            )
        ),
        headers={
            'Content-Type': 'application/octet-stream',
            'temporary-account-funds': 'True'
        },
        expected_status=200,
        expected_message_type=message.concents.ForceSubtaskResultsRejected.TYPE,
        expected_content_type='application/octet-stream',
    )


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
            timestamp=timestamp_to_isoformat(current_time),  # current_time
            ack_report_computed_task=ack_report_computed_task(
                timestamp=timestamp_to_isoformat(current_time - (cluster_consts.subtask_verification_time * 1.4)),
                report_computed_task=report_computed_task(
                    task_to_compute=task_to_compute(
                        timestamp=timestamp_to_isoformat(current_time - cluster_consts.subtask_verification_time * 1.5),
                        compute_task_def=compute_task_def(
                            task_id=task_id,
                            subtask_id=subtask_id,
                            deadline=current_time - (cluster_consts.subtask_verification_time),
                        )
                    )
                )
            )
        ),
        headers={
            'Content-Type': 'application/octet-stream',
            'temporary-account-funds': ''
        },
        expected_status=200,
        expected_message_type=message.concents.ServiceRefused.TYPE,
        expected_content_type='application/octet-stream',
    )


def test_case_2a_send_duplicated_force_subtask_results(cluster_consts, cluster_url, test_id):
    #  Test CASE 2A + 2D + 3 - Send ForceSubtaskResults with same task_id as stored by Concent before
    #  Step 1. Send ForceSubtaskResults first time
    current_time = get_current_utc_timestamp()
    (task_id, subtask_id) = get_task_id_and_subtask_id(test_id, '2A')
    api_request(
        cluster_url,
        'send',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        force_subtask_results(
            timestamp=timestamp_to_isoformat(current_time),
            ack_report_computed_task=ack_report_computed_task(
                timestamp=timestamp_to_isoformat(current_time - (cluster_consts.subtask_verification_time * 1.4)),
                report_computed_task=report_computed_task(
                    task_to_compute=task_to_compute(
                        timestamp=timestamp_to_isoformat(current_time - cluster_consts.subtask_verification_time * 1.5),
                        compute_task_def=compute_task_def(
                            task_id=task_id,
                            subtask_id=subtask_id,
                            deadline=current_time - (cluster_consts.subtask_verification_time),
                        )
                    )
                )
            )
        ),
        headers={
            'Content-Type': 'application/octet-stream',
            'temporary-account-funds': 'True'
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
                timestamp=timestamp_to_isoformat(current_time - (cluster_consts.subtask_verification_time * 1.4)),
                report_computed_task=report_computed_task(
                    task_to_compute=task_to_compute(
                        timestamp=timestamp_to_isoformat(current_time - cluster_consts.subtask_verification_time * 1.5),
                        compute_task_def=compute_task_def(
                            task_id=task_id,
                            subtask_id=subtask_id,
                            deadline=current_time - (cluster_consts.subtask_verification_time),
                        )
                    )
                )
            )
        ),
        headers={
            'Content-Type': 'application/octet-stream',
            'temporary-account-funds': 'True'
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
        main()
    except requests.exceptions.ConnectionError as exception:
        print("\nERROR: Failed connect to the server.\n", file = sys.stderr)
        sys.exit(str(exception))
