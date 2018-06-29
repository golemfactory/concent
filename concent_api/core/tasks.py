import logging

from celery import shared_task
from mypy.types import Optional

from django.db import DatabaseError
from django.db import transaction

from common.decorators import log_task_errors
from common.decorators import provides_concent_feature
from common.helpers import deserialize_message
from common.helpers import get_current_utc_timestamp
from common.helpers import parse_timestamp_to_utc_datetime
from conductor import tasks
from core.constants import VerificationResult
from core.models import PendingResponse
from core.models import Subtask
from core.payments import base
from core.subtask_helpers import update_subtask_state
from core.transfer_operations import store_pending_message
from core.utils import calculate_subtask_verification_time
from .constants import CELERY_LOCKED_SUBTASK_DELAY
from .constants import MAXIMUM_VERIFICATION_RESULT_TASK_RETRIES
from .constants import VERIFICATION_RESULT_SUBTASK_STATE_ACCEPTED_LOG_MESSAGE
from .constants import VERIFICATION_RESULT_SUBTASK_STATE_FAILED_LOG_MESSAGE
from .constants import VERIFICATION_RESULT_SUBTASK_STATE_UNEXPECTED_LOG_MESSAGE


logger = logging.getLogger(__name__)


@shared_task
@log_task_errors
@transaction.atomic(using='control')
def upload_finished(subtask_id: str):
    try:
        subtask = Subtask.objects.get(subtask_id=subtask_id)
    except Subtask.DoesNotExist:
        logging.error(f'Task `upload_finished` tried to get Subtask object with ID {subtask_id} but it does not exist.')
        return

    report_computed_task = deserialize_message(subtask.report_computed_task.data.tobytes())

    # Check subtask state, if it's VERIFICATION FILE TRANSFER, proceed with the task.
    if subtask.state_enum == Subtask.SubtaskState.VERIFICATION_FILE_TRANSFER:

        # If subtask is past the deadline, processes the timeout.
        if subtask.next_deadline.timestamp() < get_current_utc_timestamp():
            # Worker makes a payment from requestor's deposit just like in the forced acceptance use case.
            base.make_force_payment_to_provider(  # pylint: disable=no-value-for-parameter
                requestor_eth_address=report_computed_task.task_to_compute.requestor_ethereum_address,
                provider_eth_address=report_computed_task.task_to_compute.provider_ethereum_address,
                value=report_computed_task.task_to_compute.price,
                payment_ts=get_current_utc_timestamp(),
            )

            update_subtask_state(
                subtask=subtask,
                state=Subtask.SubtaskState.FAILED.name,  # pylint: disable=no-member
            )

            # Worker adds SubtaskResultsSettled to provider's and requestor's receive queues (both out-of-band)
            for public_key in [subtask.provider.public_key_bytes, subtask.requestor.public_key_bytes]:
                store_pending_message(
                    response_type=PendingResponse.ResponseType.SubtaskResultsSettled,
                    client_public_key=public_key,
                    queue=PendingResponse.Queue.ReceiveOutOfBand,
                    subtask=subtask,
                )

            return

        # Change subtask state to ADDITIONAL VERIFICATION.
        update_subtask_state(
            subtask=subtask,
            state=Subtask.SubtaskState.ADDITIONAL_VERIFICATION.name,  # pylint: disable=no-member
            next_deadline=int(subtask.next_deadline.timestamp()) + calculate_subtask_verification_time(report_computed_task)
        )

        # Add upload_acknowledged task to the work queue.
        tasks.upload_acknowledged.delay(
            subtask_id=subtask_id,
            source_file_size=report_computed_task.task_to_compute.size,
            source_package_hash=report_computed_task.task_to_compute.package_hash,
            result_file_size=report_computed_task.size,
            result_package_hash=report_computed_task.package_hash,
        )

    # If it's ADDITIONAL VERIFICATION, ACCEPTED or FAILED, log a warning and ignore the notification.
    # Processing ends here. This means that it's a duplicate notification.
    elif subtask.state_enum in [
        Subtask.SubtaskState.ADDITIONAL_VERIFICATION,
        Subtask.SubtaskState.ACCEPTED,
        Subtask.SubtaskState.FAILED
    ]:
        logging.warning(
            f'Subtask with ID {subtask_id} is expected to be in `VERIFICATION_FILE_TRANSFER` state, but was in {subtask.state}.'
        )

    # If it's one of the states that can precede verification, report an error. Processing ends here.
    else:
        logging.error(
            f'Subtask with ID {subtask_id} is expected to be in `VERIFICATION_FILE_TRANSFER` state, but was in {subtask.state}.'
        )


