from enum import Enum
from enum import unique
from typing import Any
from typing import List
from typing import NamedTuple
from typing import Tuple

from django.conf import settings
from django.db.models import QuerySet

from golem_sci.events import CoverAdditionalVerificationEvent
from golem_sci.events import ForcedPaymentEvent
from golem_sci.events import ForcedSubtaskPaymentEvent

from common.constants import ConcentUseCase
from common.helpers import deserialize_message
from common.helpers import get_current_utc_timestamp
from common.helpers import parse_datetime_to_timestamp
from core.models import Client
from core.models import DepositClaim
from core.models import PendingResponse
from core.models import Subtask
from core.payments import service
from core.payments.backends.sci_backend import TransactionType


@unique
class MatchingError(Enum):
    MESSAGE_NOT_MATCHED_WITH_ANY_PAYMENT = 'message_not_matched_with_any_payment'
    PAYMENT_NOT_MATCHED_WITH_ANY_MESSAGE = 'payment_not_matched_with_any_message'
    MORE_THAN_EXPECTED_MATCHING_MESSAGES_FOR_PAYMENT = 'more_than_expected_matching_messages_for_payment'
    MORE_THAN_ONE_MATCHING_PAYMENT_FOR_MESSAGE = 'more_than_one_matching_payment_for_message'
    MESSAGE_VALUE_DIFFERS_FROM_PAYMENT_VALUE = 'message_value_differs_from_payment_value'
    MORE_THAN_ONE_SUBTASK_RESULT_FOR_SUBTASK = 'more_than_one_subtask_result_for_subtask'
    FORCE_PAYMENT_COMMITED_PAYMENT_TS_DIFFERS_FROM_SETTLEMENT_PAYMENT_CLOSURE_TIMESTAMP = 'force_payment_committed_payment_ts_differs_from_settlement_payment_closure_timestamp'
    DEPOSIT_CLAIM_RELATED_TO_FORCED_PAYMENT_EXISTS = 'deposit_claim_related_to_forced_payment_exists'
    DEPOSIT_CLAIM_RELATED_TO_SETTLEMENT_PAYMENT_EXISTS = 'deposit_claim_related_to_settlement_payment_exists'


@unique
class MatchingWarning(Enum):
    NOT_ENOUGH_DEPOSIT_TO_COVER_WHOLE_COST = 'not_enough_deposit_to_cover_whole_cost'
    NO_MATCHING_MESSAGE_FOR_PAYMENT_BUT_DEPOSIT_CLAIM_EXISTS = 'no_matching_message_for_payment_but_deposit_claim_exists'
    PAYMENT_VALUE_DIFFERS_FROM_VERIFICATION_COST = 'payment_value_differs_from_verification_cost'
    VERIFICATION_PAYMENT_DO_NOT_HAVE_RELATED_SUBTASK = 'verification_payment_do_not_have_related_subtask'


PendingResponses = NamedTuple(
    'PendingResponses',
    [
        ('subtask_results_settled', list),
        ('subtask_results_rejected', list),
        ('force_payment_committed', list),
    ]
)


Payments = NamedTuple(
    'Payments',
    [
        ('regular_payments', list),
        ('settlement_payments', list),
        ('forced_subtask_payments', list),
        ('additional_verification_payments_for_requestor', list),
        ('additional_verification_payments_for_provider', list),
    ]
)


Summary = NamedTuple(
    'Summary',
    [
        ('number_of_pairs', int),
        ('number_of_subtasks', int),
        ('number_of_regular_payments', int),
        ('number_of_forced_payments', int),
        ('total_amount_to_be_paid', int),
        ('total_amount_actually_paid', int),
        ('total_amount_unrecoverable', int),
    ]
)


PairReport = NamedTuple(
    'PairReport',
    [
        ('requestor', Client),
        ('provider', Client),
        ('pending_responses', PendingResponses),
        ('payments', Payments),
        ('errors', list),
        ('warnings', list),
        ('summary', Summary),
    ]
)


Report = NamedTuple(
    'Report',
    [
        ('pair_reports', list),
        ('summary', Summary),
    ]
)


Error = NamedTuple(
    'Error',
    [
        ('matching_error', MatchingError),
        ('message', str),
    ]
)


