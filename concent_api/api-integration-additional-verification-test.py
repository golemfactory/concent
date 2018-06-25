#!/usr/bin/env python3

import hashlib
import os
import sys
import time
from freezegun import freeze_time

from golem_messages import message

from common.helpers import get_current_utc_timestamp
from common.helpers import upload_file_to_storage_cluster
from api_testing_common import api_request
from api_testing_common import assert_condition
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

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "concent_api.settings")

#  TODO NEGATIVE TEST CASES


def get_subtask_results_verify(
    task_id,
    subtask_id,
    current_time,
    cluster_consts,
    reason,
    report_computed_task_size,
    report_computed_task_package_hash,
    task_to_compute_size,
    task_to_compute_package_hash,
    requestor_ethereum_public_key=None,
    provider_ethereum_public_key=None,
    price=1,
):
    task_to_compute = create_signed_task_to_compute(
        task_id=task_id,
        subtask_id=subtask_id,
        deadline=current_time + cluster_consts.additional_verification_call_time,
        price=price if price is not None else 1,
        size=task_to_compute_size,
        package_hash=task_to_compute_package_hash,
        requestor_ethereum_public_key=requestor_ethereum_public_key,
        provider_ethereum_public_key=provider_ethereum_public_key
    )

    report_computed_task = message.ReportComputedTask(
        task_to_compute=task_to_compute,
        subtask_id=subtask_id,
        size=report_computed_task_size,
        package_hash=report_computed_task_package_hash,
    )
    report_computed_task.sign_message(
        PROVIDER_PRIVATE_KEY,
        report_computed_task.get_short_hash()
    )

    with freeze_time(timestamp_to_isoformat(current_time - cluster_consts.additional_verification_call_time / 2)):
        subtask_results_rejected = message.tasks.SubtaskResultsRejected(
            reason=reason,
            report_computed_task=report_computed_task,
        )
        subtask_results_rejected.sign_message(
            REQUESTOR_PRIVATE_KEY,
            subtask_results_rejected.get_short_hash(),
        )

        subtask_results_verify = message.concents.SubtaskResultsVerify(
            subtask_results_rejected=subtask_results_rejected,
        )

    return subtask_results_verify


