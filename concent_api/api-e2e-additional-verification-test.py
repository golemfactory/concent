#!/usr/bin/env python3

import hashlib
import os
import sys
import time
from freezegun import freeze_time
from typing import Optional

from golem_messages import message

from common.helpers import get_current_utc_timestamp
from common.helpers import upload_file_to_storage_cluster
from common.testing_helpers import generate_priv_and_pub_eth_account_key
from api_testing_common import api_request
from api_testing_common import assert_condition
from api_testing_common import count_fails
from api_testing_common import create_client_auth_message
from api_testing_common import create_signed_task_to_compute
from api_testing_common import PROVIDER_PRIVATE_KEY
from api_testing_common import PROVIDER_PUBLIC_KEY
from api_testing_common import REQUESTOR_ETHEREUM_PRIVATE_KEY_FOR_EMPTY_ACCOUNT
from api_testing_common import REQUESTOR_ETHEREUM_PUBLIC_KEY_FOR_EMPTY_ACCOUNT
from api_testing_common import REQUESTOR_PRIVATE_KEY
from api_testing_common import REQUESTOR_PUBLIC_KEY
from api_testing_common import run_tests
from api_testing_common import timestamp_to_isoformat
from protocol_constants import ProtocolConstants

import requests

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "concent_api.settings")

CALCULATED_VERIFICATION_TIME = 25  # seconds

(DIFFERENT_REQUESTOR_ETHEREUM_PRIVATE_KEY, DIFFERENT_REQUESTOR_ETHEREUM_PUBLIC_KEY) = generate_priv_and_pub_eth_account_key()
(DIFFERENT_PROVIDER_ETHEREUM_PRIVATE_KEY, DIFFERENT_PROVIDER_ETHEREUM_PUBLIC_KEY) = generate_priv_and_pub_eth_account_key()


#  TODO NEGATIVE TEST CASES


