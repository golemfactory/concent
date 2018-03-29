from celery import shared_task
from mypy.types         import List

from golem_messages     import message

from utils.helpers      import get_result_file_path
from utils.helpers      import get_source_file_path
from verifier.tasks import verification_order_task
from .models            import VerificationRequest
from .models            import UploadReport
from .models            import UploadRequest


@shared_task
def verification_request_task(
    compute_task_def:   message.ComputeTaskDef,
    files:              List[str],
):
    assert isinstance(compute_task_def, message.ComputeTaskDef)

    # The app creates a new instance of VerificationRequest.
    verification_request = VerificationRequest(
        task_id             = compute_task_def['task_id'],
        subtask_id          = compute_task_def['subtask_id'],
        src_code            = compute_task_def['src_code'],
        extra_data          = compute_task_def['extra_data'],
        short_description   = compute_task_def['short_description'],
        working_directory   = compute_task_def['working_directory'],
        performance         = compute_task_def['performance'],
        docker_images       = compute_task_def['docker_images'],
    )
    verification_request.full_clean()
    verification_request.save()

    # The app creates ne UploadRequest for each file listed in the task.
    for file in files:
        upload_request = UploadRequest(
            path                 = file,
            verification_request = verification_request,
        )
        upload_request.full_clean()
        upload_request.save()

        # If there are already UploadReports corresponding to some files, the app links them together by setting the
        # value of the foreign key in UploadRequest.
        UploadReport.objects.filter(
            path            = file,
            upload_request  = None,
        ).update(
            upload_request = upload_request
        )

    verification_request.refresh_from_db()

    # If all expected files have been uploaded, the app sends verification_order task to the work queue.
    if all([upload_request.upload_reports.exists() for upload_request in UploadRequest.objects.all()]):
        verification_order_task.delay(
            subtask_id          = verification_request.subtask_id,
            src_code            = verification_request.src_code,
            extra_data          = verification_request.extra_data,
            short_description   = verification_request.short_description,
            working_directory   = verification_request.working_directory,
            performance         = verification_request.performance,
            docker_images       = verification_request.docker_images,
            source_file         = get_result_file_path(
                verification_request.task_id,
                verification_request.subtask_id,
            ),
            result_file         = get_source_file_path(
                verification_request.task_id,
                verification_request.subtask_id,
            ),
        )