Warnings = NamedTuple(
    'Warnings',
    [
        ('matching_warning', MatchingWarning),
        ('message', str),
    ]
)


def create_report() -> Report:
    """ Create payments report for Concent. """
    pair_reports = []

    for subtask in get_subtasks_with_distinct_clients_pairs():  # pylint: disable=not-an-iterable
        (subtasks_ids, provider_ethereum_keys, requestor_ethereum_key) = get_subtask_ids_and_ethereum_keys_for_clients_pair(
            subtask.requestor,
            subtask.provider,
        )

        related_pending_responses_for_pair = get_related_pending_responses_for_subtasks_ids(subtasks_ids)

        related_payments_for_pair = get_related_payments_for_pair(provider_ethereum_keys, requestor_ethereum_key)

        (errors, warnings) = get_errors_and_warnings(
            related_payments_for_pair,
            related_pending_responses_for_pair,
        )

        pair_report = PairReport(
            requestor=subtask.requestor,
            provider=subtask.provider,
            pending_responses=related_pending_responses_for_pair,
            payments=related_payments_for_pair,
            errors=errors,
            warnings=warnings,
            summary=create_pair_summary(
                requestor=subtask.requestor,
                provider=subtask.provider,
                pending_responses=related_pending_responses_for_pair,
                payments=related_payments_for_pair,
            ),
        )
        pair_reports.append(pair_report)

    return Report(
        pair_reports,
        summary=create_report_summary(pair_reports),
    )


def get_subtasks_with_distinct_clients_pairs() -> QuerySet:
    """ Get Subtasks with distinct pairs of requestor and provider Clients. """
    return Subtask.objects.order_by('provider', 'requestor').distinct('provider', 'requestor')


def get_subtask_ids_and_ethereum_keys_for_clients_pair(requestor: Client, provider: Client) -> Tuple:
    """ Get Subtasks Ids and all Ethereum keys for Clients pair. """
    subtask_ids = []
    provider_ethereum_keys = []
    requestor_ethereum_keys = []

    for subtask in Subtask.objects.filter(requestor=requestor, provider=provider):  # pylint: disable=no-member
        subtask_ids.append(subtask.subtask_id)
        task_to_compute = deserialize_message(subtask.task_to_compute.data.tobytes())
        provider_ethereum_keys.append(task_to_compute.provider_ethereum_address)
        requestor_ethereum_keys.append(task_to_compute.requestor_ethereum_address)

    return subtask_ids, set(provider_ethereum_keys), set(requestor_ethereum_keys)


def get_related_pending_responses_for_subtasks_ids(subtasks_ids: List[str]) -> PendingResponses:
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
                subtask__subtask_id__in=subtasks_ids,
            )
        ),
    )


def prefetch_payment_info(queryset: QuerySet) -> QuerySet:
    """ Prefetches related PaymentInfo to PendingResponse model queryset. """
    return queryset.select_related('payment_info')


def get_related_payments_for_pair(requestor_ethereum_address: str, provider_ethereum_address: str) -> Payments:
    """ Get all payments between given requestor/provider pair. """
    regular_payments = service.get_list_of_payments(  # pylint: disable=no-value-for-parameter
        requestor_eth_address=requestor_ethereum_address,
        provider_eth_address=provider_ethereum_address,
        min_block_timestamp=get_oldest_subtask_creation_date(),
        transaction_type=TransactionType.BATCH,
    )

    settlement_payments = service.get_list_of_payments(  # pylint: disable=no-value-for-parameter
        requestor_eth_address=requestor_ethereum_address,
        provider_eth_address=provider_ethereum_address,
        min_block_timestamp=get_oldest_subtask_creation_date(),
        transaction_type=TransactionType.SETTLEMENT,
    )

    forced_subtask_payments = service.get_list_of_payments(  # pylint: disable=no-value-for-parameter
        requestor_eth_address=requestor_ethereum_address,
        provider_eth_address=provider_ethereum_address,
        min_block_timestamp=get_oldest_subtask_creation_date(),
        transaction_type=TransactionType.FORCED_SUBTASK_PAYMENT,
    )

    additional_verification_payments_for_requestor = service.get_covered_additional_verification_costs(  # pylint: disable=no-value-for-parameter
        client_eth_address=requestor_ethereum_address,
        payment_ts=get_oldest_subtask_creation_date(),
    )
    additional_verification_payments_for_provider = service.get_covered_additional_verification_costs(  # pylint: disable=no-value-for-parameter
        client_eth_address=provider_ethereum_address,
        payment_ts=get_oldest_subtask_creation_date(),
    )

    return Payments(
        regular_payments=regular_payments,
        settlement_payments=settlement_payments,
        forced_subtask_payments=forced_subtask_payments,
        additional_verification_payments_for_requestor=additional_verification_payments_for_requestor,
        additional_verification_payments_for_provider=additional_verification_payments_for_provider,
    )


