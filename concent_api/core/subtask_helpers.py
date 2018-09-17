from base64 import b64encode
from logging import getLogger
from typing import Any
from typing import List
from typing import Optional
from typing import Type
from typing import Union

from django.db import transaction
from django.db.models import Model
from django.db.models import Q
from django.db.models import QuerySet
from django.db.models.base import ModelBase
from django.utils import timezone
from golem_messages.message import Message
from golem_messages.message.concents import ForcePayment
from golem_messages.message.tasks import SubtaskResultsAccepted

from core.models import PendingResponse
from core.models import Subtask
from core.payments import service as payments_service
from core.transfer_operations import store_pending_message
from core.transfer_operations import verify_file_status
from core.validation import is_golem_message_signed_with_key
from core.utils import hex_to_bytes_convert
from common.helpers import deserialize_message
from common.helpers import get_current_utc_timestamp
from common.helpers import parse_timestamp_to_utc_datetime
from common.logging import log_change_subtask_state_name
from common.logging import log_string_message

logger = getLogger(__name__)


def update_timed_out_subtask(subtask: Subtask) -> None:

    subtasks_initial_state = subtask.state
    if subtask.state == Subtask.SubtaskState.FORCING_REPORT.name:  # pylint: disable=no-member
        update_subtask_state(
            subtask=subtask,
            state=Subtask.SubtaskState.REPORTED.name,  # pylint: disable=no-member
        )
        store_pending_message(
            response_type=PendingResponse.ResponseType.ForceReportComputedTaskResponse,
            client_public_key=subtask.provider.public_key_bytes,
            queue=PendingResponse.Queue.Receive,
            subtask=subtask,
        )
        store_pending_message(
            response_type=PendingResponse.ResponseType.VerdictReportComputedTask,
            client_public_key=subtask.requestor.public_key_bytes,
            queue=PendingResponse.Queue.ReceiveOutOfBand,
            subtask=subtask,
        )
    elif subtask.state == Subtask.SubtaskState.FORCING_RESULT_TRANSFER.name:  # pylint: disable=no-member
        update_subtask_state(
            subtask=subtask,
            state=Subtask.SubtaskState.FAILED.name,  # pylint: disable=no-member
        )
        store_pending_message(
            response_type=PendingResponse.ResponseType.ForceGetTaskResultFailed,
            client_public_key=subtask.requestor.public_key_bytes,
            queue=PendingResponse.Queue.Receive,
            subtask=subtask,
        )
    elif subtask.state == Subtask.SubtaskState.FORCING_ACCEPTANCE.name:  # pylint: disable=no-member
        update_subtask_state(
            subtask=subtask,
            state=Subtask.SubtaskState.ACCEPTED.name,  # pylint: disable=no-member
        )
        store_pending_message(
            response_type=PendingResponse.ResponseType.SubtaskResultsSettled,
            client_public_key=subtask.provider.public_key_bytes,
            queue=PendingResponse.Queue.Receive,
            subtask=subtask,
        )
        store_pending_message(
            response_type=PendingResponse.ResponseType.SubtaskResultsSettled,
            client_public_key=subtask.requestor.public_key_bytes,
            queue=PendingResponse.Queue.ReceiveOutOfBand,
            subtask=subtask,
        )
    elif subtask.state == Subtask.SubtaskState.VERIFICATION_FILE_TRANSFER.name:  # pylint: disable=no-member

        update_subtask_state(
            subtask=subtask,
            state=Subtask.SubtaskState.FAILED.name,  # pylint: disable=no-member
        )
        store_pending_message(
            response_type=PendingResponse.ResponseType.SubtaskResultsRejected,
            client_public_key=subtask.provider.public_key_bytes,
            queue=PendingResponse.Queue.ReceiveOutOfBand,
            subtask=subtask,
        )
        store_pending_message(
            response_type=PendingResponse.ResponseType.SubtaskResultsRejected,
            client_public_key=subtask.requestor.public_key_bytes,
            queue=PendingResponse.Queue.ReceiveOutOfBand,
            subtask=subtask,
        )
    elif subtask.state == Subtask.SubtaskState.ADDITIONAL_VERIFICATION.name:  # pylint: disable=no-member
        task_to_compute = deserialize_message(subtask.task_to_compute.data.tobytes())

        # Worker makes a payment from requestor's deposit just like in the forced acceptance use case.
        payments_service.make_force_payment_to_provider(  # pylint: disable=no-value-for-parameter
            requestor_eth_address=task_to_compute.requestor_ethereum_address,
            provider_eth_address=task_to_compute.provider_ethereum_address,
            value=task_to_compute.price,
            payment_ts=get_current_utc_timestamp(),
        )

        update_subtask_state(
            subtask=subtask,
            state=Subtask.SubtaskState.ACCEPTED.name,  # pylint: disable=no-member
        )
        store_pending_message(
            response_type=PendingResponse.ResponseType.SubtaskResultsSettled,
            client_public_key=subtask.provider.public_key_bytes,
            queue=PendingResponse.Queue.ReceiveOutOfBand,
            subtask=subtask,
        )
        store_pending_message(
            response_type=PendingResponse.ResponseType.SubtaskResultsSettled,
            client_public_key=subtask.requestor.public_key_bytes,
            queue=PendingResponse.Queue.ReceiveOutOfBand,
            subtask=subtask,
        )
    log_string_message(
        logger,
        f"Subtask with id: {subtask.subtask_id} changed it's state from: {subtasks_initial_state} to: {subtask.state}. "
        f"Provider id: {subtask.provider_id}. Requestor id: {subtask.requestor_id}."
    )