def get_subtask_results_verify(
    current_time: int,
    reason: message.tasks.SubtaskResultsRejected.REASON,
    report_computed_task_size: int,
    report_computed_task_package_hash: str,
    task_to_compute_size: int,
    task_to_compute_package_hash: str,
    requestor_ethereum_public_key: Optional[bytes]=None,
    requestor_ethereum_private_key: Optional[bytes]=None,
    provider_ethereum_public_key: Optional[bytes]=None,
    price: int=1,
    meta_parameters: Optional[str]=None,
) -> message.concents.SubtaskResultsVerify:
    task_to_compute = create_signed_task_to_compute(
        deadline=current_time + CALCULATED_VERIFICATION_TIME,
        price=price if price is not None else 1,
        size=task_to_compute_size,
        package_hash=task_to_compute_package_hash,
        requestor_ethereum_public_key=requestor_ethereum_public_key,
        requestor_ethereum_private_key=requestor_ethereum_private_key,
        provider_ethereum_public_key=provider_ethereum_public_key,
        meta_parameters=meta_parameters,
    )

    report_computed_task = message.ReportComputedTask(
        task_to_compute=task_to_compute,
        size=report_computed_task_size,
        package_hash=report_computed_task_package_hash,
    )
    report_computed_task.sign_message(
        PROVIDER_PRIVATE_KEY,
        report_computed_task.get_short_hash()
    )

    with freeze_time(timestamp_to_isoformat(current_time - 1)):
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
def test_case_1_test_for_positive_case(cluster_consts: ProtocolConstants, cluster_url: str) -> None:  # pylint: disable=unused-argument
    current_time = get_current_utc_timestamp()

    current_dir = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(current_dir, 'tests_resources', 'source.zip'), 'rb') as archive:
        source_file_content = archive.read()
    with open(os.path.join(current_dir, 'tests_resources', 'result.zip'), 'rb') as archive:
        result_file_content = archive.read()

    result_file_size = len(result_file_content)
    source_file_size = len(source_file_content)
    result_file_checksum = 'sha1:' + hashlib.sha1(result_file_content).hexdigest()
    source_file_checksum = 'sha1:' + hashlib.sha1(source_file_content).hexdigest()

    subtask_results_verify = get_subtask_results_verify(
        current_time,
        reason=message.tasks.SubtaskResultsRejected.REASON.VerificationNegative,
        report_computed_task_size=result_file_size,
        report_computed_task_package_hash=result_file_checksum,
        task_to_compute_size=source_file_size,
        task_to_compute_package_hash=source_file_checksum,
    )

    ack_subtask_results_verify = api_request(
        cluster_url,
        'send',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        subtask_results_verify,
        headers = {
            'Content-Type': 'application/octet-stream',
        },
        expected_status=200,
        expected_message_type=message.concents.AckSubtaskResultsVerify,
        expected_content_type='application/octet-stream',
    )

    response = upload_file_to_storage_cluster(
        result_file_content,
        ack_subtask_results_verify.file_transfer_token.files[0]['path'],  # type: ignore
        ack_subtask_results_verify.file_transfer_token,  # type: ignore
        PROVIDER_PRIVATE_KEY,
        PROVIDER_PUBLIC_KEY,
        CONCENT_PUBLIC_KEY,
        STORAGE_CLUSTER_ADDRESS,
    )
    assert_condition(response.status_code, 200, 'File has not been stored on cluster')
    print('\nUploaded file with task_id {}. Checksum of this file is {}, and size of this file is {}.\n'.format(
        subtask_results_verify.task_id,
        result_file_checksum,
        result_file_size
    ))

    response = upload_file_to_storage_cluster(
        source_file_content,
        ack_subtask_results_verify.file_transfer_token.files[1]['path'],  # type: ignore
        ack_subtask_results_verify.file_transfer_token,  # type: ignore
        PROVIDER_PRIVATE_KEY,
        PROVIDER_PUBLIC_KEY,
        CONCENT_PUBLIC_KEY,
        STORAGE_CLUSTER_ADDRESS,
    )
    assert_condition(response.status_code, 200, 'File has not been stored on cluster')
    print('\nUploaded file with task_id {}. Checksum of this file is {}, and size of this file is {}.\n'.format(
        subtask_results_verify.task_id,
        source_file_checksum,
        source_file_size
    ))

    # Adding 10 seconds to time sleep makes us sure that subtask is after deadline.
    time.sleep(CALCULATED_VERIFICATION_TIME * (ADDITIONAL_VERIFICATION_TIME_MULTIPLIER / BLENDER_THREADS))

    api_request(
        cluster_url,
        'receive',
        REQUESTOR_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        create_client_auth_message(REQUESTOR_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY, CONCENT_PUBLIC_KEY),
        headers = {
            'Content-Type': 'application/octet-stream',
        },
        expected_status=200,
        expected_message_type=message.concents.SubtaskResultsSettled,
        expected_content_type='application/octet-stream',
    )

    api_request(
        cluster_url,
        'receive',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        create_client_auth_message(PROVIDER_PRIVATE_KEY, PROVIDER_PUBLIC_KEY, CONCENT_PUBLIC_KEY),
        headers = {
            'Content-Type': 'application/octet-stream',
        },
        expected_status=200,
        expected_message_type=message.concents.SubtaskResultsSettled,
        expected_content_type='application/octet-stream',
    )


