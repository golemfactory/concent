import logging

from django.db.models import Q

from common.constants import ErrorCode
from common.logging import log_string_message, LoggingLevel
from conductor.exceptions import VerificationRequestAlreadyInitiatedError
from conductor.models import ResultTransferRequest
from conductor.models import UploadReport
from conductor.models import VerificationRequest
from core.tasks import result_upload_finished


logger = logging.getLogger(__name__)


def update_upload_report(file_path: str, result_transfer_request: ResultTransferRequest) -> None:
    """
    Updates UploadReport objects with `path` related to given file path
    and schedules `result_upload_finished` task if not scheduled before.

    """

    assert isinstance(file_path, str)
    assert isinstance(result_transfer_request, ResultTransferRequest)

    UploadReport.objects.select_for_update().filter(
        path=file_path
    ).update(
        result_transfer_request=result_transfer_request
    )

    if result_transfer_request.upload_finished is False:
        # If both ResultTransferRequest and BlenderVerificationRequest that refer to the same file exist,
        # and they both have upload_finished set to False, crash with an error. It should not happen.
        if VerificationRequest.objects.filter(
            Q(source_package_path=file_path) | Q(result_package_path=file_path),
            upload_finished=False,
        ).exists():
            log_string_message(
                logger,
                f'`update_upload_report` called but VerificationRequest with ID {result_transfer_request.subtask_id} is already initiated.',
                subtask_id=result_transfer_request.subtask_id,
                logging_level=LoggingLevel.ERROR,
            )
            raise VerificationRequestAlreadyInitiatedError(
                f'`update_upload_report` called but VerificationRequest with ID {result_transfer_request.subtask_id} is already initiated.',
                ErrorCode.CONDUCTOR_VERIFICATION_REQUEST_ALREADY_INITIATED
            )

        result_transfer_request.upload_finished = True
        result_transfer_request.full_clean()
        result_transfer_request.save()

        result_upload_finished.delay(result_transfer_request.subtask_id)
