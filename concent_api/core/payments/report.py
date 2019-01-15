from typing import List
from typing import NamedTuple
from typing import Tuple

from django.db.models import QuerySet
from golem_messages.exceptions import MessageError

from common.helpers import deserialize_message
from common.helpers import get_current_utc_timestamp
from core.exceptions import SCINotSynchronized
from core.models import Client
from core.models import PendingResponse
from core.models import Subtask
from core.payments import service
from core.payments.backends.sci_backend import TransactionType


class PendingResponses(NamedTuple):
    subtask_results_settled: QuerySet
    subtask_results_rejected: QuerySet
    force_payment_committed: QuerySet

    def is_empty(self) -> bool:
        is_subtask_results_settled_empty = self.subtask_results_settled.count() == 0
        is_subtask_results_rejected_empty = self.subtask_results_rejected.count() == 0
        is_force_payment_committed_empty = self.force_payment_committed.count() == 0

        return is_subtask_results_settled_empty and is_subtask_results_rejected_empty and is_force_payment_committed_empty


class Payments(NamedTuple):
    regular_payments: list
    settlement_payments: list
    forced_subtask_payments: list
    requestor_additional_verification_payments: list
    provider_additional_verification_payments: list

    def is_empty(self) -> bool:
        is_regular_payments_empty = len(self.regular_payments) == 0
        is_settlement_payments_empty = len(self.settlement_payments) == 0
        is_forced_subtask_payments_empty = len(self.forced_subtask_payments) == 0
        is_requestor_additional_verification_payments_empty = len(self.requestor_additional_verification_payments) == 0
        is_provider_additional_verification_payments_empty = len(self.provider_additional_verification_payments) == 0

        return is_regular_payments_empty and is_settlement_payments_empty and is_forced_subtask_payments_empty and is_requestor_additional_verification_payments_empty and is_provider_additional_verification_payments_empty


class PairReport(NamedTuple):
    requestor: Client
    provider: Client
    requestor_ethereum_addresses: list
    provider_ethereum_addresses: list
    pending_responses: PendingResponses
    payments: Payments


class ClientEthereumAddresses(NamedTuple):
    provider: str
    requestor: str


class Report(NamedTuple):
    pair_reports: list


def create_report() -> Report:
    """ Create payments report for Concent. """
    pair_reports = []

    for subtask in get_subtasks_with_distinct_clients_pairs():  # pylint: disable=not-an-iterable
        (subtasks_ids, clients_ethereum_addresses) = get_subtask_ids_and_ethereum_addresses_for_clients_pair(
            subtask.requestor,
            subtask.provider,
        )

        related_pending_responses_for_pair = get_related_pending_responses_for_subtasks_ids(
            subtasks_ids,
            subtask.requestor,
            clients_ethereum_addresses,
        )
        try:
            related_payments_for_pair = get_related_payments_for_pair(clients_ethereum_addresses)
        except SCINotSynchronized:
            related_payments_for_pair = Payments([], [], [], [], [])

        if not(related_payments_for_pair.is_empty() and related_pending_responses_for_pair.is_empty()):  # pylint: disable=no-member
            pair_report = PairReport(
                requestor=subtask.requestor,
                provider=subtask.provider,
                requestor_ethereum_addresses=[client_ethereum_address.requestor for client_ethereum_address in clients_ethereum_addresses],
                provider_ethereum_addresses=[client_ethereum_address.provider for client_ethereum_address in clients_ethereum_addresses],
                pending_responses=related_pending_responses_for_pair,
                payments=related_payments_for_pair,
            )
            pair_reports.append(pair_report)

    return Report(pair_reports)


def get_subtasks_with_distinct_clients_pairs() -> QuerySet:
    """ Get Subtasks with distinct pairs of requestor and provider Clients. """
    return Subtask.objects.order_by('provider', 'requestor').distinct('provider', 'requestor')


def get_subtask_ids_and_ethereum_addresses_for_clients_pair(requestor: Client, provider: Client) -> Tuple:
    """ Get Subtasks Ids and all Ethereum keys for Clients pair. """
    subtask_ids = []
    clients_ethereum_addresses = []

    for subtask in Subtask.objects.filter(requestor=requestor, provider=provider):  # pylint: disable=no-member
        subtask_ids.append(subtask.subtask_id)
        try:
            task_to_compute = deserialize_message(subtask.task_to_compute.data.tobytes())
            clients_ethereum_addresses.append(
                ClientEthereumAddresses(
                    task_to_compute.provider_ethereum_address,
                    task_to_compute.requestor_ethereum_address,
                )
            )
        except MessageError:
            pass

    return subtask_ids, list(set(clients_ethereum_addresses))


