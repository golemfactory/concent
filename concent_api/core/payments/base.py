import importlib

from django.conf import settings


def _add_backend(func):
    """
    Decorator which adds currently set payment backend to function call.
    :param func: Function from this module, that as a first param takes in backend's name.
    :return: decorated function
    """
    def wrapper(*args, **kwargs):
        backend = importlib.import_module(settings.PAYMENT_BACKEND)
        assert hasattr(backend, func.__name__)
        return func(backend, *args, **kwargs)
    return wrapper


@_add_backend
def get_list_of_payments(
    backend,
    requestor_eth_address   = None,
    provider_eth_address    = None,
    payment_ts              = None,
    current_time            = None,
    transaction_type        = None,
):
    return backend.get_list_of_payments(
        requestor_eth_address   = requestor_eth_address,
        provider_eth_address    = provider_eth_address,
        payment_ts              = payment_ts,
        current_time            = current_time,
        transaction_type        = transaction_type,
    )


@_add_backend
def make_force_payment_to_provider(
    backend,
    requestor_eth_address   = None,
    provider_eth_address    = None,
    value                   = None,
    payment_ts              = None,
):
    return backend.make_force_payment_to_provider(
        requestor_eth_address   = requestor_eth_address,
        provider_eth_address    = provider_eth_address,
        value                   = value,
        payment_ts              = payment_ts,
    )


@_add_backend
def is_account_status_positive(
    backend,
    client_eth_address      = None,
    pending_value           = None,
):
    return backend.is_account_status_positive(
        client_eth_address      = client_eth_address,
        pending_value           = pending_value,
    )
