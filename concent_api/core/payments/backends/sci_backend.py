import binascii
import uuid
from enum import Enum

from golem_sci import SmartContractsInterface
from golem_sci.blockshelper import BlocksHelper
from web3 import Web3

from core.constants import ETHEREUM_ADDRESS_LENGTH
from core.payments.payment_interface import PaymentInterface
from core.validation import validate_uuid


class TransactionType(Enum):
    BATCH = 'batch'
    FORCE = 'force'


def get_list_of_payments(
    requestor_eth_address:  str,
    provider_eth_address:   str,
    payment_ts:             int,
    current_time:           int,
    transaction_type:       TransactionType,
) -> list:
    """
    Function which return list of transactions from payment API
    where timestamp >= T0
    """
    assert isinstance(requestor_eth_address,    str) and len(requestor_eth_address) == ETHEREUM_ADDRESS_LENGTH
    assert isinstance(provider_eth_address,     str) and len(provider_eth_address)  == ETHEREUM_ADDRESS_LENGTH
    assert isinstance(payment_ts,               int) and payment_ts     >= 0
    assert isinstance(current_time,             int) and current_time   > 0
    assert isinstance(transaction_type,         Enum) and transaction_type in TransactionType

    payment_interface: SmartContractsInterface = PaymentInterface()

    last_block_before_payment = BlocksHelper(payment_interface).get_first_block_after(payment_ts).number

    if transaction_type == TransactionType.FORCE:
        payments_list = payment_interface.get_forced_payments(  # pylint: disable=no-member
            requestor_address   = Web3.toChecksumAddress(requestor_eth_address),
            provider_address    = Web3.toChecksumAddress(provider_eth_address),
            from_block          = last_block_before_payment,
            to_block            = payment_interface.get_block_number(),  # pylint: disable=no-member
        )
    elif transaction_type == TransactionType.BATCH:
        payments_list = payment_interface.get_batch_transfers(  # pylint: disable=no-member
            payer_address   = Web3.toChecksumAddress(requestor_eth_address),
            payee_address   = Web3.toChecksumAddress(provider_eth_address),
            from_block      = last_block_before_payment,
            to_block        = payment_interface.get_block_number(),  # pylint: disable=no-member
        )

    return payments_list


def make_force_payment_to_provider(
    requestor_eth_address:  str,
    provider_eth_address:   str,
    value:                  int,
    payment_ts:             int,
) -> str:
    """
    Concent makes transaction from requestor's deposit to provider's account on amount 'value'.
    If there is less then 'value' on requestor's deposit, Concent transfers as much as possible.
    """
    assert isinstance(requestor_eth_address,    str) and len(requestor_eth_address) == ETHEREUM_ADDRESS_LENGTH
    assert isinstance(provider_eth_address,     str) and len(provider_eth_address)  == ETHEREUM_ADDRESS_LENGTH
    assert isinstance(payment_ts,               int) and payment_ts   >= 0
    assert isinstance(value,                    int) and value        >= 0

    requestor_account_balance = PaymentInterface().get_deposit_value(Web3.toChecksumAddress(requestor_eth_address))  # type: ignore  # pylint: disable=no-member
    if requestor_account_balance < value:
        value = requestor_account_balance

    return PaymentInterface().force_payment(  # type: ignore  # pylint: disable=no-member
        requestor_address   = Web3.toChecksumAddress(requestor_eth_address),
        provider_address    = Web3.toChecksumAddress(provider_eth_address),
        value               = value,
        closure_time        = payment_ts,
    )


def get_transaction_count() -> int:
    return PaymentInterface().get_transaction_count()  # type: ignore  # pylint: disable=no-member


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
    assert isinstance(value, int) and value > 0
    assert isinstance(subtask_id, str)

    return PaymentInterface().force_subtask_payment(  # type: ignore  # pylint: disable=no-member
        requestor_address=Web3.toChecksumAddress(requestor_eth_address),
        provider_address=Web3.toChecksumAddress(provider_eth_address),
        value=value,
        subtask_id=_hexencode_uuid(subtask_id),
    )


def cover_additional_verification_cost(
    provider_eth_address: str,
    value: int,
    subtask_id: str,
) -> str:
    assert isinstance(provider_eth_address, str) and len(provider_eth_address) == ETHEREUM_ADDRESS_LENGTH
    assert isinstance(value, int) and value > 0
    assert isinstance(subtask_id, str)

    return PaymentInterface().cover_additional_verification_cost(  # type: ignore  # pylint: disable=no-member
        address=Web3.toChecksumAddress(provider_eth_address),
        value=value,
        subtask_id=_hexencode_uuid(subtask_id),
    )


def _hexencode_uuid(value: str) -> bytes:
    validate_uuid(value)

    return binascii.hexlify(uuid.UUID(value).bytes)
