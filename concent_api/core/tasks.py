from logging import getLogger
from celery import shared_task
from celery import Task
from mypy.types import Optional

from django.db import DatabaseError
from django.db import transaction

from common import logging
from common.constants import ConcentUseCase
from common.decorators import log_task_errors
from common.decorators import provides_concent_feature
from common.helpers import deserialize_message
from common.helpers import get_current_utc_timestamp
from common.helpers import parse_datetime_to_timestamp
from common.helpers import parse_timestamp_to_utc_datetime
from conductor import tasks
from core.constants import VerificationResult
from core.exceptions import SubtaskStatusError
from core.models import PendingResponse
from core.models import Subtask
from core.subtask_helpers import delete_deposit_claim
from core.subtask_helpers import finalize_deposit_claim
from core.subtask_helpers import update_subtask_state
from core.transfer_operations import store_pending_message
from core.utils import calculate_concent_verification_time
from .constants import CELERY_LOCKED_SUBTASK_DELAY
from .constants import MAXIMUM_VERIFICATION_RESULT_TASK_RETRIES
from .constants import VERIFICATION_RESULT_SUBTASK_STATE_ACCEPTED_LOG_MESSAGE
from .constants import VERIFICATION_RESULT_SUBTASK_STATE_FAILED_LOG_MESSAGE
from .constants import VERIFICATION_RESULT_SUBTASK_STATE_UNEXPECTED_LOG_MESSAGE


logger = getLogger(__name__)


@shared_task
@log_task_errors
@transaction.atomic(using='control')
def upload_finished(subtask_id: str) -> None:
    try:
        subtask = Subtask.objects.select_for_update().get(subtask_id=subtask_id)
    except Subtask.DoesNotExist:
        logging.log(
            logger,
            f'Task `upload_finished` tried to get Subtask object, but it does not exist.',
            subtask_id=subtask_id,
            logging_level=logging.LoggingLevel.ERROR,
        )
        return

    report_computed_task = deserialize_message(subtask.report_computed_task.data.tobytes())

    # Check subtask state, if it's VERIFICATION FILE TRANSFER, proceed with the task.
    if subtask.state_enum == Subtask.SubtaskState.VERIFICATION_FILE_TRANSFER:

        # If subtask is past the deadline, processes the timeout.
        if parse_datetime_to_timestamp(subtask.next_deadline) < get_current_utc_timestamp():
            # Worker makes a payment from requestor's deposit just like in the forced acceptance use case.

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

            def finalize_claims() -> None:
                finalize_deposit_claim(
                    subtask_id=subtask_id,
                    concent_use_case=ConcentUseCase.ADDITIONAL_VERIFICATION,
                    ethereum_address=report_computed_task.task_to_compute.requestor_ethereum_address,
                )
                finalize_deposit_claim(
                    subtask_id=subtask_id,
                    concent_use_case=ConcentUseCase.ADDITIONAL_VERIFICATION,
                    ethereum_address=report_computed_task.task_to_compute.provider_ethereum_address,
                )

            transaction.on_commit(
                finalize_claims,
                using='control',
            )

            return

        # Change subtask state to ADDITIONAL VERIFICATION.
        update_subtask_state(
            subtask=subtask,
            state=Subtask.SubtaskState.ADDITIONAL_VERIFICATION.name,  # pylint: disable=no-member
            next_deadline=(
                parse_datetime_to_timestamp(subtask.next_deadline) +
                calculate_concent_verification_time(report_computed_task.task_to_compute)
            )
        )

        # Add upload_acknowledged task to the work queue.
        def call_upload_acknowledged() -> None:
            tasks.upload_acknowledged.delay(
                subtask_id=subtask_id,
                source_file_size=report_computed_task.task_to_compute.size,
                source_package_hash=report_computed_task.task_to_compute.package_hash,
                result_file_size=report_computed_task.size,
                result_package_hash=report_computed_task.package_hash,
            )

        transaction.on_commit(call_upload_acknowledged)

    # If it's ADDITIONAL VERIFICATION, ACCEPTED or FAILED, log a warning and ignore the notification.
    # Processing ends here. This means that it's a duplicate notification.
    elif subtask.state_enum in [
        Subtask.SubtaskState.ADDITIONAL_VERIFICATION,
        Subtask.SubtaskState.ACCEPTED,
        Subtask.SubtaskState.FAILED
    ]:
        logging.log(
            logger,
            f'Subtask is expected to be in `VERIFICATION_FILE_TRANSFER` state, but was in {subtask.state}.',
            subtask_id=subtask_id,
            logging_level=logging.LoggingLevel.WARNING,
        )
    # If it's one of the states that can precede verification, report an error. Processing ends here.
    else:
        logging.log(
            logger,
            f'Subtask is expected to be in `VERIFICATION_FILE_TRANSFER` state, but was in {subtask.state}.',
            subtask_id=subtask_id,
            logging_level=logging.LoggingLevel.ERROR,
        )