@count_fails
def test_case_1_test_for_positive_case(cluster_consts, cluster_url, test_id):
    current_time = get_current_utc_timestamp()
    (subtask_id, task_id) = get_task_id_and_subtask_id(test_id, 'existing_file')

    result_file_content_1 = task_id
    source_file_content_2 = subtask_id
    result_file_size_1 = len(result_file_content_1)
    source_file_size_2 = len(source_file_content_2)
    result_file_check_sum_1 = 'sha1:' + hashlib.sha1(result_file_content_1.encode()).hexdigest()
    source_file_check_sum_2 = 'sha1:' + hashlib.sha1(source_file_content_2.encode()).hexdigest()

    ack_subtask_results_verify = api_request(
        cluster_url,
        'send',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        get_subtask_results_verify(
            task_id,
            subtask_id,
            current_time,
            cluster_consts,
            reason=message.tasks.SubtaskResultsRejected.REASON.VerificationNegative,
            report_computed_task_size=result_file_size_1,
            report_computed_task_package_hash=result_file_check_sum_1,
            task_to_compute_size=source_file_size_2,
            task_to_compute_package_hash=source_file_check_sum_2,
        ),
        headers = {
            'Content-Type': 'application/octet-stream',
        },
        expected_status=200,
        expected_message_type=message.concents.AckSubtaskResultsVerify.TYPE,
        expected_content_type='application/octet-stream',
    )

    response = upload_file_to_storage_cluster(
        result_file_content_1,
        ack_subtask_results_verify.file_transfer_token.files[0]['path'],
        ack_subtask_results_verify.file_transfer_token,
        PROVIDER_PRIVATE_KEY,
        PROVIDER_PUBLIC_KEY,
        CONCENT_PUBLIC_KEY,
        STORAGE_CLUSTER_ADDRESS,
    )
    assert_condition(response.status_code, 200, 'File has not been stored on cluster')
    print('\nUploaded file with task_id {}. Checksum of this file is {}, and size of this file is {}.\n'.format(
        task_id,
        result_file_check_sum_1,
        result_file_size_1
    ))

    response = upload_file_to_storage_cluster(
        source_file_content_2,
        ack_subtask_results_verify.file_transfer_token.files[1]['path'],
        ack_subtask_results_verify.file_transfer_token,
        PROVIDER_PRIVATE_KEY,
        PROVIDER_PUBLIC_KEY,
        CONCENT_PUBLIC_KEY,
        STORAGE_CLUSTER_ADDRESS,
    )
    assert_condition(response.status_code, 200, 'File has not been stored on cluster')
    print('\nUploaded file with task_id {}. Checksum of this file is {}, and size of this file is {}.\n'.format(
        task_id,
        source_file_check_sum_2,
        source_file_size_2
    ))

    time.sleep(15)

    api_request(
        cluster_url,
        'receive-out-of-band',
        REQUESTOR_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        create_client_auth_message(REQUESTOR_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY, CONCENT_PUBLIC_KEY),
        headers = {
            'Content-Type': 'application/octet-stream',
        },
        expected_status=200,
        expected_message_type=message.concents.SubtaskResultsSettled.TYPE,
        expected_content_type='application/octet-stream',
    )

    api_request(
        cluster_url,
        'receive-out-of-band',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        create_client_auth_message(PROVIDER_PRIVATE_KEY, PROVIDER_PUBLIC_KEY, CONCENT_PUBLIC_KEY),
        headers = {
            'Content-Type': 'application/octet-stream',
        },
        expected_status=200,
        expected_message_type=message.concents.SubtaskResultsSettled.TYPE,
        expected_content_type='application/octet-stream',
    )


@count_fails
def test_case_2_test_for_resources_failure_reason(cluster_consts, cluster_url, test_id):
    current_time = get_current_utc_timestamp()
    (subtask_id, task_id) = get_task_id_and_subtask_id(test_id, 'existing_file')

    file_content = task_id
    file_size = len(file_content)
    file_check_sum = 'sha1:' + hashlib.sha1(file_content.encode()).hexdigest()

    api_request(
        cluster_url,
        'send',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        get_subtask_results_verify(
            task_id,
            subtask_id,
            current_time,
            cluster_consts,
            reason=message.tasks.SubtaskResultsRejected.REASON.ResourcesFailure,
            report_computed_task_size=file_size,
            report_computed_task_package_hash=file_check_sum,
            task_to_compute_size=file_size,
            task_to_compute_package_hash=file_check_sum,
        ),
        headers = {
            'Content-Type': 'application/octet-stream',
        },
        expected_status=200,
        expected_message_type=message.concents.ServiceRefused.TYPE,
        expected_content_type='application/octet-stream',
    )


@count_fails
def test_case_3_test_for_invalid_time(cluster_consts, cluster_url, test_id):
    current_time = get_current_utc_timestamp()
    (subtask_id, task_id) = get_task_id_and_subtask_id(test_id, 'existing_file')

    file_content = task_id
    file_size = len(file_content)
    file_check_sum = 'sha1:' + hashlib.sha1(file_content.encode()).hexdigest()

    api_request(
        cluster_url,
        'send',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        get_subtask_results_verify(
            task_id,
            subtask_id,
            current_time - cluster_consts.additional_verification_call_time,
            cluster_consts,
            reason=message.tasks.SubtaskResultsRejected.REASON.VerificationNegative,
            report_computed_task_size=file_size,
            report_computed_task_package_hash=file_check_sum,
            task_to_compute_size=file_size,
            task_to_compute_package_hash=file_check_sum,
        ),
        headers = {
            'Content-Type': 'application/octet-stream',
        },
        expected_status=200,
        expected_message_type=message.concents.ServiceRefused.TYPE,
        expected_content_type='application/octet-stream',
    )


