#!/usr/bin/env python3

import hashlib
import os
import sys
import time
from freezegun import freeze_time
from typing import Any
from typing import Dict
from typing import Optional
from mock import Mock

from golem_messages import message

from common.helpers import get_current_utc_timestamp
from common.helpers import upload_file_to_storage_cluster
from api_testing_common import api_request
from api_testing_common import assert_condition
from api_testing_common import count_fails
from api_testing_common import create_client_auth_message
from api_testing_common import create_signed_task_to_compute
from api_testing_common import receive_pending_messages_for_requestor_and_provider
from api_testing_common import run_tests
from api_testing_common import timestamp_to_isoformat
from golem_messages.factories.helpers import override_timestamp
from protocol_constants import ProtocolConstants

import requests

from core.utils import calculate_maximum_download_time

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "concent_api.settings")


def get_subtask_results_verify(
    current_time: int,
    reason: message.tasks.SubtaskResultsRejected.REASON,
    report_computed_task_size: int,
    report_computed_task_package_hash: str,
    task_to_compute_size: int,
    task_to_compute_package_hash: str,
    provider_public_key: Optional[bytes] = None,
    provider_private_key: Optional[bytes] = None,
    requestor_public_key: Optional[bytes] = None,
    requestor_private_key: Optional[bytes] = None,
    price: int = 1,
    is_verification_deadline_before_current_time: bool = False,
    additional_verification_call_time: int = 0,
    minimum_upload_rate: int = 0,
    render_parameters: Dict[str, Any] = None
) -> message.concents.SubtaskResultsVerify:
    task_to_compute = create_signed_task_to_compute(
        deadline=current_time,
        price=price if price is not None else 1,
        size=task_to_compute_size,
        package_hash=task_to_compute_package_hash,
        render_parameters=render_parameters,
        provider_public_key=provider_public_key if provider_public_key else sci_base.provider_public_key,
        provider_private_key=provider_private_key if provider_private_key else sci_base.provider_private_key,
        requestor_public_key=requestor_public_key if requestor_public_key else sci_base.requestor_public_key,
        requestor_private_key=requestor_private_key if requestor_private_key else sci_base.requestor_private_key,
    )

    report_computed_task = message.ReportComputedTask(
        task_to_compute=task_to_compute,
        size=report_computed_task_size,
        package_hash=report_computed_task_package_hash,
    )
    report_computed_task.sign_message(
        provider_private_key if provider_private_key else sci_base.provider_private_key,
        report_computed_task.get_short_hash()
    )

    with freeze_time(timestamp_to_isoformat(current_time - 1)):
        subtask_results_rejected = message.tasks.SubtaskResultsRejected(
            reason=reason,
            report_computed_task=report_computed_task,
        )
        if is_verification_deadline_before_current_time:
            override_timestamp(
                subtask_results_rejected,
                subtask_results_rejected.timestamp - (
                    additional_verification_call_time +
                    calculate_maximum_download_time(
                        report_computed_task.size,
                        minimum_upload_rate,
                    ) + 1
                )
            )
        subtask_results_rejected.sign_message(
            requestor_private_key if requestor_private_key else sci_base.requestor_private_key,
            subtask_results_rejected.get_short_hash(),
        )

        subtask_results_verify = message.concents.SubtaskResultsVerify(
            subtask_results_rejected=subtask_results_rejected,
        )

        subtask_results_verify.sign_concent_promissory_note(
            deposit_contract_address=GNT_DEPOSIT_CONTRACT_ADDRESS,
            private_key=provider_private_key or sci_base.provider_private_key,
        )
    return subtask_results_verify


def calculate_verification_deadline(
    subtask_results_rejected_timestamp: int,
    additional_verification_call_time: int,
    report_computed_task_size: int,
    minimum_upload_rate: int,
) -> int:
    return (
        subtask_results_rejected_timestamp +
        additional_verification_call_time +
        calculate_maximum_download_time(
            report_computed_task_size,
            minimum_upload_rate,
        )
    )


def get_render_params() -> Dict[str, Any]:
    return dict(
        resolution=[1024, 768],
        use_compositing=False,
        samples=0,
        borders_x=[0.0, 1.0],
        borders_y=[0.0, 1.0],
    )