def get_related_pending_responses_for_subtasks_ids(subtasks_ids: List[str], requestor: Client, clients_ethereum_addresses: list) -> PendingResponses:
    """ Group and return pending responses from Subtask queryset. """
    return PendingResponses(
        subtask_results_settled=PendingResponse.objects.filter(
            response_type=PendingResponse.ResponseType.SubtaskResultsSettled.name,  # pylint: disable=no-member
            subtask__subtask_id__in=subtasks_ids,
        ),
        subtask_results_rejected=PendingResponse.objects.filter(
            response_type=PendingResponse.ResponseType.SubtaskResultsRejected.name,  # pylint: disable=no-member
            subtask__subtask_id__in=subtasks_ids,
        ),
        force_payment_committed=prefetch_payment_info(
            PendingResponse.objects.filter(
                response_type=PendingResponse.ResponseType.ForcePaymentCommitted.name,  # pylint: disable=no-member
                client=requestor,
                payment_info__provider_eth_account__in=[client_ethereum_address.provider for client_ethereum_address in clients_ethereum_addresses]
            )
        ),
    )


def prefetch_payment_info(queryset: QuerySet) -> QuerySet:
    """ Prefetches related PaymentInfo to PendingResponse model queryset. """
    return queryset.select_related('payment_info')


def get_related_payments_for_pair(clients_ethereum_addresses: list) -> Payments:
    """ Get all payments between given requestor/provider pair. """
    regular_payments = []  # type: List[str]
    settlement_payments = []  # type: List[str]
    forced_subtask_payments = []  # type: List[str]
    requestor_additional_verification_payments = []  # type: List[str]
    provider_additional_verification_payments = []  # type: List[str]
    oldest_subtask_creation_date = get_report_computed_task_timestamp_of_oldest_subtask()
    for clients_pair in clients_ethereum_addresses:
        regular_payments = service.get_list_of_payments(  # pylint: disable=no-value-for-parameter
            requestor_eth_address=clients_pair.requestor,
            provider_eth_address=clients_pair.provider,
            min_block_timestamp=oldest_subtask_creation_date,
            transaction_type=TransactionType.BATCH,
        )

        settlement_payments = service.get_list_of_payments(  # pylint: disable=no-value-for-parameter
            requestor_eth_address=clients_pair.requestor,
            provider_eth_address=clients_pair.provider,
            min_block_timestamp=oldest_subtask_creation_date,
            transaction_type=TransactionType.SETTLEMENT,
        )

        forced_subtask_payments = service.get_list_of_payments(  # pylint: disable=no-value-for-parameter
            requestor_eth_address=clients_pair.requestor,
            provider_eth_address=clients_pair.provider,
            min_block_timestamp=oldest_subtask_creation_date,
            transaction_type=TransactionType.FORCED_SUBTASK_PAYMENT,
        )

        requestor_additional_verification_payments = service.get_covered_additional_verification_costs(  # pylint: disable=no-value-for-parameter
            client_eth_address=clients_pair.requestor,
            payment_ts=oldest_subtask_creation_date,
        )
        provider_additional_verification_payments = service.get_covered_additional_verification_costs(  # pylint: disable=no-value-for-parameter
            client_eth_address=clients_pair.provider,
            payment_ts=oldest_subtask_creation_date,
        )

    return Payments(
        regular_payments=regular_payments,
        settlement_payments=settlement_payments,
        forced_subtask_payments=forced_subtask_payments,
        requestor_additional_verification_payments=requestor_additional_verification_payments,
        provider_additional_verification_payments=provider_additional_verification_payments,
    )


def get_report_computed_task_timestamp_of_oldest_subtask() -> int:
    """
    Return ReportComputedTask timestamp of oldest Subtask stored in database.
    If there are no Subtasks in database, return current timestamp.
    """
    subtasks_set = Subtask.objects.order_by('created_at')
    for subtask in subtasks_set:  # pylint: disable=not-an-iterable
        try:
            return deserialize_message(subtask.report_computed_task.data.tobytes()).timestamp
        except MessageError:
            pass

    return get_current_utc_timestamp()
