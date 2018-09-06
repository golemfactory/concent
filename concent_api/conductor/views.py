from logging import getLogger

from django.db.models import Q
from django.http.request import HttpRequest
from django.http.response import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from golem_messages.message.concents import FileTransferToken

from core.tasks import upload_finished
from common.decorators import provides_concent_feature
from common.logging import log_request_received
from common.logging import log_string_message
from .models import UploadReport
from .models import VerificationRequest

logger = getLogger(__name__)


@provides_concent_feature('conductor-urls')
@require_POST
@csrf_exempt
def report_upload(_request: HttpRequest, file_path: str) -> HttpResponse:

    log_request_received(logger,  file_path, FileTransferToken.Operation.upload)
    # If there's a corresponding VerificationRequest, the load it and link it to UploadReport.
    try:
        verification_request = VerificationRequest.objects.get(
            Q(source_package_path=file_path) | Q(result_package_path=file_path)
        )
    except VerificationRequest.DoesNotExist:
        verification_request = None

    # The app creates a new instance of UploadReport in the database.
    upload_report_obj = UploadReport(
        path = file_path,
        verification_request = verification_request,
    )
    upload_report_obj.full_clean()
    upload_report_obj.save()

    # The app gets the VerificationRequest and checks if both source and result packages have reports.
    if (
        verification_request is not None and
        verification_request.blender_subtask_definition is not None and
        verification_request.upload_reports.filter(path=verification_request.source_package_path).exists() and
        verification_request.upload_reports.filter(path=verification_request.result_package_path).exists() and
        verification_request.upload_reports.filter(path=file_path).count() == 1
    ):
        assert file_path in [verification_request.source_package_path, verification_request.result_package_path]

        # If all expected files have been uploaded, the app sends upload_finished task to the work queue.
        upload_finished.delay(verification_request.subtask_id)

        verification_request.upload_finished = True
        verification_request.full_clean()
        verification_request.save()

        log_string_message(
            logger, 'All expected files have been uploaded',
            f'Subtask ID: {verification_request.subtask_id}.'
            f'Result package path: {verification_request.result_package_path}.'
            f'Source package path: {verification_request.source_package_path}.'
        )

    return HttpResponse()