@count_fails
def test_case_2_test_for_resources_failure_reason(cluster_consts: ProtocolConstants, cluster_url: str) -> None:  # pylint: disable=unused-argument
    current_time = get_current_utc_timestamp()

    file_content = 'test'
    file_size = len(file_content)
    file_check_sum = 'sha1:' + hashlib.sha1(file_content.encode()).hexdigest()

    api_request(
        cluster_url,
        'send',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        get_subtask_results_verify(
            current_time,
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
        expected_message_type=message.concents.ServiceRefused,
        expected_content_type='application/octet-stream',
    )


@count_fails
def test_case_3_test_for_invalid_time(cluster_consts: ProtocolConstants, cluster_url: str) -> None:  # pylint: disable=unused-argument
    current_time = get_current_utc_timestamp()

    file_content = 'test'
    file_size = len(file_content)
    file_check_sum = 'sha1:' + hashlib.sha1(file_content.encode()).hexdigest()

    api_request(
        cluster_url,
        'send',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        get_subtask_results_verify(
            current_time - (CALCULATED_VERIFICATION_TIME * (ADDITIONAL_VERIFICATION_TIME_MULTIPLIER / BLENDER_THREADS)),
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
        expected_message_type=message.concents.ServiceRefused,
        expected_content_type='application/octet-stream',
    )


@count_fails
def test_case_4_test_for_duplicated_request(cluster_consts: ProtocolConstants, cluster_url: str) -> None:  # pylint: disable=unused-argument
    current_time = get_current_utc_timestamp()

    result_file_content_1 = 'test'
    source_file_content_2 = 'test'
    result_file_size_1 = len(result_file_content_1)
    source_file_size_2 = len(source_file_content_2)
    result_file_check_sum_1 = 'sha1:' + hashlib.sha1(result_file_content_1.encode()).hexdigest()
    source_file_check_sum_2 = 'sha1:' + hashlib.sha1(source_file_content_2.encode()).hexdigest()

    subtask_results_verify = get_subtask_results_verify(
        current_time,
        reason=message.tasks.SubtaskResultsRejected.REASON.VerificationNegative,
        report_computed_task_size=result_file_size_1,
        report_computed_task_package_hash=result_file_check_sum_1,
        task_to_compute_size=source_file_size_2,
        task_to_compute_package_hash=source_file_check_sum_2,
    )

    api_request(
        cluster_url,
        'send',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        subtask_results_verify,
        headers = {
            'Content-Type': 'application/octet-stream',
        },
        expected_status=200,
        expected_message_type=message.concents.AckSubtaskResultsVerify,
        expected_content_type='application/octet-stream',
    )

    # Set signature to None so message can be serialized again.
    subtask_results_verify.sig = None

    api_request(
        cluster_url,
        'send',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        subtask_results_verify,
        headers = {
            'Content-Type': 'application/octet-stream',
        },
        expected_status=200,
        expected_message_type=message.concents.ServiceRefused,
        expected_content_type='application/octet-stream',
    )


@count_fails
def test_case_5_test_requestor_status_account_negative(cluster_consts: ProtocolConstants, cluster_url: str) -> None:  # pylint: disable=unused-argument
    current_time = get_current_utc_timestamp()

    result_file_content_1 = 'test'
    source_file_content_2 = 'test'
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
            current_time,
            reason=message.tasks.SubtaskResultsRejected.REASON.VerificationNegative,
            report_computed_task_size=result_file_size_1,
            report_computed_task_package_hash=result_file_check_sum_1,
            task_to_compute_size=source_file_size_2,
            task_to_compute_package_hash=source_file_check_sum_2,
            requestor_ethereum_public_key=REQUESTOR_ETHEREUM_PUBLIC_KEY_FOR_EMPTY_ACCOUNT,
            requestor_ethereum_private_key=REQUESTOR_ETHEREUM_PRIVATE_KEY_FOR_EMPTY_ACCOUNT,
            provider_ethereum_public_key=DIFFERENT_PROVIDER_ETHEREUM_PUBLIC_KEY,
            price=1000
        ),
        headers = {
            'Content-Type': 'application/octet-stream',
        },
        expected_status=200,
        expected_message_type=message.concents.ServiceRefused,
        expected_content_type='application/octet-stream',
    )


