from enum import Enum

from celery import shared_task

from verifier.tasks import blender_verification_order
from .models import BlenderSubtaskDefinition
from .models import UploadReport
from .models import VerificationRequest


@shared_task
def blender_verification_request(
    subtask_id:             str,
    source_package_path:    str,
    result_package_path:    str,
    output_format:          Enum,
    scene_file:             str,
):
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
        output_format=output_format,
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
    verification_request.refresh_from_db()

    if (
        verification_request.upload_reports.filter(path=verification_request.source_package_path).exists() and
        verification_request.upload_reports.filter(path=verification_request.result_package_path).exists()
    ):
        # If all expected files have been uploaded, the app sends blender_verification_order task to the work queue.
        blender_verification_order.delay(
            verification_request.subtask_id,
            verification_request.source_package_path,
            verification_request.result_package_path,
            verification_request.blender_subtask_definition.output_format,
            verification_request.blender_subtask_definition.scene_file,
        )
