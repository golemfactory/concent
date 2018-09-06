from core.payments.backends.sci_backend import TransactionType


def get_list_of_payments(
    current_time: int,  # pylint: disable=unused-argument
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
) -> None:
    pass


def is_account_status_positive(
    client_eth_address: str,  # pylint: disable=unused-argument
    pending_value: int = 0
) -> bool:
    return pending_value > 0


def get_transaction_count() -> int:
    return 0
