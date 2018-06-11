import logging

from celery import shared_task

from core.models import Subtask
from utils.decorators import provides_concent_feature
from utils.helpers import deserialize_message
from verifier.tasks import blender_verification_order
from .models import BlenderSubtaskDefinition
from .models import UploadReport
from .models import VerificationRequest


logger = logging.getLogger(__name__)


@shared_task
@provides_concent_feature('conductor-worker')
def blender_verification_request(
    subtask_id:             str,
    source_package_path:    str,
    result_package_path:    str,
    output_format:          str,
    scene_file:             str,
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

    # # The app checks if files indicated by source_package_path
    # # and result_package_path in the VerificationRequest have reports.
    # verification_request.refresh_from_db()
    #
    # try:
    #     subtask = Subtask.objects.get(
    #         subtask_id = subtask_id,
    #     )
    # except Subtask.DoesNotExist:
    #     logger.error(f'Task `blender_verification_request` tried to get Subtask object with ID {subtask_id} but it does not exist.')
    #     return
    #
    # report_computed_task = deserialize_message(subtask.report_computed_task.data.tobytes())
    #
    # if (
    #     verification_request.upload_reports.filter(path=verification_request.source_package_path).exists() and
    #     verification_request.upload_reports.filter(path=verification_request.result_package_path).exists()
    # ):
    #     # If all expected files have been uploaded, the app sends blender_verification_order task to the work queue.
    #     blender_verification_order.delay(
    #         verification_request.subtask_id,
    #         verification_request.source_package_path,
    #         report_computed_task.task_to_compute.size,
    #         report_computed_task.task_to_compute.package_hash,
    #         verification_request.result_package_path,
    #         report_computed_task.size,
    #         report_computed_task.package_hash,
    #         verification_request.blender_subtask_definition.output_format,
    #         verification_request.blender_subtask_definition.scene_file,
    #     )


@shared_task
def upload_acknowledged(subtask_id: str):
    assert isinstance(subtask_id, str)

    try:
        verification_request = VerificationRequest.objects.get(subtask_id=subtask_id)
    except VerificationRequest.DoesNotExist:
        logging.error(
            f'Task `upload_acknowledged` tried to get VerificationRequest object with ID {subtask_id} but it does not exist.'
        )
        return

    try:
        subtask = Subtask.objects.get(
            subtask_id=subtask_id,
        )
    except Subtask.DoesNotExist:
        logger.error(
            f'Task `blender_verification_request` tried to get Subtask object with ID {subtask_id} but it does not exist.'
        )
        return

    verification_request.upload_acknowledged = True
    verification_request.full_clean()
    verification_request.save()

    report_computed_task = deserialize_message(subtask.report_computed_task.data.tobytes())

    blender_verification_order.delay(
        verification_request.subtask_id,
        verification_request.source_package_path,
        report_computed_task.task_to_compute.size,
        report_computed_task.task_to_compute.package_hash,
        verification_request.result_package_path,
        report_computed_task.size,
        report_computed_task.package_hash,
        verification_request.blender_subtask_definition.output_format,
        verification_request.blender_subtask_definition.scene_file,
    )