def find_forced_subtask_payments_for_subtask_results_settled(
    subtask_results_settled: PendingResponse,
    forced_subtask_payments: list,
) -> List[ForcedSubtaskPaymentEvent]:
    """ Find forced subtask payments for the same subtask for given SubtaskResultsSettled message. """
    return [
        forced_subtask_payment for forced_subtask_payment in forced_subtask_payments
        if forced_subtask_payment.subtask_id == subtask_results_settled.subtask.subtask_id
    ]


def find_subtask_result_for_additional_verification_payment(
    additional_verification_payment: CoverAdditionalVerificationEvent,
    subtask_results_settled: List[PendingResponses],
    subtask_results_rejected: List[PendingResponses],
) -> List[PendingResponse]:
    """ Find the SubtaskResultsSettled or SubtaskResultsRejected for given additional verification payment. """
    matched_subtask_results_settled = [
        results_settled for results_settled in subtask_results_settled
        if results_settled.subtask.subtask_id == additional_verification_payment.subtask_id
    ]

    matched_subtask_results_rejected = [
        results_rejected for results_rejected in subtask_results_rejected
        if results_rejected.subtask.subtask_id == additional_verification_payment.subtask_id
    ]

    return matched_subtask_results_settled + matched_subtask_results_rejected


def find_settlement_payment_for_force_payment_committed(
    force_payment_committed_pending_response: PendingResponse,
    settlement_payments: list,
) -> List[ForcedPaymentEvent]:
    """ Find settlement payment for given ForcePaymentCommitted message. """
    # assert len(force_payment_committed_pending_response.payment_info) == 1
    if force_payment_committed_pending_response.payment_info is None:
        return []
    return [
        settlement_payment for settlement_payment in settlement_payments
        if (
            int(parse_datetime_to_timestamp(force_payment_committed_pending_response.payment_info.payment_ts)) - 10 <=
            settlement_payment.closure_time <=
            int(parse_datetime_to_timestamp(force_payment_committed_pending_response.payment_info.payment_ts)) + 10
        )
    ]