@count_fails
def test_case_6_test_without_script_src_in(cluster_consts: ProtocolConstants, cluster_url: str) -> None:  # pylint: disable=unused-argument
    current_time = get_current_utc_timestamp()

    current_dir = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(current_dir, 'tests_resources', 'source.zip'), 'rb') as archive:
        source_file_content = archive.read()
    with open(os.path.join(current_dir, 'tests_resources', 'result.zip'), 'rb') as archive:
        result_file_content = archive.read()

    result_file_size = len(result_file_content)
    source_file_size = len(source_file_content)
    result_file_checksum = 'sha1:' + hashlib.sha1(result_file_content).hexdigest()
    source_file_checksum = 'sha1:' + hashlib.sha1(source_file_content).hexdigest()

    subtask_results_verify= get_subtask_results_verify(
        current_time,
        reason=message.tasks.SubtaskResultsRejected.REASON.VerificationNegative,
        report_computed_task_size=result_file_size,
        report_computed_task_package_hash=result_file_checksum,
        task_to_compute_size=source_file_size,
        task_to_compute_package_hash=source_file_checksum,
    )

    ack_subtask_results_verify = api_request(
        cluster_url,
        'send',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        subtask_results_verify,
        headers = {
            'Content-Type': 'application/octet-stream',
        },
        expected_status=200,
        expected_message_type=message.concents.AckSubtaskResultsVerify,
        expected_content_type='application/octet-stream',
    )

    response = upload_file_to_storage_cluster(
        result_file_content,
        ack_subtask_results_verify.file_transfer_token.files[0]['path'],  # type: ignore
        ack_subtask_results_verify.file_transfer_token,  # type: ignore
        PROVIDER_PRIVATE_KEY,
        PROVIDER_PUBLIC_KEY,
        CONCENT_PUBLIC_KEY,
        STORAGE_CLUSTER_ADDRESS,
    )
    assert_condition(response.status_code, 200, 'File has not been stored on cluster')
    print('\nUploaded file with task_id {}. Checksum of this file is {}, and size of this file is {}.\n'.format(
        subtask_results_verify.task_id,
        result_file_checksum,
        result_file_size
    ))

    response = upload_file_to_storage_cluster(
        source_file_content,
        ack_subtask_results_verify.file_transfer_token.files[1]['path'],  # type: ignore
        ack_subtask_results_verify.file_transfer_token,  # type: ignore
        PROVIDER_PRIVATE_KEY,
        PROVIDER_PUBLIC_KEY,
        CONCENT_PUBLIC_KEY,
        STORAGE_CLUSTER_ADDRESS,
    )
    assert_condition(response.status_code, 200, 'File has not been stored on cluster')
    print('\nUploaded file with task_id {}. Checksum of this file is {}, and size of this file is {}.\n'.format(
        subtask_results_verify.task_id,
        source_file_checksum,
        source_file_size
    ))

    # Adding 10 seconds to time sleep makes us sure that subtask is after deadline.
    time.sleep(CALCULATED_VERIFICATION_TIME * (ADDITIONAL_VERIFICATION_TIME_MULTIPLIER / BLENDER_THREADS))

    api_request(
        cluster_url,
        'receive',
        REQUESTOR_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        create_client_auth_message(REQUESTOR_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY, CONCENT_PUBLIC_KEY),
        headers = {
            'Content-Type': 'application/octet-stream',
        },
        expected_status=200,
        expected_message_type=message.concents.SubtaskResultsSettled,
        expected_content_type='application/octet-stream',
    )

    api_request(
        cluster_url,
        'receive',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        create_client_auth_message(PROVIDER_PRIVATE_KEY, PROVIDER_PUBLIC_KEY, CONCENT_PUBLIC_KEY),
        headers = {
            'Content-Type': 'application/octet-stream',
        },
        expected_status=200,
        expected_message_type=message.concents.SubtaskResultsSettled,
        expected_content_type='application/octet-stream',
    )


if __name__ == '__main__':
    try:
        from concent_api.settings import CONCENT_PUBLIC_KEY
        from concent_api.settings import STORAGE_CLUSTER_ADDRESS
        from concent_api.settings import ADDITIONAL_VERIFICATION_TIME_MULTIPLIER
        from concent_api.settings import BLENDER_THREADS
        run_tests(globals())
    except requests.exceptions.ConnectionError as exception:
        print("\nERROR: Failed connect to the server.\n", file=sys.stderr)
        sys.exit(str(exception))