@count_fails
def test_case_1_test_for_positive_case(cluster_consts: ProtocolConstants, cluster_url: str) -> None:  # pylint: disable=unused-argument
    receive_pending_messages_for_requestor_and_provider(
        cluster_url,
        sci_base,
        CONCENT_PUBLIC_KEY
    )
    current_time = get_current_utc_timestamp()
    provider_deposit_value = sci_base.get_provider_gntb_balance()
    requestor_deposit_value = sci_base.get_requestor_deposit_value()

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
        price=10000,
        render_parameters=get_render_params()
    )

    ack_subtask_results_verify = api_request(
        cluster_url,
        'send',
        sci_base.provider_private_key,
        CONCENT_PUBLIC_KEY,
        subtask_results_verify,
        expected_status=200,
        expected_message_type=message.concents.AckSubtaskResultsVerify,
        expected_content_type='application/octet-stream',
    )

    response = upload_file_to_storage_cluster(
        result_file_content,
        ack_subtask_results_verify.file_transfer_token.files[0]['path'],  # type: ignore
        ack_subtask_results_verify.file_transfer_token,  # type: ignore
        sci_base.provider_private_key,
        sci_base.provider_public_key,
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
        sci_base.provider_private_key,
        sci_base.provider_public_key,
        CONCENT_PUBLIC_KEY,
        STORAGE_CLUSTER_ADDRESS,
    )
    assert_condition(response.status_code, 200, 'File has not been stored on cluster')
    print('\nUploaded file with task_id {}. Checksum of this file is {}, and size of this file is {}.\n'.format(
        subtask_results_verify.task_id,
        source_file_checksum,
        source_file_size
    ))

    # Adding calculated number of seconds to time sleep makes us sure that subtask is after deadline.
    sleep_time = calculate_verification_deadline(
        subtask_results_verify.subtask_results_rejected.timestamp,
        cluster_consts.additional_verification_call_time,
        subtask_results_verify.subtask_results_rejected.report_computed_task.size,
        cluster_consts.minimum_upload_rate,
    ) - current_time
    print(f"Going to sleep for {sleep_time} secs...")
    time.sleep(
        sleep_time
    )

    api_request(
        cluster_url,
        'receive',
        sci_base.requestor_private_key,
        CONCENT_PUBLIC_KEY,
        create_client_auth_message(sci_base.requestor_private_key, sci_base.requestor_public_key, CONCENT_PUBLIC_KEY),
        expected_status=200,
        expected_message_type=message.concents.SubtaskResultsSettled,
        expected_content_type='application/octet-stream',
    )

    api_request(
        cluster_url,
        'receive',
        sci_base.provider_private_key,
        CONCENT_PUBLIC_KEY,
        create_client_auth_message(sci_base.provider_private_key, sci_base.provider_public_key, CONCENT_PUBLIC_KEY),
        expected_status=200,
        expected_message_type=message.concents.SubtaskResultsSettled,
        expected_content_type='application/octet-stream',
    )
    sci_base.ensure_that_provider_has_specific_gntb_balance(value=provider_deposit_value + 10000)
    sci_base.ensure_that_requestor_has_specific_deposit_balance(value=requestor_deposit_value - 10000)


@count_fails
def test_case_2_test_for_resources_failure_reason(cluster_consts: ProtocolConstants, cluster_url: str) -> None:  # pylint: disable=unused-argument
    receive_pending_messages_for_requestor_and_provider(
        cluster_url,
        sci_base,
        CONCENT_PUBLIC_KEY
    )
    current_time = get_current_utc_timestamp()
    file_content = 'test'
    file_size = len(file_content)
    file_check_sum = 'sha1:' + hashlib.sha1(file_content.encode()).hexdigest()

    api_request(
        cluster_url,
        'send',
        sci_base.provider_private_key,
        CONCENT_PUBLIC_KEY,
        get_subtask_results_verify(
            current_time,
            reason=message.tasks.SubtaskResultsRejected.REASON.ResourcesFailure,
            report_computed_task_size=file_size,
            report_computed_task_package_hash=file_check_sum,
            task_to_compute_size=file_size,
            task_to_compute_package_hash=file_check_sum,
            render_parameters=get_render_params()
        ),
        expected_status=200,
        expected_message_type=message.concents.ServiceRefused,
        expected_content_type='application/octet-stream',
    )


@count_fails
def test_case_3_test_for_invalid_time(cluster_consts: ProtocolConstants, cluster_url: str) -> None:  # pylint: disable=unused-argument
    receive_pending_messages_for_requestor_and_provider(
        cluster_url,
        sci_base,
        CONCENT_PUBLIC_KEY
    )
    current_time = get_current_utc_timestamp()

    file_content = 'test'
    file_size = len(file_content)
    file_check_sum = 'sha1:' + hashlib.sha1(file_content.encode()).hexdigest()

    api_request(
        cluster_url,
        'send',
        sci_base.provider_private_key,
        CONCENT_PUBLIC_KEY,
        get_subtask_results_verify(
            current_time,
            reason=message.tasks.SubtaskResultsRejected.REASON.VerificationNegative,
            report_computed_task_size=file_size,
            report_computed_task_package_hash=file_check_sum,
            task_to_compute_size=file_size,
            task_to_compute_package_hash=file_check_sum,
            is_verification_deadline_before_current_time=True,
            additional_verification_call_time=cluster_consts.additional_verification_call_time,
            minimum_upload_rate=cluster_consts.minimum_upload_rate,
            render_parameters=get_render_params()
        ),
        expected_status=200,
        expected_message_type=message.concents.ServiceRefused,
        expected_content_type='application/octet-stream',
    )