def get_errors_and_warnings(payments: Payments, responses: PendingResponses) -> Tuple[List[Error], List[Warnings]]:
    """ Get errors and warnings for messages and related payments. """
    errors: List[Error] = []
    warnings: List[Warnings] = []

    for subtask_results_settled_pending_response in responses.subtask_results_settled:
        matched_forced_subtask_payments_with_subtask_results_settled = find_forced_subtask_payments_for_subtask_results_settled(
            subtask_results_settled_pending_response,
            payments.forced_subtask_payments,
        )

        error_was_added = check_error_cannot_match_message_with_any_payment(
            errors,
            matched_forced_subtask_payments_with_subtask_results_settled,
            subtask_results_settled_pending_response,
        )

        if error_was_added:
            check_warning_deposit_claim_exists_for_missing_match(
                warnings,
                subtask_results_settled_pending_response.subtask.subtask_id,
                ConcentUseCase.FORCED_ACCEPTANCE,
            )

        check_error_more_matching_payment_for_message_than_given_amount(
            errors,
            matched_forced_subtask_payments_with_subtask_results_settled,
            subtask_results_settled_pending_response,
        )

    for additional_verification_payment in payments.additional_verification_payments_for_requestor:
        matched_subtask_result_with_additional_verification_payment_for_requestor = find_subtask_result_for_additional_verification_payment(
            additional_verification_payment,
            responses.subtask_results_settled,
            responses.subtask_results_rejected,
        )

        check_additional_verification_payment_errors_and_warning(
            errors,
            warnings,
            matched_subtask_result_with_additional_verification_payment_for_requestor,
            additional_verification_payment,
        )

    for additional_verification_payment in payments.additional_verification_payments_for_provider:
        matched_subtask_result_with_additional_verification_payment_for_provider = find_subtask_result_for_additional_verification_payment(
            additional_verification_payment,
            responses.subtask_results_settled,
            responses.subtask_results_rejected,
        )

        check_additional_verification_payment_errors_and_warning(
            errors,
            warnings,
            matched_subtask_result_with_additional_verification_payment_for_provider,
            additional_verification_payment,
        )

    for force_payment_committed_pending_response in responses.force_payment_committed:
        matched_settlement_payment_for_force_payment_committed = find_settlement_payment_for_force_payment_committed(
            force_payment_committed_pending_response,
            payments.settlement_payments,
        )

        error_was_added = check_error_cannot_match_message_with_any_payment(
            errors,
            matched_settlement_payment_for_force_payment_committed,
            force_payment_committed_pending_response,
        )

        if error_was_added:
            check_warning_deposit_claim_exists_for_missing_match(
                warnings,
                force_payment_committed_pending_response.subtask.subtask_id,
                ConcentUseCase.FORCED_PAYMENT,
            )

        check_error_more_matching_payment_for_message_than_given_amount(
            errors,
            matched_settlement_payment_for_force_payment_committed,
            force_payment_committed_pending_response,
        )
        check_error_message_value_is_different_than_payment_value(
            errors,
            matched_settlement_payment_for_force_payment_committed,
            force_payment_committed_pending_response,
        )
        check_error_message_payment_ts_is_different_than_payment_closure_time(
            errors,
            matched_settlement_payment_for_force_payment_committed,
            force_payment_committed_pending_response,
        )
        check_warning_force_payment_committed_indicates_that_deposit_was_too_low_to_cover_whole_cost(
            warnings,
            force_payment_committed_pending_response,
        )

    for forced_subtask_payment in payments.forced_subtask_payments:
        check_error_deposit_claim_exists_for_forced_payment(
            errors,
            forced_subtask_payment.tx_hash,
        )

    for settlement_payment in payments.settlement_payments:
        check_error_deposit_claim_exists_for_settlement_payment(
            errors,
            settlement_payment.tx_hash,
        )

    return errors, warnings


def check_additional_verification_payment_errors_and_warning(
    errors: List[Error],
    warnings: List[Warnings],
    matched_objects: List[PendingResponse],
    additional_verification_payment: CoverAdditionalVerificationEvent,
) -> None:
    """ Check errors and warning related to CoverAdditionalVerificationEvent object. """
    error_was_added = check_error_cannot_match_payment_with_any_message(
        errors,
        matched_objects,
        additional_verification_payment
    )

    if error_was_added:
        check_warning_deposit_claim_exists_for_missing_match(
            warnings,
            additional_verification_payment.subtask_id,
            ConcentUseCase.ADDITIONAL_VERIFICATION,
        )

    check_error_more_matching_message_for_payment_than_given_amount(
        errors,
        matched_objects,
        additional_verification_payment,
        amount=2,
    )
    check_error_more_than_one_subtask_result_of_the_same_type_for_subtask(
        errors,
        matched_objects,
        additional_verification_payment,
    )
    check_warning_no_subtask_related_with_additional_verification_payment(
        warnings,
        additional_verification_payment.subtask_id,
    )
    check_warning_payment_value_differs_from_verification_cost_in_settings(
        warnings,
        matched_objects,
        additional_verification_payment,
    )


def check_error_cannot_match_message_with_any_payment(
    errors: List[Error],
    matched_objects: List,
    pending_response: PendingResponse,
) -> bool:
    """ Add error if message cannot be matched with any payment."""
    if len(matched_objects) == 0:
        errors.append(
            Error(
                matching_error=MatchingError.MESSAGE_NOT_MATCHED_WITH_ANY_PAYMENT,
                message=f'PendingResponse of type {pending_response.response_type} and pk {pending_response.pk} does not have any matching payment.',
            )
        )
        return True
    return False


