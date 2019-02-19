import binascii
import uuid
from enum import Enum
from functools import wraps

from typing import Any
from typing import Callable

from golem_sci.blockshelper import BlocksHelper
from golem_sci.implementation import SCIImplementation
from web3 import Web3

from common.constants import ErrorCode
from common.helpers import get_current_utc_timestamp
from core.constants import ETHEREUM_ADDRESS_LENGTH
from core.constants import MINIMUM_BLOCK_TIMESTAMP_MARGIN
from core.constants import PAYMENTS_FROM_BLOCK_SAFETY_MARGIN
from core.exceptions import SCINotSynchronized
from core.payments.payment_interface import PaymentInterface
from core.validation import validate_uuid
from core.validation import validate_value_is_int_convertible_and_non_negative
from core.validation import validate_value_is_int_convertible_and_positive


class TransactionType(Enum):
    BATCH = 'batch'
    FORCED_SUBTASK_PAYMENT = 'force_subtask_payment'
    SETTLEMENT = 'settlement'


def handle_sci_synchronization(sci_function: Callable) -> Callable:

    @wraps(sci_function)
    def wrapper(*args: Any, **kwargs: Any) -> None:
        if PaymentInterface().is_synchronized():  # type: ignore  # pylint: disable=no-member
            try:
                return sci_function(*args, **kwargs)
            except ValueError as exception:
                if "There are currently no blocks after" in str(exception):
                    return []  # type: ignore
                else:
                    raise
        else:
            raise SCINotSynchronized(
                'SCI is currently not synchronized',
                ErrorCode.SCI_NOT_SYNCHRONIZED,
            )
    return wrapper


@handle_sci_synchronization
def get_list_of_payments(
    requestor_eth_address: str,
    provider_eth_address: str,
    min_block_timestamp: int,
    transaction_type: TransactionType,
) -> list:
    """
    Function which return list of transactions from payment API
    where timestamp >= T0
    """
    assert isinstance(requestor_eth_address, str) and len(requestor_eth_address) == ETHEREUM_ADDRESS_LENGTH
    assert isinstance(provider_eth_address, str) and len(provider_eth_address) == ETHEREUM_ADDRESS_LENGTH
    assert isinstance(min_block_timestamp, int) and min_block_timestamp >= 0
    assert isinstance(transaction_type, Enum) and transaction_type in TransactionType

    payment_interface: SCIImplementation = PaymentInterface()

    current_time = get_current_utc_timestamp()
    if min_block_timestamp + MINIMUM_BLOCK_TIMESTAMP_MARGIN > current_time:
        min_block_timestamp = current_time - MINIMUM_BLOCK_TIMESTAMP_MARGIN

    first_block_after_payment_number = BlocksHelper(payment_interface).get_first_block_after(min_block_timestamp).number
    latest_block_number = payment_interface.get_block_number()  # pylint: disable=no-member
    if latest_block_number - first_block_after_payment_number < payment_interface.REQUIRED_CONFS:  # pylint: disable=no-member
        return []

    if transaction_type == TransactionType.SETTLEMENT:
        payments_list = payment_interface.get_forced_payments(  # pylint: disable=no-member
            requestor_address=Web3.toChecksumAddress(requestor_eth_address),
            provider_address=Web3.toChecksumAddress(provider_eth_address),
            from_block=first_block_after_payment_number,
            to_block=latest_block_number - payment_interface.REQUIRED_CONFS,  # pylint: disable=no-member
        )
    elif transaction_type == TransactionType.BATCH:
        payments_list = payment_interface.get_batch_transfers(  # pylint: disable=no-member
            payer_address=Web3.toChecksumAddress(requestor_eth_address),
            payee_address=Web3.toChecksumAddress(provider_eth_address),
            from_block=first_block_after_payment_number,
            to_block=latest_block_number - payment_interface.REQUIRED_CONFS,  # pylint: disable=no-member
        )
    elif transaction_type == TransactionType.FORCED_SUBTASK_PAYMENT:
        payments_list = payment_interface.get_forced_subtask_payments(  # pylint: disable=no-member
            requestor_address=Web3.toChecksumAddress(requestor_eth_address),
            provider_address=Web3.toChecksumAddress(provider_eth_address),
            # We start few blocks before first matching block because forced subtask payments
            # do not have closure_time so we are relying on blockchain timestamps
            from_block=first_block_after_payment_number - PAYMENTS_FROM_BLOCK_SAFETY_MARGIN,
            to_block=latest_block_number - payment_interface.REQUIRED_CONFS,  # pylint: disable=no-member
        )

    return payments_list


