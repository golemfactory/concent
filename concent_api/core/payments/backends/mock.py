import uuid
from typing import Callable

from core.constants import CLIENT_ETH_ADDRESS_WITH_0_DEPOSIT
from core.payments.backends.sci_backend import TransactionType


def get_list_of_payments(
    requestor_eth_address: str,  # pylint: disable=unused-argument
    provider_eth_address: str,  # pylint: disable=unused-argument
    payment_ts: int,  # pylint: disable=unused-argument
    transaction_type: TransactionType,  # pylint: disable=unused-argument
) -> list:  # pylint: disable=inconsistent-return-statements
    return []


def make_force_payment_to_provider(
    requestor_eth_address: str,  # pylint: disable=unused-argument
    provider_eth_address: str,  # pylint: disable=unused-argument
    value: int,  # pylint: disable=unused-argument
    payment_ts: int,  # pylint: disable=unused-argument
) -> str:
    return f'{uuid.uuid4()}{uuid.uuid4()}'[:64].replace('-', '1')


def get_transaction_count() -> int:
    return 0


def get_deposit_value(client_eth_address: str) -> int:  # pylint: disable=unused-argument
    if client_eth_address == CLIENT_ETH_ADDRESS_WITH_0_DEPOSIT:
        return 0
    else:
        return 10000


def force_subtask_payment(
    requestor_eth_address: str,  # pylint: disable=unused-argument
    provider_eth_address: str,  # pylint: disable=unused-argument
    value: int,  # pylint: disable=unused-argument
    subtask_id: str,  # pylint: disable=unused-argument
) -> str:
    return f'{uuid.uuid4()}{uuid.uuid4()}'[:64].replace('-', '1')


def cover_additional_verification_cost(
    provider_eth_address: str,  # pylint: disable=unused-argument
    value: int,  # pylint: disable=unused-argument
    subtask_id: str,  # pylint: disable=unused-argument
) -> str:
    return f'{uuid.uuid4()}{uuid.uuid4()}'[:64].replace('-', '1')


def call_on_confirmed_transaction(
    tx_hash: str,  # pylint: disable=unused-argument
    callback: Callable,  # pylint: disable=unused-argument
) -> None:
    pass


def validate_that_last_closure_time_is_older_than_oldest_payment(
    requestor_eth_address: str,  # pylint: disable=unused-argument
    provider_eth_address: str,  # pylint: disable=unused-argument
    oldest_payments_ts: int,  # pylint: disable=unused-argument
) -> None:
    pass