def check_error_cannot_match_payment_with_any_message(
    errors: List[Error],
    matched_objects: List,
    payment: Any,
) -> bool:
    """ Add error if payment cannot be matched with any message."""
    if len(matched_objects) == 0:
        errors.append(
            Error(
                matching_error=MatchingError.PAYMENT_NOT_MATCHED_WITH_ANY_MESSAGE,
                message=f'Payment of type {type(payment)} and tx_hash {payment.tx_hash} does not have any matching messages.',
            )
        )
        return True
    return False


def check_error_more_matching_message_for_payment_than_given_amount(
    errors: List[Error],
    matched_objects: List,
    payment: Any,
    amount: int = 1,
) -> None:
    """ Add error if there are more messages matched with a payment than given amount. """
    if len(matched_objects) > amount:
        errors.append(
            Error(
                matching_error=MatchingError.MORE_THAN_EXPECTED_MATCHING_MESSAGES_FOR_PAYMENT,
                message=f'Payment of type {type(payment)} and tx_hash {payment.tx_hash} has {len(matched_objects)} matching messages.',
            )
        )


def check_error_more_matching_payment_for_message_than_given_amount(
    errors: List[Error],
    matched_objects: List,
    pending_response: PendingResponse,
    amount: int = 1,
) -> None:
    """ Add error if there are more payments matched with a message than given amount. """
    if len(matched_objects) > amount:
        errors.append(
            Error(
                matching_error=MatchingError.MORE_THAN_ONE_MATCHING_PAYMENT_FOR_MESSAGE,
                message=f'PendingResponse of type {pending_response.response_type} and pk {pending_response.pk} has {len(matched_objects)} matching payments.',
            )
        )


def check_error_message_value_is_different_than_payment_value(
    errors: List[Error],
    matched_objects: List,
    force_payment_committed_pending_response: PendingResponse,
) -> None:
    """
    Add error if PaymentInfo.amount_paid related to stored PendingResponse of type ForcePaymentCommitted
    differs from the settlement_payment.amount value.
    """
    # assert len(force_payment_committed_pending_response.payment_info) == 1
    payment_info = force_payment_committed_pending_response.payment_info
    if payment_info is not None:
        for settlement_payment in matched_objects:
            if settlement_payment.amount != payment_info.amount_paid:
                errors.append(
                    Error(
                        matching_error=MatchingError.MESSAGE_VALUE_DIFFERS_FROM_PAYMENT_VALUE,
                        message=f'PaymentInfo with pk {payment_info.pk} amount_paid value {payment_info.amount_paid} '
                                f'related to stored PendingResponse of type ForcePaymentCommitted '
                                f'with pk {force_payment_committed_pending_response.pk} '
                                f'differs from the settlement payment with tx_hash {settlement_payment.tx_hash} '
                                f'amount value {settlement_payment.amount}.',
                    )
                )


def check_error_message_payment_ts_is_different_than_payment_closure_time(
    errors: List[Error],
    matched_objects: List,
    force_payment_committed_pending_response: PendingResponse,
) -> None:
    """
    Add error if PaymentInfo.payment_ts related stored PendingResponse of type ForcePaymentCommitted
    differs from closure_time of the settlement payment.
    """
    # assert len(force_payment_committed_pending_response.payment_info) == 1
    payment_info = force_payment_committed_pending_response.payment_info
    if payment_info is not None:
        for settlement_payment in matched_objects:
            if settlement_payment.closure_time != parse_datetime_to_timestamp(payment_info.payment_ts):
                errors.append(
                    Error(
                        matching_error=MatchingError.FORCE_PAYMENT_COMMITED_PAYMENT_TS_DIFFERS_FROM_SETTLEMENT_PAYMENT_CLOSURE_TIMESTAMP,
                        message=f'PaymentInfo with pk {payment_info.pk} payment ts value {payment_info.payment_ts} '
                                f'related to stored PendingResponse of type ForcePaymentCommitted '
                                f'with pk {force_payment_committed_pending_response.pk} '
                                f'differs from the settlement payment with tx_hash {settlement_payment.tx_hash} '
                                f'closure time value {settlement_payment.closure_time}.',
                    )
                )


