import logging

from celery import shared_task

from core import tasks
from utils.constants import ErrorCode
from utils.decorators import provides_concent_feature
from verifier.tasks import blender_verification_order
from .exceptions import VerificationRequestAlreadyAcknowledgedError
from .models import BlenderSubtaskDefinition
from .models import UploadReport
from .models import VerificationRequest


logger = logging.getLogger(__name__)


@shared_task
@provides_concent_feature('conductor-worker')
def blender_verification_request(
    subtask_id: str,
    source_package_path: str,
    result_package_path: str,
    output_format: str,
    scene_file: str,
    blender_crop_script: str,
):
    assert isinstance(output_format, str)

    output_format = output_format.upper()
    assert output_format in BlenderSubtaskDefinition.OutputFormat.__members__.keys()

    # The app creates a new instance of VerificationRequest in the database
    # and a BlenderSubtaskDefinition instance associated with it.
    verification_request = VerificationRequest(
        subtask_id=subtask_id,
        source_package_path=source_package_path,
        result_package_path=result_package_path,
    )
    verification_request.full_clean()
    verification_request.save()

    blender_subtask_definition = BlenderSubtaskDefinition(
        verification_request=verification_request,
        output_format=BlenderSubtaskDefinition.OutputFormat[output_format].name,
        scene_file=scene_file,
        blender_crop_script=blender_crop_script,
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
        # If all expected files have been uploaded, the app sends upload_finished task to the work queue.
        tasks.upload_finished.delay(verification_request.subtask_id)

        verification_request.upload_finished = True
        verification_request.full_clean()
        verification_request.save()


@shared_task
def upload_acknowledged(
    subtask_id: str,
    source_file_size: str,
    source_package_hash: str,
    result_file_size: str,
    result_package_hash: str,
):
    assert isinstance(subtask_id, str)

    try:
        verification_request = VerificationRequest.objects.get(subtask_id=subtask_id)
    except VerificationRequest.DoesNotExist:
        logging.error(
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
        blender_crop_script=verification_request.blender_subtask_definition.blender_crop_script,
    )
