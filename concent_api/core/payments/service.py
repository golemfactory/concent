from typing import Any
from typing import Callable
from typing import List
import importlib

from django.conf import settings
from ethereum.transactions import Transaction

from core.payments.backends.sci_backend import TransactionType


def _add_backend(func: Callable) -> Callable:
    """
    Decorator which adds currently set payment backend to function call.
    :param func: Function from this module, that as a first param takes in backend's name.
    :return: decorated function
    """
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        backend = importlib.import_module(settings.PAYMENT_BACKEND)
        assert hasattr(backend, func.__name__)
        return func(backend, *args, **kwargs)
    return wrapper


@_add_backend
def get_list_of_payments(
    backend: Any,
    requestor_eth_address: str = None,
    provider_eth_address: str = None,
    min_block_timestamp: int = None,
    transaction_type: TransactionType = None,
) -> list:
    return backend.get_list_of_payments(
        requestor_eth_address=requestor_eth_address,
        provider_eth_address=provider_eth_address,
        min_block_timestamp=min_block_timestamp,
        transaction_type=transaction_type,
    )


@_add_backend
def make_settlement_payment(
    backend: Any,
    requestor_eth_address: str,
    provider_eth_address: str,
    value: List[int],
    subtask_ids: List[int],
    closure_time: int,
    v: List[int],
    r: List[bytes],
    s: List[bytes],
    reimburse_amount: int,
) -> Transaction:
    return backend.make_settlement_payment(
        requestor_eth_address=requestor_eth_address,
        provider_eth_address=provider_eth_address,
        value=value,
        subtask_ids=subtask_ids,
        closure_time=closure_time,
        v=v,
        r=r,
        s=s,
        reimburse_amount=reimburse_amount,
    )


@_add_backend
def get_transaction_count(backend: Any) -> int:
    return backend.get_transaction_count()


@_add_backend
def get_deposit_value(backend: Any, client_eth_address: str) -> int:
    return backend.get_deposit_value(client_eth_address)


@_add_backend
def force_subtask_payment(
    backend: Any,
    requestor_eth_address: str,
    provider_eth_address: str,
    value: int,
    subtask_id: str,
    v: int,
    r: bytes,
    s: bytes,
    reimburse_amount: int,
) -> str:
    return backend.force_subtask_payment(
        requestor_eth_address=requestor_eth_address,
        provider_eth_address=provider_eth_address,
        value=value,
        subtask_id=subtask_id,
        v=v,
        r=r,
        s=s,
        reimburse_amount=reimburse_amount,
    )


@_add_backend
def cover_additional_verification_cost(
    backend: Any,
    provider_eth_address: str,
    value: int,
    subtask_id: str,
    v: int,
    r: bytes,
    s: bytes,
    reimburse_amount: int,
) -> Transaction:
    return backend.cover_additional_verification_cost(
        provider_eth_address=provider_eth_address,
        value=value,
        subtask_id=subtask_id,
        v=v,
        r=r,
        s=s,
        reimburse_amount=reimburse_amount,
    )


@_add_backend
def register_confirmed_transaction_handler(
    backend: Any,
    tx_hash: str,
    callback: Callable
) -> None:
    backend.register_confirmed_transaction_handler(tx_hash, callback)


@_add_backend
def get_covered_additional_verification_costs(
    backend: Any,
    client_eth_address: str,
    payment_ts: int,
) -> list:
    return backend.get_covered_additional_verification_costs(
        client_eth_address,
        payment_ts,
    )
