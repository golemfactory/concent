
def get_list_of_payments(current_time = None, requestor_eth_address = None, provider_eth_address = None, payment_ts = None, request = None, transaction_type = None):  # pylint: disable=inconsistent-return-statements, unused-argument
    return []


def make_force_payment_to_provider(requestor_eth_address = None, provider_eth_address = None, value = None, payment_ts = None):  # pylint: disable=unused-argument
    pass


def is_account_status_positive(client_eth_address = None, pending_value = None):  # pylint: disable=unused-argument
    return pending_value > 0


def get_transaction_count() -> int:
    return 0
