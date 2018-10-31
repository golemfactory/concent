from typing import List
from typing import Optional
from typing import Tuple
from typing import Union

from django.conf import settings
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.db import transaction

from golem_messages.message.tasks import SubtaskResultsAccepted
from golem_messages.utils import encode_hex
from golem_sci.events import BatchTransferEvent
from golem_sci.events import ForcedPaymentEvent

from common.constants import ConcentUseCase
from common.helpers import generate_ethereum_address_from_ethereum_public_key_bytes
from common.helpers import get_current_utc_timestamp
from core.constants import ETHEREUM_ADDRESS_LENGTH
from core.models import Client
from core.models import DepositAccount
from core.models import DepositClaim
from core.payments import service
from core.payments.backends.sci_backend import TransactionType
from core.validation import validate_bytes_public_key


class ClaimPaymentInfo:

    __slots__ = [
        'amount_paid',
        'amount_pending',
        'tx_hash',
        'payment_ts',
        'timestamp_error',
    ]

    def __init__(
        self,
        amount_paid: int,
        amount_pending: int,
        tx_hash: Optional[str] = None,
        payment_ts: Optional[int] = None,
        timestamp_error: bool = False,
    ) -> None:
        assert isinstance(amount_paid, int) and amount_paid >= 0
        assert isinstance(amount_pending, int) and amount_paid >= 0
        assert isinstance(tx_hash, str) or (tx_hash is None and amount_paid == 0)
        assert isinstance(payment_ts, int) or (payment_ts is None and tx_hash is None)
        assert timestamp_error is False or (timestamp_error is True and amount_paid == amount_pending == 0)

        self.amount_paid = amount_paid
        self.amount_pending = amount_pending
        self.tx_hash = tx_hash
        self.payment_ts = payment_ts
        self.timestamp_error = timestamp_error


