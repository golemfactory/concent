from logging import getLogger

from django.db import transaction
from django.db.models import Q
from django.http.request import HttpRequest
from django.http.response import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from golem_messages.message.concents import FileTransferToken

from common.decorators import provides_concent_feature
from common.logging import log_request_received
from common.logging import log
from conductor.models import ResultTransferRequest
from conductor.models import UploadReport
from conductor.models import VerificationRequest
from conductor.service import update_upload_report
from core.tasks import upload_finished

logger = getLogger(__name__)


@provides_concent_feature('conductor-urls')
@require_POST
@csrf_exempt
@transaction.atomic(using='storage')
def report_upload(_request: HttpRequest, file_path: str) -> HttpResponse:

    log_request_received(logger,  file_path, FileTransferToken.Operation.upload)
    # If there's a corresponding VerificationRequest, the load it and link it to UploadReport.
    try:
        verification_request = VerificationRequest.objects.select_for_update().get(
            Q(source_package_path=file_path) | Q(result_package_path=file_path)
        )
    except VerificationRequest.DoesNotExist:
        verification_request = None

    # The app creates a new instance of UploadReport in the database.
    upload_report = UploadReport(
        path = file_path,
        verification_request = verification_request,
    )
    upload_report.full_clean()
    upload_report.save()

    # The app gets the VerificationRequest and checks if both source and result packages have reports.
    if (
        verification_request is not None and
        verification_request.blender_subtask_definition is not None and
        verification_request.upload_reports.filter(path=verification_request.source_package_path).exists() and
        verification_request.upload_reports.filter(path=verification_request.result_package_path).exists() and
        verification_request.upload_reports.filter(path=file_path).count() == 1
    ):
        assert file_path in [verification_request.source_package_path, verification_request.result_package_path]

        verification_request.upload_finished = True
        verification_request.full_clean()
        verification_request.save()

        # If all expected files have been uploaded, the app sends upload_finished task to the work queue.
        def call_upload_finished() -> None:
            upload_finished.delay(verification_request.subtask_id)

        transaction.on_commit(call_upload_finished, using='control')

        log(
            logger, 'All expected files have been uploaded',
            f'Result package path: {verification_request.result_package_path}.'
            f'Source package path: {verification_request.source_package_path}.',
            subtask_id=verification_request.subtask_id
        )

    # If ResultTransferRequest matching the file exists, report finished upload.
    result_transfer_request = ResultTransferRequest.objects.filter(result_package_path=file_path).first()
    if result_transfer_request is not None:
        update_upload_report(
            file_path=file_path,
            result_transfer_request=result_transfer_request,
        )

    return HttpResponse()
