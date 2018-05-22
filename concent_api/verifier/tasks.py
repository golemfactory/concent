from enum import Enum
import logging

from celery import shared_task
from mypy.types import Optional

from django.db import DatabaseError
from django.db import transaction

from core.transfer_operations import store_pending_message
from core.models import PendingResponse
from core.models import Subtask
from utils.constants import ErrorCode
from utils.helpers import get_current_utc_timestamp
from utils.helpers import parse_timestamp_to_utc_datetime
from .constants import VerificationResult
from .constants import CELERY_LOCKED_SUBTASK_DELAY
from .constants import MAXIMUM_VERIFICATION_RESULT_TASK_RETRIES
from .constants import VERIFICATION_RESULT_SUBTASK_STATE_ACCEPTED_LOG_MESSAGE
from .constants import VERIFICATION_RESULT_SUBTASK_STATE_FAILED_LOG_MESSAGE
from .constants import VERIFICATION_RESULT_SUBTASK_STATE_UNEXPECTED_LOG_MESSAGE


logger = logging.getLogger(__name__)


@shared_task
def blender_verification_order(
    subtask_id:             str,
    source_package_path:    str,  # pylint: disable=unused-argument
    result_package_path:    str,  # pylint: disable=unused-argument
    output_format:          Enum,  # pylint: disable=unused-argument
    scene_file:             str,  # pylint: disable=unused-argument
):
    verification_result.delay(
        subtask_id,
        VerificationResult.MATCH,
    )


@shared_task(bind=True)
@transaction.atomic(using='control')
def verification_result(
    self,
    subtask_id:     str,
    result:         VerificationResult,
    error_message:  Optional[str] = None,
    error_code:     Optional[ErrorCode] = None,
):
    logger.info(f'verification_result_task starts with: SUBTASK_ID {subtask_id} -- RESULT {result}')

    assert isinstance(subtask_id, str)
    assert isinstance(result, VerificationResult)
    assert isinstance(error_message, (str, type(None)))
    assert isinstance(error_code, (ErrorCode, type(None)))
    assert all([error_message, error_code]) if result == VerificationResult.ERROR else True

    # Worker locks database row corresponding to the subtask in the subtask table.
    try:
        subtask = Subtask.objects.select_for_update(nowait=True).get(subtask_id=subtask_id)
    except DatabaseError:
        logging.warning(
            f'Subtask object with ID {subtask_id} database row is locked, '
            f'retrying task {self.request.retries}/{self.max_retries}'
        )
        # If the row is already locked, task fails so that Celery can retry later.
        self.retry(
            countdown=CELERY_LOCKED_SUBTASK_DELAY,
            max_retries=MAXIMUM_VERIFICATION_RESULT_TASK_RETRIES,
            throw=False,
        )
        return

    if subtask.state_enum == Subtask.SubtaskState.ACCEPTED:
        logger.warning(VERIFICATION_RESULT_SUBTASK_STATE_ACCEPTED_LOG_MESSAGE.format(subtask_id))
        return

    elif subtask.state_enum == Subtask.SubtaskState.FAILED:
        logger.warning(VERIFICATION_RESULT_SUBTASK_STATE_FAILED_LOG_MESSAGE.format(subtask_id))
        return

    elif subtask.state_enum != Subtask.SubtaskState.ADDITIONAL_VERIFICATION:
        logger.error(VERIFICATION_RESULT_SUBTASK_STATE_UNEXPECTED_LOG_MESSAGE.format(subtask_id, subtask.state))
        return

    # If the time is already past next_deadline for the subtask (SubtaskResultsRejected.timestamp + AVCT)
    # worker ignores worker's message and processes the timeout.
    if subtask.next_deadline < parse_timestamp_to_utc_datetime(get_current_utc_timestamp()):
        pass  # TODO: Process timeout here

    if result == VerificationResult.MISMATCH:
        # Worker adds SubtaskResultsRejected to provider's and requestor's receive queues (both out-of-band)
        for public_key in [subtask.provider.public_key_bytes, subtask.requestor.public_key_bytes]:
            store_pending_message(
                response_type=PendingResponse.ResponseType.SubtaskResultsRejected,
                client_public_key=public_key,
                queue=PendingResponse.Queue.ReceiveOutOfBand,
                subtask=subtask,
            )

        # Worker changes subtask state to FAILED
        subtask.state = Subtask.SubtaskState.FAILED.name  # pylint: disable=no-member
        subtask.next_deadline = None
        subtask.full_clean()
        subtask.save()

    elif result in (VerificationResult.MATCH, VerificationResult.ERROR):
        # Worker logs the error code and message
        if result == VerificationResult.ERROR:
            logger.info(
                f'verification_result_task processing error result with: '
                f'SUBTASK_ID {subtask_id} -- RESULT {result} -- ERROR MESSAGE {error_message} -- ERROR CODE {error_code}'
            )

        # Worker makes a payment from requestor's deposit just like in the forced acceptance use case.
        # TODO: make payment

        # Worker adds SubtaskResultsSettled to provider's and requestor's receive queues (both out-of-band)
        for public_key in [subtask.provider.public_key_bytes, subtask.requestor.public_key_bytes]:
            store_pending_message(
                response_type=PendingResponse.ResponseType.SubtaskResultsSettled,
                client_public_key=public_key,
                queue=PendingResponse.Queue.ReceiveOutOfBand,
                subtask=subtask,
            )

        # Worker changes subtask state to ACCEPTED
        subtask.state = Subtask.SubtaskState.ACCEPTED.name  # pylint: disable=no-member
        subtask.next_deadline = None
        subtask.full_clean()
        subtask.save()

    logger.info(f'verification_result_task ends with: SUBTASK_ID {subtask_id} -- RESULT {result}')