def claim_deposit(
    concent_use_case: ConcentUseCase,
    requestor_ethereum_address: str,
    provider_ethereum_address: str,
    subtask_cost: int,
    requestor_public_key: str,
    provider_public_key: str,
) -> Tuple[DepositClaim, DepositClaim]:
    """
    The purpose of this operation is to check whether the clients participating in a use case have enough funds in their
    deposits to cover all the costs associated with the use case in the pessimistic scenario.
    """

    assert isinstance(concent_use_case, ConcentUseCase)
    assert isinstance(requestor_ethereum_address, str)
    assert isinstance(provider_ethereum_address, str)
    assert isinstance(subtask_cost, int) and subtask_cost > 0

    assert concent_use_case in [ConcentUseCase.FORCED_ACCEPTANCE, ConcentUseCase.ADDITIONAL_VERIFICATION]
    assert len(requestor_ethereum_address) == ETHEREUM_ADDRESS_LENGTH
    assert len(provider_ethereum_address) == ETHEREUM_ADDRESS_LENGTH
    assert provider_ethereum_address != requestor_ethereum_address

    validate_bytes_public_key(requestor_public_key, 'requestor_public_key')
    validate_bytes_public_key(provider_public_key, 'provider_public_key')

    is_claim_against_provider: bool = (
        concent_use_case == ConcentUseCase.ADDITIONAL_VERIFICATION and
        0 <= settings.ADDITIONAL_VERIFICATION_COST
    )

    # Bankster creates Client and DepositAccount objects (if they don't exist yet) for the requestor
    # and also for the provider if there's a non-zero claim against his account.
    # This is done in single database transaction.
    with transaction.atomic(using='control'):
        requestor_client = Client.objects.get_or_create_full_clean(
            public_key=requestor_public_key,
        )
        requestor_deposit_account = DepositAccount.objects.get_or_create_full_clean(
            client=requestor_client,
            ethereum_address=requestor_ethereum_address,
        )

        if is_claim_against_provider:
            provider_client = Client.objects.get_or_create_full_clean(
                public_key=provider_public_key,
            )
            provider_deposit_account = DepositAccount.objects.get_or_create_full_clean(
                client=provider_client,
                ethereum_address=provider_ethereum_address,
            )

    # Bankster asks SCI about the amount of funds available in requestor's deposit.
    requestor_deposit = service.get_deposit_value(client_eth_address=requestor_ethereum_address)  # pylint: disable=no-value-for-parameter

    # If the amount claimed from provider's deposit is non-zero,
    # Bankster asks SCI about the amount of funds available in his deposit.
    if is_claim_against_provider:
        provider_deposit = service.get_deposit_value(client_eth_address=provider_ethereum_address)  # pylint: disable=no-value-for-parameter

    # Bankster puts database locks on DepositAccount objects
    # that will be used as payers in newly created DatabaseClaims.
    with transaction.atomic(using='control'):
        # Bankster sums the amounts of all existing DepositClaims that have the same payer as the one being processed.
        sum_of_existing_requestor_claims = DepositClaim.objects.filter(
            payer_deposit_account=requestor_deposit_account
        ).aggregate(
            sum_of_existing_claims=Coalesce(Sum('amount'), 0)
        )

        # If the existing claims against requestor's deposit are greater or equal to his current deposit,
        # we can't add a new claim.
        if requestor_deposit <= sum_of_existing_requestor_claims:
            return (None, None)

        if is_claim_against_provider:
            # Bankster sums the amounts of all existing DepositClaims where the provider is the payer.
            sum_of_existing_provider_claims = DepositClaim.objects.filter(
                payer_deposit_account=provider_deposit_account
            ).aggregate(
                sum_of_existing_claims=Coalesce(Sum('amount'), 0)
            )

            # If the total of existing claims and the current claim is greater or equal to the current deposit,
            # we can't add a new claim.
            if provider_deposit <= sum_of_existing_provider_claims + settings.ADDITIONAL_VERIFICATION_COST:
                return (None, None)

        # Deposit lock for requestor.
        claim_against_requestor = DepositClaim(
            payee_ethereum_address=provider_ethereum_address,
            amount=subtask_cost,
            concent_use_case=concent_use_case,
            payer_deposit_account=requestor_deposit_account,
        )
        claim_against_requestor.full_clean()
        claim_against_requestor.save()

        # Deposit lock for provider.
        if is_claim_against_provider:
            claim_against_provider = DepositClaim(
                payee_ethereum_address=generate_ethereum_address_from_ethereum_public_key_bytes(
                    settings.CONCENT_ETHEREUM_PUBLIC_KEY
                ),
                amount=subtask_cost,
                concent_use_case=concent_use_case,
                payer_deposit_account=provider_deposit_account,
            )
            claim_against_provider.full_clean()
            claim_against_provider.save()
        else:
            claim_against_provider = None

    return (claim_against_requestor, claim_against_provider)


