import logging
from celery import shared_task
from django.db import transaction

from core import tasks
from common.constants import ErrorCode
from common.decorators import log_task_errors
from common.decorators import provides_concent_feature
from common.helpers import parse_timestamp_to_utc_datetime
from common.logging import log_error_message
from common.logging import log_string_message
from verifier.tasks import blender_verification_order
from .exceptions import VerificationRequestAlreadyAcknowledgedError
from .models import BlenderSubtaskDefinition
from .models import UploadReport
from .models import VerificationRequest


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
):
    log_string_message(
        logger,
        f'Blender verification request starts. SUBTASK_ID: {subtask_id}',
        f'Source_package_path {source_package_path}',
        f'Result_package_path: {result_package_path}',
        f'Output_format: {output_format}',
        f'Scene_file: {scene_file}'
    )
    assert isinstance(output_format, str)
    assert isinstance(verification_deadline, int)

    output_format = output_format.upper()
    assert output_format in BlenderSubtaskDefinition.OutputFormat.__members__.keys()

    # The app creates a new instance of VerificationRequest in the database
    # and a BlenderSubtaskDefinition instance associated with it.
    verification_request = VerificationRequest(
        subtask_id=subtask_id,
        source_package_path=source_package_path,
        result_package_path=result_package_path,
        verification_deadline=parse_timestamp_to_utc_datetime(verification_deadline),
    )
    verification_request.full_clean()
    verification_request.save()

    blender_subtask_definition = BlenderSubtaskDefinition(
        verification_request=verification_request,
        output_format=BlenderSubtaskDefinition.OutputFormat[output_format].name,
        scene_file=scene_file,
    )
    blender_subtask_definition.full_clean()
    blender_subtask_definition.save()

    # If there are already UploadReports corresponding to some files, the app links them with the VerificationRequest
    # by setting the value of the foreign key in UploadReport.
    for path in [source_package_path, result_package_path]:
        UploadReport.objects.filter(
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
        log_string_message(
            logger, 'All expected files have been uploaded',
            f'Subtask ID: {verification_request.subtask_id}'
            f'Result package path: {verification_request.result_package_path}'
            f'Source package path: {verification_request.source_package_path}'
        )
        # If all expected files have been uploaded, the app sends upload_finished task to the work queue.
        tasks.upload_finished.delay(verification_request.subtask_id)

        verification_request.upload_finished = True
        verification_request.full_clean()
        verification_request.save()


@shared_task
@log_task_errors
@transaction.atomic(using='storage')
def upload_acknowledged(
    subtask_id: str,
    source_file_size: str,
    source_package_hash: str,
    result_file_size: str,
    result_package_hash: str,
):
    log_string_message(
        logger,
        f'Upload acknowledgment starts. SUBTASK_ID: {subtask_id}',
        f'Source_file_size {source_file_size}',
        f'Source_package_hash: {source_package_hash}',
        f'Result_file_size: {result_file_size}',
        f'Result_package_hash: {result_package_hash}'
    )
    assert isinstance(subtask_id, str)

    try:
        verification_request = VerificationRequest.objects.get(subtask_id=subtask_id)
    except VerificationRequest.DoesNotExist:
        log_error_message(
            logger,
            f'Task `upload_acknowledged` tried to get VerificationRequest object with ID {subtask_id} but it does not exist.'
        )
        return

    if verification_request.upload_acknowledged is True:
        logging.error(
            f'Task `upload_acknowledged` scheduled but VerificationRequest with with ID {subtask_id} is already acknowledged.'
        )
        raise VerificationRequestAlreadyAcknowledgedError(
            f'Task `upload_acknowledged` scheduled but VerificationRequest with with ID {subtask_id} is already acknowledged.',
            ErrorCode.CONDUCTOR_VERIFICATION_REQUEST_ALREADY_ACKNOWLEDGED
        )
    else:
        verification_request.upload_acknowledged = True
        verification_request.full_clean()
        verification_request.save()

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
        verification_deadline=int(verification_request.verification_deadline.timestamp()),
    )
    log_string_message(
        logger,
        f'Upload acknowledgment finished. SUBTASK_ID: {subtask_id}',
        f'Source_file_size {source_file_size}',
        f'Source_package_hash: {source_package_hash}',
        f'Result_file_size: {result_file_size}',
        f'Result_package_hash: {result_package_hash}'
    )
