import logging
from typing import List

from celery import shared_task
from django.db import transaction
from mypy.types import Optional


from common.constants import ErrorCode
from common.decorators import log_task_errors
from common.decorators import provides_concent_feature
from common.helpers import parse_datetime_to_timestamp
from common.logging import log
from common.logging import LoggingLevel
from conductor.exceptions import VerificationRequestAlreadyAcknowledgedError
from conductor.models import BlenderSubtaskDefinition
from conductor.models import ResultTransferRequest
from conductor.models import UploadReport
from conductor.models import VerificationRequest
from conductor.service import filter_frames_by_blender_subtask_definition
from conductor.service import store_frames
from conductor.service import store_verification_request_and_blender_subtask_definition
from conductor.service import update_upload_report
from core import tasks
from core.validation import validate_frames
from verifier.tasks import blender_verification_order

logger = logging.getLogger(__name__)


@shared_task
@provides_concent_feature('conductor-worker')
@log_task_errors
@transaction.atomic(using='storage')
def blender_verification_request(
    subtask_id: str,
    source_package_path: str,
    result_package_path: str,
    output_format: str,
    scene_file: str,
    verification_deadline: int,
    frames: List[int],
    blender_crop_script: Optional[str],
) -> None:
    log(
        logger,
        f'Blender verification request starts.',
        f'Source_package_path {source_package_path}',
        f'Result_package_path: {result_package_path}',
        f'Output_format: {output_format}',
        f'Scene_file: {scene_file}',
        f'Frames: {frames}',
        f'Verification_deadline: {verification_deadline}',
        f'With blender_crop_script: {bool(blender_crop_script)}',
        subtask_id=subtask_id
    )
    validate_frames(frames)
    assert isinstance(output_format, str)
    assert isinstance(verification_deadline, int)

    output_format = output_format.upper()
    assert output_format in BlenderSubtaskDefinition.OutputFormat.__members__.keys()

    # The app creates a new instance of VerificationRequest in the database
    # and a BlenderSubtaskDefinition instance associated with it.
    (verification_request, blender_subtask_definition) = store_verification_request_and_blender_subtask_definition(
        subtask_id=subtask_id,
        source_package_path=source_package_path,
        result_package_path=result_package_path,
        verification_deadline=verification_deadline,
        output_format=output_format,
        scene_file=scene_file,
        blender_crop_script=blender_crop_script,
    )

    store_frames(
        blender_subtask_definition=blender_subtask_definition,
        frame_list=frames,
    )

    # If there are already UploadReports corresponding to some files, the app links them with the VerificationRequest
    # by setting the value of the foreign key in UploadReport.
    for path in [source_package_path, result_package_path]:
        UploadReport.objects.select_for_update().filter(
            path=path,
            verification_request=None,
        ).update(
            verification_request=verification_request
        )

    # The app checks if files indicated by source_package_path
    # and result_package_path in the VerificationRequest have reports.
    if (
        verification_request.upload_reports.filter(path=verification_request.source_package_path).exists() and
        verification_request.upload_reports.filter(path=verification_request.result_package_path).exists()
    ):
        log(
            logger, 'All expected files have been uploaded',
            f'Result package path: {verification_request.result_package_path}'
            f'Source package path: {verification_request.source_package_path}',
            subtask_id=subtask_id

        )

        verification_request.upload_finished = True
        verification_request.full_clean()
        verification_request.save()

        # If all expected files have been uploaded, the app sends upload_finished task to the work queue.
        def call_upload_finished() -> None:
            tasks.upload_finished.delay(verification_request.subtask_id)

        transaction.on_commit(call_upload_finished, using='control')


@shared_task
@log_task_errors
@transaction.atomic(using='storage')
def upload_acknowledged(
    subtask_id: str,
    source_file_size: str,
    source_package_hash: str,
    result_file_size: str,
    result_package_hash: str,
) -> None:
    log(
        logger,
        f'Upload acknowledgment starts.',
        f'Source_file_size {source_file_size}',
        f'Source_package_hash: {source_package_hash}',
        f'Result_file_size: {result_file_size}',
        f'Result_package_hash: {result_package_hash}',
        subtask_id=subtask_id
    )
    assert isinstance(subtask_id, str)

    try:
        verification_request = VerificationRequest.objects.select_for_update().get(subtask_id=subtask_id)
    except VerificationRequest.DoesNotExist:
        log(
            logger,
            f'Task `upload_acknowledged` tried to get VerificationRequest object with ID {subtask_id} but it does not exist.',
            subtask_id=subtask_id,
            logging_level=LoggingLevel.ERROR,
        )
        return

    if verification_request.upload_acknowledged is True:
        log(
            logger,
            f'Task `upload_acknowledged` scheduled but VerificationRequest with with ID {subtask_id} is already acknowledged.',
            subtask_id=subtask_id,
        )
        raise VerificationRequestAlreadyAcknowledgedError(
            f'Task `upload_acknowledged` scheduled but VerificationRequest with with ID {subtask_id} is already acknowledged.',
            ErrorCode.CONDUCTOR_VERIFICATION_REQUEST_ALREADY_ACKNOWLEDGED
        )
    else:
        verification_request.upload_acknowledged = True
        verification_request.full_clean()
        verification_request.save()

    frames = filter_frames_by_blender_subtask_definition(verification_request.blender_subtask_definition)

    def call_blender_verification_order() -> None:
        blender_verification_order.delay(
            subtask_id=verification_request.subtask_id,
            source_package_path=verification_request.source_package_path,
            source_size=source_file_size,
            source_package_hash=source_package_hash,
            result_package_path=verification_request.result_package_path,
            result_size=result_file_size,
            result_package_hash=result_package_hash,
            output_format=verification_request.blender_subtask_definition.output_format,
            scene_file=verification_request.blender_subtask_definition.scene_file,
            verification_deadline=parse_datetime_to_timestamp(verification_request.verification_deadline),
            frames=frames,
            blender_crop_script=verification_request.blender_subtask_definition.blender_crop_script,
        )

    transaction.on_commit(call_blender_verification_order, using='control')

    log(
        logger,
        f'Upload acknowledgment finished.',
        f'Source_file_size {source_file_size}',
        f'Source_package_hash: {source_package_hash}',
        f'Result_file_size: {result_file_size}',
        f'Result_package_hash: {result_package_hash}',
        subtask_id=subtask_id
    )


@shared_task
@provides_concent_feature('conductor-worker')
@log_task_errors
@transaction.atomic(using='storage')
def result_transfer_request(subtask_id: str, result_package_path: str) -> None:
    assert isinstance(subtask_id, str)
    assert isinstance(result_package_path, str)

    result_transfer_request_obj = ResultTransferRequest(
        subtask_id=subtask_id,
        result_package_path=result_package_path,
    )
    result_transfer_request_obj.full_clean()
    result_transfer_request_obj.save()

    if UploadReport.objects.filter(path=result_package_path).exists():
        update_upload_report(
            file_path=result_package_path,
            result_transfer_request=result_transfer_request_obj,
        )
