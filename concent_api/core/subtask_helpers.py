from base64                     import b64encode
from logging import getLogger
from typing import List
from typing import Optional

from django.db.models           import Q
from django.utils               import timezone
from golem_messages.message.tasks import SubtaskResultsAccepted

from core.models                import PendingResponse
from core.models                import Subtask
from core.payments import service as payments_service
from core.transfer_operations   import store_pending_message
from core.transfer_operations   import verify_file_status
from core.validation import is_golem_message_signed_with_key
from core.utils import hex_to_bytes_convert
from common.helpers              import deserialize_message
from common.helpers              import get_current_utc_timestamp
from common.helpers import parse_timestamp_to_utc_datetime
from common                      import logging

logger = getLogger(__name__)


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
        elif subtask.state == Subtask.SubtaskState.VERIFICATION_FILE_TRANSFER.name:  # pylint: disable=no-member
            locked_subtask = Subtask.objects.select_for_update().get(pk=subtask.pk)

            update_subtask_state(
                subtask=locked_subtask,
                state=Subtask.SubtaskState.FAILED.name,  # pylint: disable=no-member
            )
            store_pending_message(
                response_type=PendingResponse.ResponseType.SubtaskResultsRejected,
                client_public_key=locked_subtask.provider.public_key_bytes,
                queue=PendingResponse.Queue.ReceiveOutOfBand,
                subtask=locked_subtask,
            )
            store_pending_message(
                response_type=PendingResponse.ResponseType.SubtaskResultsRejected,
                client_public_key=locked_subtask.requestor.public_key_bytes,
                queue=PendingResponse.Queue.ReceiveOutOfBand,
                subtask=locked_subtask,
            )
        elif subtask.state == Subtask.SubtaskState.ADDITIONAL_VERIFICATION.name:  # pylint: disable=no-member
            locked_subtask = Subtask.objects.select_for_update().get(pk=subtask.pk)
            task_to_compute = deserialize_message(locked_subtask.task_to_compute.data.tobytes())

            # Worker makes a payment from requestor's deposit just like in the forced acceptance use case.
            payments_service.make_force_payment_to_provider(  # pylint: disable=no-value-for-parameter
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
        logger,
        client_public_key,
        clients_subtask_list.count(),
    )


def update_subtask_state(
    subtask,
    state,
    next_deadline: Optional[int] = None
):
    logging.log_change_subtask_state_name(
        logger,
        subtask.state,
        state,
    )
    subtask.state = state
    subtask.next_deadline = None if next_deadline is None else parse_timestamp_to_utc_datetime(next_deadline)
    subtask.full_clean()
    subtask.save()


def are_keys_and_addresses_unique_in_message_subtask_results_accepted(subtask_results_accepted_list: List[SubtaskResultsAccepted]) -> bool:

    unique_requestor_public_keys = set(subtask_results_accepted.task_to_compute.requestor_public_key for subtask_results_accepted in subtask_results_accepted_list)
    unique_requestor_ethereum_addresses = set(subtask_results_accepted.task_to_compute.requestor_ethereum_address for subtask_results_accepted in subtask_results_accepted_list)
    unique_requestor_ethereum_public_keys = set(subtask_results_accepted.task_to_compute.requestor_ethereum_public_key for subtask_results_accepted in subtask_results_accepted_list)

    unique_provider_public_keys = set(subtask_results_accepted.task_to_compute.provider_public_key for subtask_results_accepted in subtask_results_accepted_list)
    unique_provider_ethereum_addresses = set(subtask_results_accepted.task_to_compute.provider_ethereum_address for subtask_results_accepted in subtask_results_accepted_list)
    unique_provider_ethereum_public_keys = set(subtask_results_accepted.task_to_compute.provider_ethereum_public_key for subtask_results_accepted in subtask_results_accepted_list)

    is_requestor_public_key_unique = (len(unique_requestor_public_keys) == 1)
    is_requestor_ethereum_address_unique = (len(unique_requestor_ethereum_addresses) == 1)
    is_requestor_ethereum_public_key_unique = (len(unique_requestor_ethereum_public_keys) == 1)

    is_provider_public_key_unique = (len(unique_provider_public_keys) == 1)
    is_provider_ethereum_address_unique = (len(unique_provider_ethereum_addresses) == 1)
    is_provider_ethereum_public_key_unique = (len(unique_provider_ethereum_public_keys) == 1)

    return (
        is_requestor_public_key_unique and
        is_requestor_ethereum_address_unique and
        is_requestor_ethereum_public_key_unique and
        is_provider_public_key_unique and
        is_provider_ethereum_address_unique and
        is_provider_ethereum_public_key_unique
    )


def are_subtask_results_accepted_messages_signed_by_the_same_requestor(subtask_results_accepted_list: List[SubtaskResultsAccepted]) -> bool:
    requestor_public_key = subtask_results_accepted_list[0].task_to_compute.requestor_public_key
    are_all_signed_by_requestor = all(
        is_golem_message_signed_with_key(
            hex_to_bytes_convert(requestor_public_key),
            subtask_results_accepted
        ) for subtask_results_accepted in subtask_results_accepted_list
    )
    return are_all_signed_by_requestor
