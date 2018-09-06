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
from api_testing_common import api_request
from api_testing_common import assert_condition
from api_testing_common import count_fails
from api_testing_common import create_client_auth_message
from api_testing_common import create_signed_task_to_compute
from api_testing_common import PROVIDER_PRIVATE_KEY
from api_testing_common import PROVIDER_PUBLIC_KEY
from api_testing_common import REQUESTOR_PRIVATE_KEY
from api_testing_common import REQUESTOR_PUBLIC_KEY
from api_testing_common import run_tests
from api_testing_common import timestamp_to_isoformat
from protocol_constants import ProtocolConstants

import requests

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "concent_api.settings")

CALCULATED_VERIFICATION_TIME = 25  # seconds


#  TODO NEGATIVE TEST CASES


def get_subtask_results_verify(
    task_id: str,
    subtask_id: str,
    current_time: int,
    reason: message.tasks.SubtaskResultsRejected.REASON,
    report_computed_task_size: int,
    report_computed_task_package_hash: str,
    task_to_compute_size: int,
    task_to_compute_package_hash: str,
    requestor_ethereum_public_key: Optional[bytes]=None,
    provider_ethereum_public_key: Optional[bytes]=None,
    price: int=1,
    script_src: Optional[str]=None,
) -> message.concents.SubtaskResultsVerify:
    task_to_compute = create_signed_task_to_compute(
        task_id=task_id,
        subtask_id=subtask_id,
        deadline=current_time + CALCULATED_VERIFICATION_TIME,
        price=price if price is not None else 1,
        size=task_to_compute_size,
        package_hash=task_to_compute_package_hash,
        requestor_ethereum_public_key=requestor_ethereum_public_key,
        provider_ethereum_public_key=provider_ethereum_public_key,
        script_src=script_src,
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
def test_case_1_test_for_positive_case(
    cluster_consts: ProtocolConstants,
    cluster_url: str,
    task_id: str,
    subtask_id: str,
) -> None:  # pylint: disable=unused-argument
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

    ack_subtask_results_verify = api_request(
        cluster_url,
        'send',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        get_subtask_results_verify(
            task_id,
            subtask_id,
            current_time,
            reason=message.tasks.SubtaskResultsRejected.REASON.VerificationNegative,
            report_computed_task_size=result_file_size,
            report_computed_task_package_hash=result_file_checksum,
            task_to_compute_size=source_file_size,
            task_to_compute_package_hash=source_file_checksum,
            script_src='# This template is rendered by\n# apps.blender.resources.scenefileeditor.generate_blender_crop_file(),\n# written to tempfile and passed as arg to blender.\nimport bpy\n\nclass EngineWarning(bpy.types.Operator):\n    bl_idname = "wm.engine_warning"\n    bl_label = "Inform about not supported rendering engine"\n\n    def execute(self, context):\n        self.report({"ERROR"}, "Engine " + bpy.context.scene.render.engine + \\\n                               " not supported by Golem")\n        return {"FINISHED"}\n\nclass ShowInformation(bpy.types.Operator):\n    bl_idname = "wm.scene_information"\n    bl_label = "Inform user about scene settings"\n\n\n    def execute(self, context):\n        self.report({"INFO"}, "Resolution: " +\n                              str(bpy.context.scene.render.resolution_x) +\n                               " x " +\n                               str(bpy.context.scene.render.resolution_y))\n        self.report({"INFO"}, "File format: " +\n                               str(bpy.context.scene.render.file_extension))\n        self.report({"INFO"}, "Filepath: " +\n                              str(bpy.context.scene.render.filepath))\n        self.report({"INFO"}, "Frames: " +\n                              str(bpy.context.scene.frame_start) + "-" +\n                              str(bpy.context.scene.frame_end) + ";" +\n                              str(bpy.context.scene.frame_step))\n\n        return {"FINISHED"}\n\n\nbpy.utils.register_class(EngineWarning)\nengine = bpy.context.scene.render.engine\nif engine not in ("BLENDER_RENDER", "CYCLES"):\n    bpy.ops.wm.engine_warning()\n\nbpy.utils.register_class(ShowInformation)\nbpy.ops.wm.scene_information()\n\n\nfor scene in bpy.data.scenes:\n\n    scene.render.tile_x = 0\n    scene.render.tile_y = 0\n    scene.render.resolution_x = 1024\n    scene.render.resolution_y = 768\n    scene.render.resolution_percentage = 100\n    scene.render.use_border = True\n    scene.render.use_crop_to_border = True\n    scene.render.border_max_x = 1.0\n    scene.render.border_min_x = 0.0\n    scene.render.border_min_y = 0.0\n    scene.render.border_max_y = 1.0\n    scene.render.use_compositing = bool(False)\n\n#and check if additional files aren\'t missing\nbpy.ops.file.report_missing_files()\n',
        ),
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
        task_id,
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
        task_id,
        source_file_checksum,
        source_file_size
    ))

    # Adding 10 seconds to time sleep makes us sure that subtask is after deadline.
    time.sleep(CALCULATED_VERIFICATION_TIME * (ADDITIONAL_VERIFICATION_TIME_MULTIPLIER / BLENDER_THREADS))

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
        expected_message_type=message.concents.SubtaskResultsSettled,
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
        expected_message_type=message.concents.SubtaskResultsSettled,
        expected_content_type='application/octet-stream',
    )