def check_error_more_than_one_subtask_result_of_the_same_type_for_subtask(
    errors: List[Error],
    matched_objects: List,
    additional_verification_payment: CoverAdditionalVerificationEvent,
) -> None:
    """ Add error if there is more than two SubtaskResultsSettled or SubtaskResultsRejected for the same subtask. """
    matching_subtasks_results_settled_existence = [
        subtask_result.response_type == PendingResponse.ResponseType.SubtaskResultsSettled.name  # pylint: disable=no-member
        for subtask_result in matched_objects
    ]
    matching_subtasks_results_rejected_existence = [
        subtask_result.response_type == PendingResponse.ResponseType.SubtaskResultsRejected.name  # pylint: disable=no-member
        for subtask_result in matched_objects
    ]

    if any(matching_subtasks_results_settled_existence) and any(matching_subtasks_results_rejected_existence):
        errors.append(
            Error(
                matching_error=MatchingError.MORE_THAN_ONE_SUBTASK_RESULT_FOR_SUBTASK,
                message=f'Subtask related with CoverAdditionalVerificationEvent with '
                        f'tx_hash {additional_verification_payment.tx_hash} '
                        f'and subtask_id {additional_verification_payment.subtask_id} '
                        f'has both SubtaskResultsSettled or SubtaskResultsRejected.',
            )
        )


def check_error_deposit_claim_exists_for_settlement_payment(errors: List[Error], tx_hash: str) -> None:
    """ Add error if there is DepositClaim related with settlement payment. """
    if DepositClaim.objects.filter(tx_hash=tx_hash).exists():
        errors.append(
            Error(
                matching_error=MatchingError.DEPOSIT_CLAIM_RELATED_TO_SETTLEMENT_PAYMENT_EXISTS,
                message=f'DepositClaim still exists for transaction with tx_hash {tx_hash}',
            )
        )


def check_error_deposit_claim_exists_for_forced_payment(errors: List[Error], tx_hash: str) -> None:
    """ Add error if there is DepositClaim related with forced payment. """
    if DepositClaim.objects.filter(tx_hash=tx_hash).exists():
        errors.append(
            Error(
                matching_error=MatchingError.DEPOSIT_CLAIM_RELATED_TO_FORCED_PAYMENT_EXISTS,
                message=f'DepositClaim still exists for transaction with tx_hash {tx_hash}',
            )
        )


def check_warning_deposit_claim_exists_for_missing_match(
    warnings: List[Warnings],
    subtask_id: str,
    concent_use_case: ConcentUseCase,
) -> None:
    """
    Add warning if message cannot be matched with a payment
    but there's a DepositClaim that indicates that the transaction is pending.
    """
    if DepositClaim.objects.filter(
        subtask_id=subtask_id,
        concent_use_case=concent_use_case,
    ).exists():
        warnings.append(
            Warnings(
                matching_warning=MatchingWarning.NO_MATCHING_MESSAGE_FOR_PAYMENT_BUT_DEPOSIT_CLAIM_EXISTS,
                message=f'DepositClaim exists for subtask_id {subtask_id} and concent use case {concent_use_case}',
            )
        )


def check_warning_no_subtask_related_with_additional_verification_payment(
    warnings: List[Warnings],
    subtask_id: str,
) -> None:
    """ Add warning if there is no related Subtask in the database for additional verification payment. """
    if not Subtask.objects.filter(subtask_id=subtask_id).exists():  # pylint: disable=no-member
        warnings.append(
            Warnings(
                matching_warning=MatchingWarning.VERIFICATION_PAYMENT_DO_NOT_HAVE_RELATED_SUBTASK,
                message=f'There is no subtask related with additional verification payment with subtask_id {subtask_id}',
            )
        )


def check_warning_payment_value_differs_from_verification_cost_in_settings(
    warnings: List[Warnings],
    matched_objects: List,
    additional_verification_payment: CoverAdditionalVerificationEvent,
) -> None:
    """
    Add warning if for SubtaskResultsRejected the value of the additional verification payment is different than
    verification cost defined in settings.
    """
    for subtask_result in matched_objects:
        if (
            subtask_result.response_type == PendingResponse.ResponseType.SubtaskResultsRejected.name and  # pylint: disable=no-member
            additional_verification_payment.amount != settings.ADDITIONAL_VERIFICATION_COST
        ):
            warnings.append(
                Warnings(
                    matching_warning=MatchingWarning.PAYMENT_VALUE_DIFFERS_FROM_VERIFICATION_COST,
                    message=f'CoverAdditionalVerificationEvent with tx_hash {additional_verification_payment.tx_hash} '
                            f'has different value {additional_verification_payment.amount} than '
                            f'verification cost defined in settings {settings.ADDITIONAL_VERIFICATION_COST}.',
                )
            )


