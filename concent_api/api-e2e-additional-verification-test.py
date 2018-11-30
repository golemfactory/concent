#!/usr/bin/env python3

import hashlib
import os
import sys
import time
from freezegun import freeze_time
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
from api_testing_common import run_tests
from api_testing_common import timestamp_to_isoformat
from golem_messages.factories.helpers import override_timestamp
from protocol_constants import ProtocolConstants

import requests

from core.utils import calculate_maximum_download_time

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "concent_api.settings")


#  TODO NEGATIVE TEST CASES

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
    script_src: Optional[str] = None,
    is_verification_deadline_before_current_time: bool=False,
    additional_verification_call_time: int=0,
    minimum_upload_rate: int=0
) -> message.concents.SubtaskResultsVerify:
    task_to_compute = create_signed_task_to_compute(
        deadline=current_time,
        price=price if price is not None else 1,
        size=task_to_compute_size,
        package_hash=task_to_compute_package_hash,
        script_src=script_src,
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


@count_fails
def test_case_1_test_for_positive_case(cluster_consts: ProtocolConstants, cluster_url: str) -> None:  # pylint: disable=unused-argument
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
        script_src='# This template is rendered by\n# apps.blender.resources.scenefileeditor.generate_blender_crop_file(),\n# written to tempfile and passed as arg to blender.\nimport bpy\n\nclass EngineWarning(bpy.types.Operator):\n    bl_idname = "wm.engine_warning"\n    bl_label = "Inform about not supported rendering engine"\n\n    def execute(self, context):\n        self.report({"ERROR"}, "Engine " + bpy.context.scene.render.engine + \\\n                               " not supported by Golem")\n        return {"FINISHED"}\n\nclass ShowInformation(bpy.types.Operator):\n    bl_idname = "wm.scene_information"\n    bl_label = "Inform user about scene settings"\n\n\n    def execute(self, context):\n        self.report({"INFO"}, "Resolution: " +\n                              str(bpy.context.scene.render.resolution_x) +\n                               " x " +\n                               str(bpy.context.scene.render.resolution_y))\n        self.report({"INFO"}, "File format: " +\n                               str(bpy.context.scene.render.file_extension))\n        self.report({"INFO"}, "Filepath: " +\n                              str(bpy.context.scene.render.filepath))\n        self.report({"INFO"}, "Frames: " +\n                              str(bpy.context.scene.frame_start) + "-" +\n                              str(bpy.context.scene.frame_end) + ";" +\n                              str(bpy.context.scene.frame_step))\n\n        return {"FINISHED"}\n\n\nbpy.utils.register_class(EngineWarning)\nengine = bpy.context.scene.render.engine\nif engine not in ("BLENDER_RENDER", "CYCLES"):\n    bpy.ops.wm.engine_warning()\n\nbpy.utils.register_class(ShowInformation)\nbpy.ops.wm.scene_information()\n\n\nfor scene in bpy.data.scenes:\n\n    scene.render.tile_x = 0\n    scene.render.tile_y = 0\n    scene.render.resolution_x = 1024\n    scene.render.resolution_y = 768\n    scene.render.resolution_percentage = 100\n    scene.render.use_border = True\n    scene.render.use_crop_to_border = True\n    scene.render.border_max_x = 1.0\n    scene.render.border_min_x = 0.0\n    scene.render.border_min_y = 0.0\n    scene.render.border_max_y = 1.0\n    scene.render.use_compositing = bool(False)\n\n#and check if additional files aren\'t missing\nbpy.ops.file.report_missing_files()\n',
        price=10000,
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
    time.sleep(
        calculate_verification_deadline(
            subtask_results_verify.subtask_results_rejected.timestamp,
            cluster_consts.additional_verification_call_time,
            subtask_results_verify.subtask_results_rejected.report_computed_task.size,
            cluster_consts.minimum_upload_rate,
        ) - current_time
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
        ),
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
        ),
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
            price=1000
        ),
        expected_status=200,
        expected_message_type=message.concents.ServiceRefused,
        expected_content_type='application/octet-stream',
    )


@count_fails
def test_case_6_test_without_script_src_in(cluster_consts: ProtocolConstants, cluster_url: str) -> None:  # pylint: disable=unused-argument
    current_time = get_current_utc_timestamp()
    provider_gntb_balance = sci_base.get_provider_gntb_balance()
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

    subtask_results_verify= get_subtask_results_verify(
        current_time,
        reason=message.tasks.SubtaskResultsRejected.REASON.VerificationNegative,
        report_computed_task_size=result_file_size,
        report_computed_task_package_hash=result_file_checksum,
        task_to_compute_size=source_file_size,
        task_to_compute_package_hash=source_file_checksum,
        price=1000,
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
    time.sleep(
        calculate_verification_deadline(
            subtask_results_verify.subtask_results_rejected.timestamp,
            cluster_consts.additional_verification_call_time,
            subtask_results_verify.subtask_results_rejected.report_computed_task.size,
            cluster_consts.minimum_upload_rate,
        ) - current_time
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
    sci_base.ensure_that_provider_has_specific_gntb_balance(value=provider_gntb_balance + 1000)
    sci_base.ensure_that_requestor_has_specific_deposit_balance(value=requestor_deposit_value - 1000)


if __name__ == '__main__':
    try:
        from concent_api.settings import CONCENT_PUBLIC_KEY
        from concent_api.settings import STORAGE_CLUSTER_ADDRESS
        # Dirty workaround for init `sci_base` variable to hide errors in IDE.
        # sci_base is initiated in `run_tests` function
        sci_base = Mock()
        status = run_tests(globals())
        exit(status)
    except requests.exceptions.ConnectionError as exception:
        print("\nERROR: Failed connect to the server.\n", file=sys.stderr)
        sys.exit(str(exception))