@count_fails
def test_case_4_test_for_duplicated_request(cluster_consts: ProtocolConstants, cluster_url: str) -> None:  # pylint: disable=unused-argument
    receive_pending_messages_for_requestor_and_provider(
        cluster_url,
        sci_base,
        CONCENT_PUBLIC_KEY
    )
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
        render_parameters=get_render_params()
    )

    api_request(
        cluster_url,
        'send',
        sci_base.provider_private_key,
        CONCENT_PUBLIC_KEY,
        subtask_results_verify,
        expected_status=200,
        expected_message_type=message.concents.AckSubtaskResultsVerify,
        expected_content_type='application/octet-stream',
    )

    # Set signature to None so message can be serialized again.
    subtask_results_verify.sig = None

    api_request(
        cluster_url,
        'send',
        sci_base.provider_private_key,
        CONCENT_PUBLIC_KEY,
        subtask_results_verify,
        expected_status=200,
        expected_message_type=message.concents.ServiceRefused,
        expected_content_type='application/octet-stream',
    )


@count_fails
def test_case_5_test_requestor_status_account_negative(cluster_consts: ProtocolConstants, cluster_url: str) -> None:  # pylint: disable=unused-argument
    receive_pending_messages_for_requestor_and_provider(
        cluster_url,
        sci_base,
        CONCENT_PUBLIC_KEY
    )
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
        sci_base.provider_empty_account_private_key,
        CONCENT_PUBLIC_KEY,
        get_subtask_results_verify(
            current_time,
            reason=message.tasks.SubtaskResultsRejected.REASON.VerificationNegative,
            report_computed_task_size=result_file_size_1,
            report_computed_task_package_hash=result_file_check_sum_1,
            task_to_compute_size=source_file_size_2,
            task_to_compute_package_hash=source_file_check_sum_2,
            provider_public_key=sci_base.provider_empty_account_public_key,
            provider_private_key=sci_base.provider_empty_account_private_key,
            requestor_public_key=sci_base.requestor_empty_account_public_key,
            requestor_private_key=sci_base.requestor_empty_account_private_key,
            price=1000,
            render_parameters=get_render_params()
        ),
        expected_status=200,
        expected_message_type=message.concents.ServiceRefused,
        expected_content_type='application/octet-stream',
    )


@count_fails
def test_case_6_test_with_invalid_blender_script_parameters(cluster_consts: ProtocolConstants, cluster_url: str) -> None:  # pylint: disable=unused-argument
    receive_pending_messages_for_requestor_and_provider(
        cluster_url,
        sci_base,
        CONCENT_PUBLIC_KEY
    )
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

    subtask_results_verify=get_subtask_results_verify(
        current_time,
        reason=message.tasks.SubtaskResultsRejected.REASON.VerificationNegative,
        report_computed_task_size=result_file_size,
        report_computed_task_package_hash=result_file_checksum,
        task_to_compute_size=source_file_size,
        task_to_compute_package_hash=source_file_checksum,
        price=1000,
    )

    # Setting parameters which are necessary for proper blender work to invalid values
    subtask_results_verify.task_to_compute.compute_task_def['extra_data']['crops'] = None
    subtask_results_verify.task_to_compute.compute_task_def['extra_data']['resolution'] = None
    subtask_results_verify.task_to_compute.compute_task_def['extra_data']['samples'] = None
    subtask_results_verify.task_to_compute.compute_task_def['extra_data']['use_compositing'] = None

    api_request(
        cluster_url,
        'send',
        sci_base.provider_private_key,
        CONCENT_PUBLIC_KEY,
        subtask_results_verify,
        expected_status=400,
        expected_error_code='message.invalid',
    )


if __name__ == '__main__':
    try:
        from concent_api.settings import CONCENT_PUBLIC_KEY
        from concent_api.settings import STORAGE_CLUSTER_ADDRESS
        from concent_api.settings import GNT_DEPOSIT_CONTRACT_ADDRESS
        # Dirty workaround for init `sci_base` variable to hide errors in IDE.
        # sci_base is initiated in `run_tests` function
        sci_base = Mock()
        status = run_tests(globals())
        exit(status)
    except requests.exceptions.ConnectionError as exception:
        print("\nERROR: Failed connect to the server.\n", file=sys.stderr)
        sys.exit(str(exception))