@shared_task(bind=True)
@provides_concent_feature('concent-worker')
@transaction.atomic(using='control')
@log_task_errors
def verification_result(
    self: Task,
    subtask_id: str,
    result: str,
    error_message: Optional[str] = None,
    error_code: Optional[str] = None,
) -> None:
    logging.log(
        logger,
        f'Verification_result_task starts. Result: {result}',
        subtask_id=subtask_id
    )

    assert isinstance(subtask_id, str)
    assert isinstance(result, str)
    assert result in VerificationResult.__members__.keys()
    assert isinstance(error_message, (str, type(None)))
    assert isinstance(error_code, (str, type(None)))

    result_enum = VerificationResult[result]

    assert result_enum != VerificationResult.ERROR or all([isinstance(error_message, str), isinstance(error_code, str)])

    # Worker locks database row corresponding to the subtask in the subtask table.
    try:
        subtask = Subtask.objects.select_for_update(nowait=True).get(subtask_id=subtask_id)
    except DatabaseError:
        logging.log(
            logger,
            f'Row in database corresponding with Subtask object is already locked.'
            f'retrying task {self.request.retries}/{self.max_retries}',
            subtask_id=subtask_id,
            logging_level=logging.LoggingLevel.WARNING,
        )
        # If the row is already locked, task fails so that Celery can retry later.
        self.retry(
            countdown=CELERY_LOCKED_SUBTASK_DELAY,
            max_retries=MAXIMUM_VERIFICATION_RESULT_TASK_RETRIES,
            throw=False,
        )
        return

    if subtask.state_enum == Subtask.SubtaskState.ACCEPTED:
        logging.log(
            logger,
            VERIFICATION_RESULT_SUBTASK_STATE_ACCEPTED_LOG_MESSAGE.format(subtask_id),
            subtask_id=subtask_id,
            logging_level=logging.LoggingLevel.WARNING
        )
        return

    elif subtask.state_enum == Subtask.SubtaskState.FAILED:
        logging.log(
            logger,
            VERIFICATION_RESULT_SUBTASK_STATE_FAILED_LOG_MESSAGE.format(subtask_id),
            subtask_id=subtask_id,
            logging_level=logging.LoggingLevel.WARNING
        )
        return

    elif subtask.state_enum != Subtask.SubtaskState.ADDITIONAL_VERIFICATION:
        logging.log(
            logger,
            VERIFICATION_RESULT_SUBTASK_STATE_UNEXPECTED_LOG_MESSAGE.format(subtask.state),
            subtask_id=subtask_id,
            logging_level=logging.LoggingLevel.ERROR,
        )
        return

    # If the time is already past next_deadline for the subtask (SubtaskResultsRejected.timestamp + AVCT)
    # worker ignores worker's message and processes the timeout.
    if subtask.next_deadline < parse_timestamp_to_utc_datetime(get_current_utc_timestamp()):
        task_to_compute = deserialize_message(subtask.task_to_compute.data.tobytes())
        # Worker makes a payment from requestor's deposit just like in the forced acceptance use case.

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

        def finalize_claims() -> None:
            finalize_deposit_claim(
                subtask_id=subtask_id,
                concent_use_case=ConcentUseCase.ADDITIONAL_VERIFICATION,
                ethereum_address=task_to_compute.requestor_ethereum_address,
            )
            finalize_deposit_claim(
                subtask_id=subtask_id,
                concent_use_case=ConcentUseCase.ADDITIONAL_VERIFICATION,
                ethereum_address=task_to_compute.provider_ethereum_address,
            )

        transaction.on_commit(
            finalize_claims,
            using='control',
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

        task_to_compute = deserialize_message(subtask.task_to_compute.data.tobytes())

        # Worker changes subtask state to FAILED
        subtask.state = Subtask.SubtaskState.FAILED.name  # pylint: disable=no-member
        subtask.next_deadline = None
        subtask.full_clean()
        subtask.save()

        def finalize_claims() -> None:  # pylint: disable=function-redefined
            delete_deposit_claim(
                subtask_id=subtask_id,
                concent_use_case=ConcentUseCase.ADDITIONAL_VERIFICATION,
                ethereum_address=task_to_compute.requestor_ethereum_address,
            )
            finalize_deposit_claim(
                subtask_id=subtask_id,
                concent_use_case=ConcentUseCase.ADDITIONAL_VERIFICATION,
                ethereum_address=task_to_compute.provider_ethereum_address,
            )

        transaction.on_commit(
            finalize_claims,
            using='control',
        )

    elif result_enum in (VerificationResult.MATCH, VerificationResult.ERROR):
        # Worker logs the error code and message
        if result_enum == VerificationResult.ERROR:
            logging.log(
                logger,
                f'Verification_result_task processing error result with: RESULT {result_enum.name}. ERROR MESSAGE {error_message}. ERROR CODE {error_code}',
                subtask_id=subtask_id,
            )
        task_to_compute = deserialize_message(subtask.task_to_compute.data.tobytes())

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

        def finalize_claims() -> None:  # pylint: disable=function-redefined
            finalize_deposit_claim(
                subtask_id=subtask_id,
                concent_use_case=ConcentUseCase.ADDITIONAL_VERIFICATION,
                ethereum_address=task_to_compute.requestor_ethereum_address,
            )
            finalize_deposit_claim(
                subtask_id=subtask_id,
                concent_use_case=ConcentUseCase.ADDITIONAL_VERIFICATION,
                ethereum_address=task_to_compute.provider_ethereum_address,
            )

        transaction.on_commit(
            finalize_claims,
            using='control',
        )

    logging.log(
        logger,
        f'Verification_result_task ends. Result: {result_enum.name}',
        subtask_id=subtask_id
    )


@shared_task(bind=True)
@provides_concent_feature('concent-worker')
@transaction.atomic(using='control')
@log_task_errors
def result_upload_finished(self: Task, subtask_id: str) -> None:
    logging.log(
        logger,
        f'result_upload_finished starts',
        subtask_id=subtask_id
    )

    assert isinstance(subtask_id, str)

    # Worker locks database row corresponding to the subtask in the subtask table.
    try:
        subtask = Subtask.objects.select_for_update(nowait=True).get(subtask_id=subtask_id)
    except DatabaseError:
        logging.log(
            logger,
            f'Row in database corresponding with Subtask object is already locked.'
            f'retrying task {self.request.retries}/{self.max_retries}',
            subtask_id=subtask_id,
            logging_level=logging.LoggingLevel.WARNING
        )
        # If the row is already locked, task fails so that Celery can retry later.
        self.retry(
            countdown=CELERY_LOCKED_SUBTASK_DELAY,
            max_retries=MAXIMUM_VERIFICATION_RESULT_TASK_RETRIES,
            throw=False,
        )
        return

    if subtask.state_enum in [
        Subtask.SubtaskState.REPORTED,
        Subtask.SubtaskState.FORCING_REPORT,
    ]:
        logging.log(
            logger,
            f'result_upload_finished called for Subtask but it has status {subtask.state} instead of `FORCING_RESULT_TRANSFER`.',
            subtask_id=subtask_id,
            logging_level=logging.LoggingLevel.ERROR
        )
        raise SubtaskStatusError(
            f'result_upload_finished called for Subtask with ID `{subtask_id}` but it has status {subtask.state} instead of `FORCING_RESULT_TRANSFER`.'
        )
    elif subtask.state_enum == Subtask.SubtaskState.FAILED:
        logging.log(
            logger,
            f'result_upload_finished called for Subtask, but it has status FAILED.',
            subtask_id=subtask_id,
        )
    elif subtask.state_enum != Subtask.SubtaskState.FORCING_RESULT_TRANSFER:
        logging.log(
            logger,
            f'result_upload_finished called for Subtask but it has status {subtask.state} instead of `FORCING_RESULT_TRANSFER`.',
            subtask_id=subtask_id,
            logging_level=logging.LoggingLevel.WARNING
        )

    subtask.result_upload_finished = True
    subtask.full_clean()
    subtask.save()