def finalize_payment(deposit_claim: DepositClaim) -> str:
    """
    This operation tells Bankster to pay out funds from deposit.
    For each claim, Bankster uses SCI to submit an Ethereum transaction to the Ethereum client which then propagates it
    to the rest of the network.
    Hopefully the transaction is included in one of the upcoming blocks on the blockchain.
    """

    assert isinstance(deposit_claim, DepositClaim)

    # Bankster asks SCI about the amount of funds available on the deposit account listed in the DepositClaim.
    available_funds = service.get_deposit_value(  # pylint: disable=no-value-for-parameter
        client_eth_address=deposit_claim.payer_deposit_account.ethereum_address
    )

    # Bankster begins a database transaction and puts a database lock on the DepositAccount object.
    with transaction.atomic(using='control'):
        DepositAccount.objects.select_for_update().get(
            pk=deposit_claim.payer_deposit_account_id
        )

        # Bankster sums the amounts of all existing DepositClaims that have the same payer as the one being processed.
        sum_of_existing_claims = DepositClaim.objects.filter(
            payer_deposit_account=deposit_claim.payer_deposit_account
        ).exclude(
            pk=deposit_claim.pk
        ).aggregate(
            sum_of_existing_claims=Coalesce(Sum('amount'), 0)
        )

        # Bankster subtracts that value from the amount of funds available in the deposit.
        available_funds_without_claims = available_funds - sum_of_existing_claims['sum_of_existing_claims']

        # If the result is negative or zero, Bankster removes the DepositClaim object being processed.
        if available_funds_without_claims <= 0:
            deposit_claim.delete()
            return None

        # Otherwise if the result is lower than DepositAccount.amount,
        # Bankster sets this field to the amount that's actually available.
        elif available_funds_without_claims < deposit_claim.amount:
            deposit_claim.amount = available_funds_without_claims

        # If the DepositClaim still exists at this point, Bankster uses SCI to create an Ethereum transaction.
        if deposit_claim.concent_use_case == ConcentUseCase.FORCED_ACCEPTANCE:
            ethereum_transaction = service.force_subtask_payment(  # pylint: disable=no-value-for-parameter
                requestor_eth_address=deposit_claim.payer_deposit_account.ethereum_address,
                provider_eth_address=deposit_claim.payee_ethereum_address,
                value=deposit_claim.amount,
                subtask_id=deposit_claim.subtask.subtask_id,
            )
        elif deposit_claim.concent_use_case == ConcentUseCase.ADDITIONAL_VERIFICATION:
            ethereum_transaction = service.cover_additional_verification_cost(  # pylint: disable=no-value-for-parameter
                provider_eth_address=deposit_claim.payer_deposit_account.ethereum_address,
                value=deposit_claim.amount,
                subtask_id=deposit_claim.subtask.subtask_id,
            )

        # Bankster puts transaction ID in DepositClaim.tx_hash.
        deposit_claim.tx_hash = encode_hex(ethereum_transaction.hash)
        deposit_claim.save()

    return deposit_claim.tx_hash


def settle_overdue_acceptances(
    requestor_ethereum_address: str,
    provider_ethereum_address: str,
    acceptances: List[SubtaskResultsAccepted],
) -> ClaimPaymentInfo:
    """
    The purpose of this operation is to calculate the total amount that the requestor owes provider for completed
    computations and transfer that amount from requestor's deposit.
    The caller is responsible for making sure that the payment is legitimate and should be performed.
    Bankster simply calculates the amount and executes it.
    """

    assert isinstance(requestor_ethereum_address, str)
    assert isinstance(provider_ethereum_address, str)
    assert all([isinstance(acceptance, SubtaskResultsAccepted) for acceptance in acceptances])

    assert len(requestor_ethereum_address) == ETHEREUM_ADDRESS_LENGTH
    assert len(provider_ethereum_address) == ETHEREUM_ADDRESS_LENGTH
    assert provider_ethereum_address != requestor_ethereum_address

    # Bankster asks SCI about the amount of funds available in requestor's deposit.
    requestor_deposit_value = service.get_deposit_value(client_eth_address=requestor_ethereum_address)  # pylint: disable=no-value-for-parameter

    # Concent defines time T0 equal to oldest payment_ts from passed SubtaskResultAccepted messages from
    # subtask_results_accepted_list.
    oldest_payments_ts = min(subtask_results_accepted.payment_ts for subtask_results_accepted in acceptances)

    current_time = get_current_utc_timestamp()

    # Concent gets list of transactions from payment API where timestamp >= T0.
    list_of_transactions = service.get_list_of_payments(  # pylint: disable=no-value-for-parameter
        requestor_eth_address=requestor_ethereum_address,
        provider_eth_address=provider_ethereum_address,
        payment_ts=oldest_payments_ts,
        current_time=current_time,
        transaction_type=TransactionType.BATCH,
    )

    # Concent defines time T1 equal to youngest timestamp from list of transactions.
    if len(list_of_transactions) == 0:
        t1_is_bigger_than_payments_ts = False
    else:
        youngest_transaction = max(transaction.closure_time for transaction in list_of_transactions)
        # Concent checks if all passed SubtaskResultAccepted messages from subtask_results_accepted_list
        # have payment_ts < T1
        t1_is_bigger_than_payments_ts = any(
            youngest_transaction > subtask_results_accepted.payment_ts for subtask_results_accepted in acceptances
        )

    # Any of the items from list of overdue acceptances
    # matches condition current_time < payment_ts + PAYMENT_DUE_TIME
    acceptance_time_overdue = any(
        current_time < subtask_results_accepted.payment_ts + settings.PAYMENT_DUE_TIME
        for subtask_results_accepted in acceptances
    )

    if t1_is_bigger_than_payments_ts or acceptance_time_overdue:
        return ClaimPaymentInfo(0, 0, timestamp_error=True)

    # Concent gets list of forced payments from payment API where T0 <= payment_ts + PAYMENT_DUE_TIME.
    list_of_forced_payments = service.get_list_of_payments(  # pylint: disable=no-value-for-parameter
        requestor_eth_address=requestor_ethereum_address,
        provider_eth_address=provider_ethereum_address,
        payment_ts=oldest_payments_ts + settings.PAYMENT_DUE_TIME,  # Im not sure, check it please
        current_time=current_time,
        transaction_type=TransactionType.FORCE,
    )

    (_amount_paid, amount_pending) = get_provider_payment_info(
        list_of_forced_payments=list_of_forced_payments,
        list_of_payments=list_of_transactions,
        subtask_results_accepted_list=acceptances,
    )

    if amount_pending == 0:
        requestors_claim_payment_info = ClaimPaymentInfo(0, 0)
    elif requestor_deposit_value == 0:
        requestors_claim_payment_info = ClaimPaymentInfo(0, amount_pending)
    else:
        requestor_payable_amount = min(amount_pending, requestor_deposit_value)
        transaction_hash = service.make_force_payment_to_provider(  # pylint: disable=no-value-for-parameter
            requestor_eth_address=requestor_ethereum_address,
            provider_eth_address=provider_ethereum_address,
            value=requestor_payable_amount,
            payment_ts=current_time,  # TODO: Was payment_ts created in handler
        )
        requestors_claim_payment_info = ClaimPaymentInfo(
            amount_paid=requestor_payable_amount,
            amount_pending=amount_pending - requestor_payable_amount,
            tx_hash=transaction_hash,
            payment_ts=current_time,
        )

    return requestors_claim_payment_info


