from core.exceptions import PaymentTimestampError
from core.payments.backends.sci_backend import get_list_of_payments
from core.payments.backends.sci_backend import TransactionType


def validate_that_last_closure_time_is_older_than_oldest_payment(  # pylint: disable=inconsistent-return-statements
    requestor_eth_address: str,
    provider_eth_address: str,
    youngest_payment_ts: int,
) -> None:
    forced_payment_event_list = get_list_of_payments(
        requestor_eth_address=requestor_eth_address,
        provider_eth_address=provider_eth_address,
        payment_ts=youngest_payment_ts,
        transaction_type=TransactionType.FORCE,
    )
    if forced_payment_event_list == []:
        return None
    elif youngest_payment_ts < max([event.closure_time for event in forced_payment_event_list]):
        raise PaymentTimestampError
