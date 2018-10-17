from typing import Tuple

from django.conf import settings

from common.constants import ConcentUseCase
from core.constants import ETHEREUM_ADDRESS_LENGTH
from core.payments import service


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
