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
def sum_payments(backend, list_of_payments):
    return backend.sum_payments(list_of_payments)


@_add_backend
def get_client_eth_account(backend):
    return backend.get_client_eth_account()


@_add_backend
def get_number_of_eth_block(backend, request = None):
    return backend.get_number_of_eth_block(request)


@_add_backend
def payment_summary(backend, request = None, subtask_results_accepted_list = None, list_of_transactions = None, list_of_forced_payments = None):
    return backend.payment_summary(request, subtask_results_accepted_list, list_of_transactions, list_of_forced_payments)


@_add_backend
def get_list_of_transactions(backend, _oldest_payments_ts = None, current_time = None, _to_block = None, _payer_address = None, _payee_address = None, request = None):
    return backend.get_list_of_transactions(_oldest_payments_ts, current_time, _to_block, _payer_address, _payee_address, request)


@_add_backend
def get_forced_payments(backend, _oldest_payments_ts = None, _requestor_address = None, _provider_address = None, _to_block = None, request = None, current_time = None):
    return backend.get_forced_payments(_oldest_payments_ts, _requestor_address, _provider_address, _to_block, request, current_time)


@_add_backend
def make_payment_to_provider(backend, _sum_of_payments = None, _payment_ts = None, _requestor_ethereum_public_key = None, _provider_ethereum_public_key = None):
    return backend.make_payment_to_provider(_sum_of_payments, _payment_ts, _requestor_ethereum_public_key, _provider_ethereum_public_key)


@_add_backend
def make_forced_payment(backend, _provider = None, _requestor = None):
    return backend.make_forced_payment(_provider, _requestor)


@_add_backend
def is_provider_account_status_positive(backend, request = None):
    return backend.is_provider_account_status_positive(request)


@_add_backend
def calculate_amount_pending(backend):
    return backend.calculate_amount_pending()


@_add_backend
def is_requestor_account_status_positive(backend, request):  # TODO use real concent_rpc when available
    return backend.is_requestor_account_status_positive(request)