@count_fails
def test_case_4_test_for_duplicated_request(cluster_consts, cluster_url, test_id):
    current_time = get_current_utc_timestamp()
    (subtask_id, task_id) = get_task_id_and_subtask_id(test_id, 'existing_file')

    result_file_content_1 = task_id
    source_file_content_2 = subtask_id
    result_file_size_1 = len(result_file_content_1)
    source_file_size_2 = len(source_file_content_2)
    result_file_check_sum_1 = 'sha1:' + hashlib.sha1(result_file_content_1.encode()).hexdigest()
    source_file_check_sum_2 = 'sha1:' + hashlib.sha1(source_file_content_2.encode()).hexdigest()

    api_request(
        cluster_url,
        'send',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        get_subtask_results_verify(
            task_id,
            subtask_id,
            current_time,
            cluster_consts,
            reason=message.tasks.SubtaskResultsRejected.REASON.VerificationNegative,
            report_computed_task_size=result_file_size_1,
            report_computed_task_package_hash=result_file_check_sum_1,
            task_to_compute_size=source_file_size_2,
            task_to_compute_package_hash=source_file_check_sum_2,
        ),
        headers = {
            'Content-Type': 'application/octet-stream',
        },
        expected_status=200,
        expected_message_type=message.concents.AckSubtaskResultsVerify.TYPE,
        expected_content_type='application/octet-stream',
    )

    api_request(
        cluster_url,
        'send',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        get_subtask_results_verify(
            task_id,
            subtask_id,
            current_time,
            cluster_consts,
            reason=message.tasks.SubtaskResultsRejected.REASON.VerificationNegative,
            report_computed_task_size=result_file_size_1,
            report_computed_task_package_hash=result_file_check_sum_1,
            task_to_compute_size=source_file_size_2,
            task_to_compute_package_hash=source_file_check_sum_2,
        ),
        headers = {
            'Content-Type': 'application/octet-stream',
        },
        expected_status=200,
        expected_message_type=message.concents.ServiceRefused.TYPE,
        expected_content_type='application/octet-stream',
    )


@count_fails
def test_case_5_test_requestor_status_account_negative(cluster_consts, cluster_url, test_id):
    current_time = get_current_utc_timestamp()
    (subtask_id, task_id) = get_task_id_and_subtask_id(test_id, 'existing_file')

    result_file_content_1 = task_id
    source_file_content_2 = subtask_id
    result_file_size_1 = len(result_file_content_1)
    source_file_size_2 = len(source_file_content_2)
    result_file_check_sum_1 = 'sha1:' + hashlib.sha1(result_file_content_1.encode()).hexdigest()
    source_file_check_sum_2 = 'sha1:' + hashlib.sha1(source_file_content_2.encode()).hexdigest()

    api_request(
        cluster_url,
        'send',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        get_subtask_results_verify(
            task_id,
            subtask_id,
            current_time,
            cluster_consts,
            reason=message.tasks.SubtaskResultsRejected.REASON.VerificationNegative,
            report_computed_task_size=result_file_size_1,
            report_computed_task_package_hash=result_file_check_sum_1,
            task_to_compute_size=source_file_size_2,
            task_to_compute_package_hash=source_file_check_sum_2,
            requestor_ethereum_public_key='33' * 64,
            provider_ethereum_public_key='32' * 64,
            price=0
        ),
        headers = {
            'Content-Type': 'application/octet-stream',
        },
        expected_status=200,
        expected_message_type=message.concents.ServiceRefused.TYPE,
        expected_content_type='application/octet-stream',
    )


if __name__ == '__main__':
    try:
        from concent_api.settings import CONCENT_PUBLIC_KEY
        from concent_api.settings import STORAGE_CLUSTER_ADDRESS
        run_tests(globals())
    except requests.exceptions.ConnectionError as exception:
        print("\nERROR: Failed connect to the server.\n", file=sys.stderr)
        sys.exit(str(exception))