@count_fails
def test_case_2_test_for_resources_failure_reason(
    cluster_consts: ProtocolConstants,
    cluster_url: str,
    task_id: str,
    subtask_id: str,
) -> None:  # pylint: disable=unused-argument
    current_time = get_current_utc_timestamp()

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
def test_case_3_test_for_invalid_time(
    cluster_consts: ProtocolConstants,
    cluster_url: str,
    task_id: str,
    subtask_id: str,
) -> None:  # pylint: disable=unused-argument
    current_time = get_current_utc_timestamp()

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
def test_case_4_test_for_duplicated_request(
    cluster_consts: ProtocolConstants,
    cluster_url: str,
    task_id: str,
    subtask_id: str,
) -> None:  # pylint: disable=unused-argument
    current_time = get_current_utc_timestamp()

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
        expected_message_type=message.concents.AckSubtaskResultsVerify,
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
        expected_message_type=message.concents.ServiceRefused,
        expected_content_type='application/octet-stream',
    )


@count_fails
def test_case_5_test_requestor_status_account_negative(
    cluster_consts: ProtocolConstants,
    cluster_url: str,
    task_id: str,
    subtask_id: str,
) -> None:  # pylint: disable=unused-argument
    current_time = get_current_utc_timestamp()

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
            reason=message.tasks.SubtaskResultsRejected.REASON.VerificationNegative,
            report_computed_task_size=result_file_size_1,
            report_computed_task_package_hash=result_file_check_sum_1,
            task_to_compute_size=source_file_size_2,
            task_to_compute_package_hash=source_file_check_sum_2,
            requestor_ethereum_public_key=b'33' * 64,
            provider_ethereum_public_key=b'32' * 64,
            price=0
        ),
        headers = {
            'Content-Type': 'application/octet-stream',
        },
        expected_status=200,
        expected_message_type=message.concents.ServiceRefused,
        expected_content_type='application/octet-stream',
    )


@count_fails
def test_case_6_test_without_script_src_in(
    cluster_consts: ProtocolConstants,
    cluster_url: str,
    task_id: str,
    subtask_id: str,
) -> None:  # pylint: disable=unused-argument
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

    ack_subtask_results_verify = api_request(
        cluster_url,
        'send',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        get_subtask_results_verify(
            task_id,
            subtask_id,
            current_time,
            reason=message.tasks.SubtaskResultsRejected.REASON.VerificationNegative,
            report_computed_task_size=result_file_size,
            report_computed_task_package_hash=result_file_checksum,
            task_to_compute_size=source_file_size,
            task_to_compute_package_hash=source_file_checksum,
        ),
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
        task_id,
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
        task_id,
        source_file_checksum,
        source_file_size
    ))

    # Adding 10 seconds to time sleep makes us sure that subtask is after deadline.
    time.sleep(CALCULATED_VERIFICATION_TIME * (ADDITIONAL_VERIFICATION_TIME_MULTIPLIER / BLENDER_THREADS))

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
        expected_message_type=message.concents.SubtaskResultsSettled,
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
