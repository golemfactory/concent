import enum
from typing import Any

from golem_messages.message.base import Message
from golem_messages.register import library
from golem_messages.validators import validate_integer
from golem_messages.validators import validate_varchar

from middleman_protocol.concent_golem_messages.validators import validate_bytes
from middleman_protocol.concent_golem_messages.validators import validate_maximum_int_length


CONCENT_CUSTOM_MSG_BASE = 9000


class NonceAbstractMessage(Message):
    """
    Abstract message containing `nonce` field and its validation.
    """

    __slots__ = [
        'nonce',
    ] + Message.__slots__

    def deserialize_slot(self, key: str, value: Any) -> Any:
        value = super().deserialize_slot(key, value)
        if key == 'nonce':
            validate_integer(
                field_name=key,
                value=value,
            )
            validate_maximum_int_length(
                field_name=key,
                value=value,
                maximum_allowed_length=78,
            )
        return value


class TransactionAbstractMessage(NonceAbstractMessage):
    """
    Abstract message containing transaction data and its validation.
    """

    __slots__ = [
        'gasprice',
        'startgas',
        'to',
        'value',
        'data',
    ] + NonceAbstractMessage.__slots__

    def deserialize_slot(self, key: str, value: Any) -> Any:
        value = super().deserialize_slot(key, value)
        if key == 'to':
            validate_varchar(
                field_name=key,
                value=value,
                max_length=20,
            )
        if key == 'data':
            validate_bytes(
                field_name=key,
                value=value,
            )
        if key in ('gasprice', 'startgas', 'value'):
            validate_integer(
                field_name=key,
                value=value
            )
            validate_maximum_int_length(
                field_name=key,
                value=value,
                maximum_allowed_length=78,
            )
        return value


@library.register(CONCENT_CUSTOM_MSG_BASE + 1)
class TransactionSigningRequest(TransactionAbstractMessage):
    """
    Message sent from SCI transaction signing callback to a Concent,
    containing data about transaction which client wants to sign using SigningService.
    """

    __slots__ = [
        'from',
    ] + TransactionAbstractMessage.__slots__

    def deserialize_slot(self, key: str, value: Any) -> Any:
        value = super().deserialize_slot(key, value)
        if key == 'from':
            validate_varchar(
                field_name=key,
                value=value,
                max_length=20,
            )
        return value


@library.register(CONCENT_CUSTOM_MSG_BASE + 2)
class SignedTransaction(TransactionAbstractMessage):
    """
    Message sent from SigningService to the Concent,
    if transaction was successfully signed,
    containing data about transaction and its signature.

    Concent should copy the signature data to the transaction object passed
    to the callback by SCI.
    """

    __slots__ = [
        'v',
        'r',
        's',
    ] + TransactionAbstractMessage.__slots__

    def deserialize_slot(self, key: str, value: Any) -> Any:
        value = super().deserialize_slot(key, value)
        if key in ('v', 'r', 's'):
            validate_integer(
                field_name=key,
                value=value,
            )
        if key == 'v':
            validate_maximum_int_length(
                field_name=key,
                value=value,
                maximum_allowed_length=3,
            )
        if key in ('r', 's'):
            validate_maximum_int_length(
                field_name=key,
                value=value,
                maximum_allowed_length=78,
            )
        return value


@library.register(CONCENT_CUSTOM_MSG_BASE + 3)
class TransactionRejected(NonceAbstractMessage):
    """
    Message sent from SigningService to the Concent,
    if transaction cannot be signed from any of various reasons.
    """

    @enum.unique
    class REASON(enum.Enum):
        # The message itself is valid but does not describe a valid Ethereum
        # transaction. Use this if it passes our validations but the Ethereum
        # library still rejects it for any reason.
        InvalidTransaction = 'invalid_transaction'
        # The service is not authorized to transfer funds from the account
        # specified in the transaction.
        UnauthorizedAccount = 'unauthorized_account'

    ENUM_SLOTS = {
        'reason': REASON,
    }

    __slots__ = [
        'reason',
    ] + NonceAbstractMessage.__slots__
