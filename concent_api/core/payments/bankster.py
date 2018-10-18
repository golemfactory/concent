from typing import Optional
from typing import Tuple

from django.conf import settings

from common.constants import ConcentUseCase
from common.helpers import get_current_utc_timestamp
from core.constants import ETHEREUM_ADDRESS_LENGTH
from core.payments import service


class ClaimPaymentInfo:

    __slots__ = [
        'amount_paid',
        'amount_pending',
        'tx_hash',
        'payment_ts',
    ]

    def __init__(
        self,
        amount_paid: int,
        amount_pending: int,
        tx_hash: Optional[bytes] = None,
        payment_ts: Optional[int] = None,
    ) -> None:
        assert isinstance(amount_paid, int) and amount_paid >= 0
        assert isinstance(amount_pending, int) and amount_paid >= 0
        assert isinstance(tx_hash, bytes) or (tx_hash is None and amount_paid == 0)
        assert isinstance(payment_ts, int) or (payment_ts is None and tx_hash is None)

        self.amount_paid = amount_paid
        self.amount_pending = amount_pending
        self.tx_hash = tx_hash
        self.payment_ts = payment_ts


def claim_deposit(
    concent_use_case: ConcentUseCase,
    requestor_ethereum_address: str,
    provider_ethereum_address: str,
    subtask_cost: int,
) -> Tuple[bool, bool]:
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

    # Claims against requestor's deposit can be paid partially because the service has already been performed
    # by the provider and giving him something is better than giving nothing.
    # If the requestor's deposit is zero, we can't add a new claim.
    requestor_has_enough_deposit: bool = service.get_deposit_value(client_eth_address=requestor_ethereum_address) > 0  # pylint: disable=no-value-for-parameter

    # Claims against provider's deposit must be paid in full because they're payments for using Concent for
    # additional verification and we did not perform the service yet so we can just refuse.
    # If the provider's claim is greater than his current deposit, we can't add a new claim.
    provider_has_enough_deposit: bool = (
        concent_use_case != ConcentUseCase.ADDITIONAL_VERIFICATION or
        service.get_deposit_value(client_eth_address=provider_ethereum_address) >= settings.ADDITIONAL_VERIFICATION_COST  # pylint: disable=no-value-for-parameter
    )

    return (requestor_has_enough_deposit, provider_has_enough_deposit)


def finalize_payment(
    subtask_id: str,
    concent_use_case: ConcentUseCase,
    requestor_ethereum_address: str,
    provider_ethereum_address: str,
    subtask_cost: int,
) -> Tuple[ClaimPaymentInfo, ClaimPaymentInfo]:
    """
    This operation tells Bankster to pay out funds from deposit.
    For each claim, Bankster uses SCI to submit an Ethereum transaction to the Ethereum client which then propagates it
    to the rest of the network.
    Hopefully the transaction is included in one of the upcoming blocks on the blockchain.
    """

    assert isinstance(subtask_id, str)
    assert isinstance(concent_use_case, ConcentUseCase)
    assert isinstance(requestor_ethereum_address, str)
    assert isinstance(provider_ethereum_address, str)
    assert isinstance(subtask_cost, int) and subtask_cost > 0

    assert concent_use_case in [ConcentUseCase.FORCED_ACCEPTANCE, ConcentUseCase.ADDITIONAL_VERIFICATION]
    assert len(requestor_ethereum_address) == ETHEREUM_ADDRESS_LENGTH
    assert len(provider_ethereum_address) == ETHEREUM_ADDRESS_LENGTH
    assert provider_ethereum_address != requestor_ethereum_address

    # Bankster determines the amount that needs to be claimed from each account.
    available_requestor_claim = min(service.get_deposit_value(client_eth_address=requestor_ethereum_address), subtask_cost)  # pylint: disable=no-value-for-parameter
    available_provider_claim = (
        min(
            service.get_deposit_value(client_eth_address=provider_ethereum_address),  # pylint: disable=no-value-for-parameter
            settings.ADDITIONAL_VERIFICATION_COST
        )
        if concent_use_case == ConcentUseCase.ADDITIONAL_VERIFICATION
        else 0
    )

    current_time = get_current_utc_timestamp()

    # Handle requestor claim payment info
    if available_requestor_claim == 0:
        requestors_claim_payment_info = ClaimPaymentInfo(0, subtask_cost)
    else:
        transaction = service.force_subtask_payment(  # pylint: disable=no-value-for-parameter
            requestor_eth_address=requestor_ethereum_address,
            provider_eth_address=provider_ethereum_address,
            value=available_requestor_claim,
            subtask_id=subtask_id,
        )
        requestors_claim_payment_info = ClaimPaymentInfo(
            amount_paid=available_requestor_claim,
            amount_pending=subtask_cost - available_requestor_claim,
            tx_hash=transaction.hash,
            payment_ts=current_time,
        )

    # Handle provider claim payment info
    if settings.ADDITIONAL_VERIFICATION_COST == 0 or concent_use_case != ConcentUseCase.ADDITIONAL_VERIFICATION:
        providers_claim_payment_info = ClaimPaymentInfo(0, 0)
    elif available_provider_claim == 0:
        providers_claim_payment_info = ClaimPaymentInfo(0, settings.ADDITIONAL_VERIFICATION_COST)
    else:
        transaction = service.cover_additional_verification_cost(  # pylint: disable=no-value-for-parameter
            provider_eth_address=provider_ethereum_address,
            value=available_provider_claim,
            subtask_id=subtask_id,
        )
        providers_claim_payment_info = ClaimPaymentInfo(
            amount_paid=available_provider_claim,
            amount_pending=settings.ADDITIONAL_VERIFICATION_COST - available_provider_claim,
            tx_hash=transaction.hash,
            payment_ts=current_time,
        )

    return requestors_claim_payment_info, providers_claim_payment_info
