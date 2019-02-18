from base64 import b64encode
from logging import getLogger
from typing import List
from typing import Union

from django.conf import settings
from django.db import transaction
from django.db.models import Q

from golem_messages.message import Message
from golem_messages.message.concents import ForcePayment
from golem_messages.message.tasks import SubtaskResultsAccepted

from common.constants import ConcentUseCase
from common.constants import ErrorCode
from common.decorators import non_nesting_atomic
from common.helpers import deserialize_message
from common.helpers import get_current_utc_timestamp
from common.helpers import parse_timestamp_to_utc_datetime
from common.logging import log
from core.exceptions import UnsupportedProtocolVersion
from core.models import DepositClaim
from core.models import PendingResponse
from core.models import Subtask
from core.model_helpers import get_one_or_none
from core.payments import bankster
from core.transfer_operations import store_pending_message
from core.transfer_operations import verify_file_status
from core.utils import hex_to_bytes_convert
from core.utils import is_protocol_version_compatible
from core.validation import is_golem_message_signed_with_key

logger = getLogger(__name__)


def _update_timed_out_subtask(subtask: Subtask) -> None:
    """
    Function called for timed out subtasks - checks state and changes it from one of actives to one of passives
    """

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
        task_to_compute = deserialize_message(subtask.task_to_compute.data.tobytes())
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

        def finalize_claim_for_acceptance_case() -> None:
            finalize_deposit_claim(
                subtask_id=subtask.subtask_id,
                concent_use_case=ConcentUseCase.FORCED_ACCEPTANCE,
                ethereum_address=task_to_compute.requestor_ethereum_address,
            )

        transaction.on_commit(
            finalize_claim_for_acceptance_case,
            using='control',
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

        def finalize_claim_for_additional_verification_case() -> None:
            finalize_deposit_claim(
                subtask_id=subtask.subtask_id,
                concent_use_case=ConcentUseCase.ADDITIONAL_VERIFICATION,
                ethereum_address=task_to_compute.requestor_ethereum_address,
            )
            finalize_deposit_claim(
                subtask_id=subtask.subtask_id,
                concent_use_case=ConcentUseCase.ADDITIONAL_VERIFICATION,
                ethereum_address=task_to_compute.provider_ethereum_address,
            )

        transaction.on_commit(
            finalize_claim_for_additional_verification_case,
            using='control',
        )

    log(
        logger,
        f"Subtask changed it's state from: {subtasks_initial_state} to: {subtask.state}. "
        f"Provider id: {subtask.provider_id}. Requestor id: {subtask.requestor_id}.",
        subtask_id=subtask.subtask_id
    )


def check_compatibility(subtask: Subtask, client_public_key: bytes) -> None:
    if not is_protocol_version_compatible(subtask.task_to_compute.protocol_version):
        error_message = f'Unsupported version of golem messages in stored messages. ' \
            f'Version stored in database is {subtask.task_to_compute.protocol_version}, ' \
            f'Concent version is {settings.MAJOR_MINOR_GOLEM_MESSAGES_VERSION}.'
        log(
            logger,
            error_message,
            subtask_id=subtask.subtask_id,
            client_public_key=client_public_key,
        )
        raise UnsupportedProtocolVersion(
            error_message=error_message,
            error_code=ErrorCode.UNSUPPORTED_PROTOCOL_VERSION)


def update_subtasks_states(subtask: Subtask, client_public_key: bytes) -> None:
    if (
        subtask.state in [state.name for state in Subtask.ACTIVE_STATES] and
        subtask.next_deadline <= parse_timestamp_to_utc_datetime(get_current_utc_timestamp())
    ):
        verify_file_status(subtask=subtask, client_public_key=client_public_key)
        _update_timed_out_subtask(subtask)


def pre_process_message_related_subtasks(
    client_message: Message,
    client_public_key: bytes
) -> None:
    """
    Function gets subtask_id (or more subtask id's if message is ForcePayment) from client message, starts transaction,
    checks if state is active and subtask is timed out (in database query, if it is subtask is locked). If so, file
    status is verified (check additional conditions in verify_file_status) and subtask's state is updated
    """
    subtask_ids_list = []  # type: list

    if isinstance(client_message, ForcePayment):
        for subtask_result_accepted in client_message.subtask_results_accepted_list:
            subtask_ids_list.append(subtask_result_accepted.subtask_id)
    else:
        subtask_ids_list = [client_message.subtask_id]

    for subtask_id in subtask_ids_list:
        with non_nesting_atomic(using='control'):
            subtask = get_one_or_none(
                model_or_query_set=Subtask.objects.select_for_update(),
                subtask_id=subtask_id,
            )
            if subtask is None:
                return
            check_compatibility(subtask, client_public_key)
            update_subtasks_states(subtask, client_public_key)


def update_all_timed_out_subtasks_of_a_client(client_public_key: bytes) -> None:
    """
    Function looks for all subtasks in active state of client. All found subtasks are processed in separate transactions,
    locked in database, file status is verified (check additional conditions in verify_file_status) and subtask's state
    is updated in _update_timed_out_subtask
    """

    encoded_client_public_key = b64encode(client_public_key)

    clients_subtask_list = Subtask.objects.filter(
        Q(requestor__public_key=encoded_client_public_key) | Q(provider__public_key=encoded_client_public_key),
        state__in=[state.name for state in Subtask.ACTIVE_STATES],
    )
    # Check if files are uploaded for all clients subtasks. It is checked for all clients subtasks, not only timeouted.
    for subtask in clients_subtask_list:
        with non_nesting_atomic(using='control'):
            Subtask.objects.select_for_update().filter(subtask_id=subtask.subtask_id)
            verify_file_status(subtask=subtask, client_public_key=client_public_key)

            # Subtask may change it's state to passive (RESULT UPLOADED) in verify_file_status. In this case there
            # is no need to call _update_timed_out_subtask any more. Next_deadline will be set to None, so it is
            # necessary to check it before checking if deadline is exceeded.
            if subtask.next_deadline is not None and subtask.next_deadline <= parse_timestamp_to_utc_datetime(get_current_utc_timestamp()):
                _update_timed_out_subtask(subtask)


def update_subtask_state(subtask: Subtask, state: str, next_deadline: Union[int, float, None] = None) -> None:
    old_state = subtask.state
    subtask.state = state
    subtask.next_deadline = None if next_deadline is None else parse_timestamp_to_utc_datetime(next_deadline)
    subtask.full_clean()
    subtask.save()

    log(
        logger,
        f'Subtask changed its state from {old_state} to {subtask.state}',
        subtask_id=subtask.subtask_id
    )


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


def finalize_deposit_claim(
    subtask_id: str,
    concent_use_case: ConcentUseCase,
    ethereum_address: str,
) -> None:
    deposit_claim: DepositClaim = get_one_or_none(  # type: ignore
        DepositClaim,
        subtask_id=subtask_id,
        concent_use_case=concent_use_case,
        payer_deposit_account__ethereum_address=ethereum_address,
    )

    if deposit_claim is not None:
        bankster.finalize_payment(deposit_claim)


def delete_deposit_claim(
    subtask_id: str,
    concent_use_case: ConcentUseCase,
    ethereum_address: str,
) -> None:
    deposit_claim = get_one_or_none(
        DepositClaim,
        subtask_id=subtask_id,
        concent_use_case=concent_use_case,
        payer_deposit_account__ethereum_address=ethereum_address,
    )

    if deposit_claim is not None:
        bankster.discard_claim(deposit_claim)


def is_state_transition_possible(
    to_: Subtask.SubtaskState,
    from_: Subtask.SubtaskState,
) -> bool:
    return from_ in Subtask.POSSIBLE_TRANSITIONS_TO[to_]  # type: ignore