@shared_task(bind=True)
@provides_concent_feature('concent-worker')
@transaction.atomic(using='control')
@log_task_errors
def verification_result(
    self,
    subtask_id: str,
    result: str,
    error_message: Optional[str] = None,
    error_code: Optional[str] = None,
):
    logger.info(f'verification_result_task starts with: SUBTASK_ID {subtask_id} -- RESULT {result}')

    assert isinstance(subtask_id, str)
    assert isinstance(result, str)
    assert result in VerificationResult.__members__.keys()
    assert isinstance(error_message, (str, type(None)))
    assert isinstance(error_code, (str, type(None)))

    result_enum = VerificationResult[result]

    assert result_enum != VerificationResult.ERROR or all([error_message, error_code])

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
        task_to_compute = deserialize_message(subtask.task_to_compute.data.tobytes())
        # Worker makes a payment from requestor's deposit just like in the forced acceptance use case.
        base.make_force_payment_to_provider(  # pylint: disable=no-value-for-parameter
            requestor_eth_address=task_to_compute.requestor_ethereum_address,
            provider_eth_address=task_to_compute.provider_ethereum_address,
            value=task_to_compute.price,
            payment_ts=get_current_utc_timestamp(),
        )

        update_subtask_state(
            subtask=subtask,
            state=Subtask.SubtaskState.ACCEPTED.name,  # pylint: disable=no-member
        )
        for public_key in [subtask.provider.public_key_bytes, subtask.requestor.public_key_bytes]:
            store_pending_message(
                response_type=PendingResponse.ResponseType.SubtaskResultsSettled,
                client_public_key=public_key,
                queue=PendingResponse.Queue.ReceiveOutOfBand,
                subtask=subtask,
            )
        return

    if result_enum == VerificationResult.MISMATCH:
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

    elif result_enum in (VerificationResult.MATCH, VerificationResult.ERROR):
        # Worker logs the error code and message
        if result_enum == VerificationResult.ERROR:
            logger.info(
                f'verification_result_task processing error result with: '
                f'SUBTASK_ID {subtask_id} -- RESULT {result_enum.name} -- ERROR MESSAGE {error_message} -- ERROR CODE {error_code}'
            )

        task_to_compute = deserialize_message(subtask.task_to_compute.data.tobytes())

        # Worker makes a payment from requestor's deposit just like in the forced acceptance use case.
        base.make_force_payment_to_provider(  # pylint: disable=no-value-for-parameter
            requestor_eth_address=task_to_compute.requestor_ethereum_address,
            provider_eth_address=task_to_compute.provider_ethereum_address,
            value=task_to_compute.price,
            payment_ts=get_current_utc_timestamp(),
        )

        # Worker adds SubtaskResultsSettled to provider's and requestor's receive queues (both out-of-band)
        for public_key in [subtask.provider.public_key_bytes, subtask.requestor.public_key_bytes]:
            store_pending_message(
                response_type=PendingResponse.ResponseType.SubtaskResultsSettled,
                client_public_key=public_key,
                queue=PendingResponse.Queue.ReceiveOutOfBand,
                subtask=subtask,
            )

        # Worker changes subtask state to ACCEPTED
        update_subtask_state(
            subtask=subtask,
            state=Subtask.SubtaskState.ACCEPTED.name,  # pylint: disable=no-member
        )

    logger.info(f'verification_result_task ends with: SUBTASK_ID {subtask_id} -- RESULT {result_enum.name}')
