from base64                     import b64encode
from django.db.models           import Q
from django.utils               import timezone

from core.models                import PendingResponse
from core.models                import Subtask
from core.payments              import base
from core.transfer_operations   import store_pending_message
from core.transfer_operations   import verify_file_status
from utils.helpers              import deserialize_message
from utils.helpers              import get_current_utc_timestamp
from utils                      import logging


def update_timed_out_subtasks(
    client_public_key: bytes,
):
    verify_file_status(client_public_key)

    clients_subtask_list = Subtask.objects.filter(
        Q(requestor__public_key = b64encode(client_public_key)) | Q(provider__public_key = b64encode(client_public_key)),
        state__in               = [state.name for state in Subtask.ACTIVE_STATES],
        next_deadline__lte      = timezone.now()
    )

    for subtask in clients_subtask_list:
        if subtask.state == Subtask.SubtaskState.FORCING_REPORT.name:  # pylint: disable=no-member
            update_subtask_state(
                subtask                 = subtask,
                state                   = Subtask.SubtaskState.REPORTED.name,  # pylint: disable=no-member
            )
            store_pending_message(
                response_type       = PendingResponse.ResponseType.ForceReportComputedTaskResponse,
                client_public_key   = subtask.provider.public_key_bytes,
                queue               = PendingResponse.Queue.Receive,
                subtask             = subtask,
            )
            store_pending_message(
                response_type       = PendingResponse.ResponseType.VerdictReportComputedTask,
                client_public_key   = subtask.requestor.public_key_bytes,
                queue               = PendingResponse.Queue.ReceiveOutOfBand,
                subtask             = subtask,
            )
        elif subtask.state == Subtask.SubtaskState.FORCING_RESULT_TRANSFER.name:  # pylint: disable=no-member
            update_subtask_state(
                subtask                 = subtask,
                state                   = Subtask.SubtaskState.FAILED.name,  # pylint: disable=no-member
            )
            store_pending_message(
                response_type       = PendingResponse.ResponseType.ForceGetTaskResultFailed,
                client_public_key   = subtask.requestor.public_key_bytes,
                queue               = PendingResponse.Queue.Receive,
                subtask             = subtask,
            )
        elif subtask.state == Subtask.SubtaskState.FORCING_ACCEPTANCE.name:  # pylint: disable=no-member
            update_subtask_state(
                subtask                 = subtask,
                state                   = Subtask.SubtaskState.ACCEPTED.name,  # pylint: disable=no-member
            )
            store_pending_message(
                response_type       = PendingResponse.ResponseType.SubtaskResultsSettled,
                client_public_key   = subtask.provider.public_key_bytes,
                queue               = PendingResponse.Queue.Receive,
                subtask             = subtask,
            )
            store_pending_message(
                response_type       = PendingResponse.ResponseType.SubtaskResultsSettled,
                client_public_key   = subtask.requestor.public_key_bytes,
                queue               = PendingResponse.Queue.ReceiveOutOfBand,
                subtask             = subtask,
            )
        elif subtask.state == Subtask.SubtaskState.ADDITIONAL_VERIFICATION.name:  # pylint: disable=no-member
            locked_subtask = Subtask.objects.select_for_update().get(pk=subtask.pk)
            task_to_compute = deserialize_message(locked_subtask.task_to_compute.data.tobytes())

            # Worker makes a payment from requestor's deposit just like in the forced acceptance use case.
            base.make_force_payment_to_provider(  # pylint: disable=no-value-for-parameter
                requestor_eth_address=task_to_compute.requestor_ethereum_address,
                provider_eth_address=task_to_compute.provider_ethereum_address,
                value=task_to_compute.price,
                payment_ts=get_current_utc_timestamp(),
            )

            update_subtask_state(
                subtask                 = locked_subtask,
                state                   = Subtask.SubtaskState.ACCEPTED.name,  # pylint: disable=no-member
            )
            store_pending_message(
                response_type       = PendingResponse.ResponseType.SubtaskResultsSettled,
                client_public_key   = locked_subtask.provider.public_key_bytes,
                queue               = PendingResponse.Queue.ReceiveOutOfBand,
                subtask             = locked_subtask,
            )
            store_pending_message(
                response_type       = PendingResponse.ResponseType.SubtaskResultsSettled,
                client_public_key   = locked_subtask.requestor.public_key_bytes,
                queue               = PendingResponse.Queue.ReceiveOutOfBand,
                subtask             = locked_subtask,
            )

    logging.log_changes_in_subtask_states(
        b64encode(client_public_key),
        clients_subtask_list.count(),
    )


def update_subtask_state(
    subtask,
    state,
):
    logging.log_change_subtask_state_name(
        subtask.state,
        state,
    )
    subtask.state    = state
    subtask.next_deadline = None
    subtask.full_clean()
    subtask.save()


def verify_message_subtask_results_accepted(subtask_results_accepted_list: dict) -> bool:
    """
    function verify if all requestor public key and ethereum public key
    in subtask_reesults_accepted_list are the same
    """
    verify_public_key           = len(set(subtask_results_accepted.task_to_compute.requestor_public_key             for subtask_results_accepted in subtask_results_accepted_list)) == 1
    verify_ethereum_public_key  = len(set(subtask_results_accepted.task_to_compute.requestor_ethereum_public_key    for subtask_results_accepted in subtask_results_accepted_list)) == 1
    return bool(verify_public_key is True and verify_ethereum_public_key is True)