def check_warning_force_payment_committed_indicates_that_deposit_was_too_low_to_cover_whole_cost(
    warnings: List[Warnings],
    force_payment_committed_pending_response: PendingResponse,
) -> None:
    """
    Add error if PaymentInfo.amount_pending related stored PendingResponse of type ForcePaymentCommitted
    is greater than 0.
    """
    # assert len(force_payment_committed_pending_response.payment_info) == 1
    payment_info = force_payment_committed_pending_response.payment_info
    if payment_info is not None and payment_info.amount_pending > 0:
        warnings.append(
            Warnings(
                matching_warning=MatchingWarning.NOT_ENOUGH_DEPOSIT_TO_COVER_WHOLE_COST,
                message=f'PendingResponse of type ForcePaymentCommitted with pk {force_payment_committed_pending_response.pk} '
                        f'has related PaymentInfo that indicated that deposit was too low to cover whole cost.',
            )
        )


def create_pair_summary(
    provider: Client,
    requestor: Client,
    payments: Payments,
    pending_responses: PendingResponses,
) -> Summary:
    """ Prepare summary for provider/requestor pair. """
    return Summary(
        number_of_pairs=1,
        number_of_subtasks=Subtask.objects.filter(
            provider=provider,
            requestor=requestor,
        ).count(),
        number_of_regular_payments=len(payments.regular_payments),
        number_of_forced_payments=(
            len(payments.settlement_payments) +
            len(payments.forced_subtask_payments) +
            len(payments.additional_verification_payments_for_requestor) +
            len(payments.additional_verification_payments_for_provider)
        ),
        total_amount_to_be_paid=(
            sum([
                int(force_payment_committed.payment_info.amount_paid)
                for force_payment_committed in pending_responses.force_payment_committed
                if force_payment_committed.payment_info is not None
            ])
        ),
        total_amount_actually_paid=(
            sum([payment.amount for payment in payments.settlement_payments]) +
            sum([payment.amount for payment in payments.forced_subtask_payments]) +
            sum([payment.amount for payment in payments.additional_verification_payments_for_requestor]) +
            sum([payment.amount for payment in payments.additional_verification_payments_for_provider])
        ),
        total_amount_unrecoverable=(
            sum([
                int(force_payment_committed.payment_info.amount_pending)
                for force_payment_committed in pending_responses.force_payment_committed
                if force_payment_committed.payment_info is not None
            ])
        ),
    )


def create_report_summary(pair_reports: List[PairReport]) -> Summary:
    """ Prepare summary for the whole report. """
    return Summary(
        number_of_pairs=len(pair_reports),
        number_of_subtasks=sum([pair_report.summary.number_of_subtasks for pair_report in pair_reports]),
        number_of_regular_payments=sum([pair_report.summary.number_of_regular_payments for pair_report in pair_reports]),
        number_of_forced_payments=sum([pair_report.summary.number_of_forced_payments for pair_report in pair_reports]),
        total_amount_to_be_paid=sum([pair_report.summary.total_amount_to_be_paid for pair_report in pair_reports]),
        total_amount_actually_paid=sum([pair_report.summary.total_amount_actually_paid for pair_report in pair_reports]),
        total_amount_unrecoverable=sum([pair_report.summary.total_amount_unrecoverable for pair_report in pair_reports]),
    )


def get_oldest_subtask_creation_date() -> int:
    """
    Return creation date as timestamp of oldest Subtask stored in database.
    If there are no Subtasks in database, return current timestamp.
    """
    oldest_subtask = Subtask.objects.order_by('-created_at').first()

    if oldest_subtask is not None:
        return int(parse_datetime_to_timestamp(oldest_subtask.created_at))

    return get_current_utc_timestamp()