def update_timed_out_subtasks_in_message(client_message: Message, client_public_key: bytes) -> None:
    if isinstance(client_message, ForcePayment):
        for subtask_result_accepted in client_message.subtask_results_accepted_list:
            _update_timed_out_subtask(subtask_result_accepted.subtask_id, client_public_key)
    else:
        _update_timed_out_subtask(client_message.subtask_id, client_public_key)


def update_all_clients_timed_out_subtasks(client_public_key: bytes) -> None:

    encoded_client_public_key = b64encode(client_public_key)

    clients_subtask_list = Subtask.objects.filter(
        Q(requestor__public_key=encoded_client_public_key) | Q(provider__public_key = encoded_client_public_key),
        state__in=[state.name for state in Subtask.ACTIVE_STATES],
    )

    for subtask in clients_subtask_list:
        with transaction.atomic(using='control'):
            Subtask.objects.select_for_update().filter(subtask_id=subtask.subtask_id)
            if subtask.state_enum == Subtask.SubtaskState.FORCING_RESULT_TRANSFER and subtask.requestor.public_key_bytes == client_public_key:
                verify_file_status(subtask=subtask)

# Subtask may change it's state in verify_file_status, so it is necessary to check the state again. If state will change
# to passive, there is no need to call update_timed_out_subtask any more. State has to be checked first, if is passive
# second condition is not checked. If it would be it will raise Error because of comparing datetime and NoneType
            if subtask.state_enum in Subtask.ACTIVE_STATES and subtask.next_deadline <= timezone.now():
                update_timed_out_subtask(subtask)


@transaction.atomic(using='control')
def _update_timed_out_subtask(
    subtask_id: str,
    client_public_key: bytes,
) -> None:
    try:
        subtask = Subtask.objects.select_for_update().get(
            subtask_id=subtask_id,
            state__in=[state.name for state in Subtask.ACTIVE_STATES],
            next_deadline__lte=timezone.now()
        )
    except Subtask.DoesNotExist:
        return

    if subtask.state_enum == Subtask.SubtaskState.FORCING_RESULT_TRANSFER and client_public_key == subtask.requestor.public_key_bytes:
        verify_file_status(subtask=subtask)

    update_timed_out_subtask(subtask)


def update_subtask_state(subtask: Subtask, state: str, next_deadline: Optional[int] = None) -> None:
    log_change_subtask_state_name(
        logger,
        subtask.state,
        state,
    )
    subtask.state = state
    subtask.next_deadline = None if next_deadline is None else parse_timestamp_to_utc_datetime(next_deadline)
    subtask.full_clean()
    subtask.save()


def are_keys_and_addresses_unique_in_message_subtask_results_accepted(
    subtask_results_accepted_list: List[SubtaskResultsAccepted]
) -> bool:

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


def are_subtask_results_accepted_messages_signed_by_the_same_requestor(
    subtask_results_accepted_list: List[SubtaskResultsAccepted]
) -> bool:
    requestor_public_key = subtask_results_accepted_list[0].task_to_compute.requestor_public_key
    are_all_signed_by_requestor = all(
        is_golem_message_signed_with_key(
            hex_to_bytes_convert(requestor_public_key),
            subtask_results_accepted
        ) for subtask_results_accepted in subtask_results_accepted_list
    )
    return are_all_signed_by_requestor


def get_one_or_none(
    query_set_or_model: Union[Type[Model], QuerySet],
    **conditions: Any
)-> Optional[Model]:
    if isinstance(query_set_or_model, ModelBase):
        instances = query_set_or_model.objects.filter(**conditions)
        assert len(instances) <= 1
        return None if len(instances) == 0 else instances[0]
    else:
        instances = query_set_or_model.filter(**conditions)
        assert len(instances) <= 1
        return None if len(instances) == 0 else instances[0]
