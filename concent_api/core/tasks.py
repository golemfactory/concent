import logging

from celery import shared_task

from conductor import tasks
from core.models import PendingResponse
from core.models import Subtask
from core.payments import base
from core.subtask_helpers import update_subtask_state
from core.transfer_operations import store_pending_message
from utils.helpers import deserialize_message
from utils.helpers import get_current_utc_timestamp


logger = logging.getLogger(__name__)


@shared_task
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
        subtask.state = Subtask.SubtaskState.ADDITIONAL_VERIFICATION.name  # pylint: disable=no-member
        subtask.full_clean()
        subtask.save()

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