def make_settlement_payment(
    requestor_eth_address: str,
    provider_eth_address: str,
    value: int,
    closure_time: int,
) -> str:
    """
    Makes forced transaction from requestor's deposit to provider's account on amount 'value'.
    If there is less then 'value' on requestor's deposit, Concent transfers as much as possible.
    """
    assert isinstance(requestor_eth_address, str) and len(requestor_eth_address) == ETHEREUM_ADDRESS_LENGTH
    assert isinstance(provider_eth_address, str) and len(provider_eth_address) == ETHEREUM_ADDRESS_LENGTH
    assert isinstance(closure_time, int) and closure_time >= 0

    validate_value_is_int_convertible_and_positive(value)

    requestor_account_balance = PaymentInterface().get_deposit_value(Web3.toChecksumAddress(requestor_eth_address))  # type: ignore  # pylint: disable=no-member
    if requestor_account_balance < value:
        value = requestor_account_balance

    return PaymentInterface().force_payment(  # type: ignore  # pylint: disable=no-member
        requestor_address=Web3.toChecksumAddress(requestor_eth_address),
        provider_address=Web3.toChecksumAddress(provider_eth_address),
        value=int(value),
        closure_time=closure_time,
    )


def get_transaction_count() -> int:
    return PaymentInterface().get_transaction_count()  # type: ignore  # pylint: disable=no-member


@handle_sci_synchronization
def get_deposit_value(client_eth_address: str) -> int:
    assert isinstance(client_eth_address, str) and len(client_eth_address) == ETHEREUM_ADDRESS_LENGTH

    return PaymentInterface().get_deposit_value(Web3.toChecksumAddress(client_eth_address))  # type: ignore  # pylint: disable=no-member


def force_subtask_payment(
    requestor_eth_address: str,
    provider_eth_address: str,
    value: int,
    subtask_id: str,
) -> str:
    assert isinstance(requestor_eth_address, str) and len(requestor_eth_address) == ETHEREUM_ADDRESS_LENGTH
    assert isinstance(provider_eth_address, str) and len(provider_eth_address) == ETHEREUM_ADDRESS_LENGTH
    assert isinstance(subtask_id, str)

    validate_value_is_int_convertible_and_non_negative(value)

    return PaymentInterface().force_subtask_payment(  # type: ignore  # pylint: disable=no-member
        requestor_address=Web3.toChecksumAddress(requestor_eth_address),
        provider_address=Web3.toChecksumAddress(provider_eth_address),
        value=int(value),
        subtask_id=_hexencode_uuid(subtask_id),
    )


def cover_additional_verification_cost(
    provider_eth_address: str,
    value: int,
    subtask_id: str,
) -> str:
    assert isinstance(provider_eth_address, str) and len(provider_eth_address) == ETHEREUM_ADDRESS_LENGTH
    assert isinstance(subtask_id, str)

    validate_value_is_int_convertible_and_non_negative(value)

    return PaymentInterface().cover_additional_verification_cost(  # type: ignore  # pylint: disable=no-member
        address=Web3.toChecksumAddress(provider_eth_address),
        value=int(value),
        subtask_id=_hexencode_uuid(subtask_id),
    )


def register_confirmed_transaction_handler(
    tx_hash: str,
    callback: Callable
) -> None:
    PaymentInterface().on_transaction_confirmed(  # type: ignore  # pylint: disable=no-member
        tx_hash=tx_hash,
        cb=callback,
    )


def get_covered_additional_verification_costs(client_eth_address: str, payment_ts: int) -> list:
    assert isinstance(client_eth_address, str) and len(client_eth_address) == ETHEREUM_ADDRESS_LENGTH
    assert isinstance(payment_ts, int) and payment_ts >= 0

    payment_interface: SCIImplementation = PaymentInterface()

    current_time = get_current_utc_timestamp()  # pylint: disable=no-member
    if payment_ts + MINIMUM_BLOCK_TIMESTAMP_MARGIN > current_time:
        payment_ts = current_time - MINIMUM_BLOCK_TIMESTAMP_MARGIN

    first_block_after_payment_number = BlocksHelper(payment_interface).get_first_block_after(payment_ts).number

    latest_block_number = payment_interface.get_block_number()  # pylint: disable=no-member

    if latest_block_number - first_block_after_payment_number < payment_interface.REQUIRED_CONFS:  # pylint: disable=no-member
        return []

    return payment_interface.get_covered_additional_verification_costs(  # pylint: disable=no-member
        address=Web3.toChecksumAddress(client_eth_address),
        # We start few blocks before first matching block because additional verification payments
        # do not have closure_time so we are relying on blockchain timestamps
        from_block=first_block_after_payment_number - PAYMENTS_FROM_BLOCK_SAFETY_MARGIN,
        to_block=latest_block_number - payment_interface.REQUIRED_CONFS,  # pylint: disable=no-member
    )


def _hexencode_uuid(value: str) -> bytes:
    validate_uuid(value)

    return binascii.hexlify(uuid.UUID(value).bytes)
