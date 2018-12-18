from core.exceptions import PaymentTimestampError
from core.payments.backends.sci_backend import TransactionType
from core.payments.service import get_list_of_payments


def validate_that_last_closure_time_is_older_than_oldest_payment(
    requestor_eth_address: str,
    provider_eth_address: str,
    search_payments_since_ts: int,
) -> None:
    forced_payment_event_list = get_list_of_payments(  # pylint: disable=no-value-for-parameter
        requestor_eth_address=requestor_eth_address,
        provider_eth_address=provider_eth_address,
        payment_ts=search_payments_since_ts,
        transaction_type=TransactionType.FORCE,
    )
    if forced_payment_event_list != [] and search_payments_since_ts < max([event.closure_time
                                                                           for event in forced_payment_event_list]):
        raise PaymentTimestampError