def sum_payments(payments: List[Union[ForcedPaymentEvent, BatchTransferEvent]]) -> int:
    assert isinstance(payments, list)

    return sum([item.amount for item in payments])


def sum_subtask_price(subtask_results_accepted_list: List[SubtaskResultsAccepted]) -> int:
    assert isinstance(subtask_results_accepted_list, list)

    return sum(
        [subtask_results_accepted.task_to_compute.price for subtask_results_accepted in subtask_results_accepted_list]
    )


def get_provider_payment_info(
    list_of_forced_payments: List[ForcedPaymentEvent],
    list_of_payments: List[BatchTransferEvent],
    subtask_results_accepted_list: List[SubtaskResultsAccepted],
) -> Tuple[int, int]:
    assert isinstance(list_of_payments, list)
    assert isinstance(list_of_forced_payments, list)
    assert isinstance(subtask_results_accepted_list, list)

    force_payments_price = sum_payments(list_of_forced_payments)
    payments_price = sum_payments(list_of_payments)
    subtasks_price = sum_subtask_price(subtask_results_accepted_list)

    amount_paid = payments_price + force_payments_price
    amount_pending = subtasks_price - amount_paid

    return (amount_paid, amount_pending)


def discard_claim(deposit_claim: DepositClaim) -> bool:
    """ This operation tells Bankster to discard the claim. Claim is simply removed, freeing the funds. """

    assert isinstance(deposit_claim, DepositClaim)

    with transaction.atomic(using='control'):
        DepositAccount.objects.select_for_update().get(
            pk=deposit_claim.payer_deposit_account_id
        )

        if deposit_claim.tx_hash is None:
            claim_removed = False
        else:
            deposit_claim.delete()
            claim_removed = True

    return claim_removed
