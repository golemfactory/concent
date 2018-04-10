from django.http.response import HttpResponse

from utils.helpers        import get_result_file_path
from utils.helpers        import get_source_file_path
from verifier.tasks       import verification_order_task
from .models              import UploadReport
from .models              import UploadRequest


def report_upload(_request, file_path):

    # If there's a corresponding UploadRequest, then load it and link it to UploadReport.
    try:
        upload_request = UploadRequest.objects.get(
            path = file_path
        )
    except UploadRequest.DoesNotExist:
        upload_request = None

    # The app creates a new instance of UploadReport in the database.
    upload_report = UploadReport(
        path            = file_path,
        upload_request  = upload_request,
    )
    upload_report.full_clean()
    upload_report.save()

    # If the UploadRequest exists, it's linked with a VerificationRequest.
    # The app gets the VerificationRequest and checks if all UploadRequest instances have reports.
    # If all expected files have been uploaded, the app sends verification_order task to the work queue.
    if (
        upload_request is not None and
        upload_request.verification_request is not None and
        all([
            upload_request.upload_reports.exists()
            for upload_request in upload_request.verification_request.upload_requests.all()
        ])
    ):
        verification_order_task.delay(
            subtask_id          = upload_request.verification_request.subtask_id,
            src_code            = upload_request.verification_request.src_code,
            extra_data          = upload_request.verification_request.extra_data,
            short_description   = upload_request.verification_request.short_description,
            working_directory   = upload_request.verification_request.working_directory,
            performance         = upload_request.verification_request.performance,
            docker_images       = upload_request.verification_request.docker_images,
            source_file         = get_result_file_path(
                upload_request.verification_request.task_id,
                upload_request.verification_request.subtask_id,
            ),
            result_file         = get_source_file_path(
                upload_request.verification_request.task_id,
                upload_request.verification_request.subtask_id,
            ),
        )

    return HttpResponse()
