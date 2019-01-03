import enum
from typing import Any
from typing import List
from typing import Union

from golem_messages.message.base import Message
from golem_messages.register import library
from golem_messages.validators import validate_integer

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

    def slots(self) -> List[List[Union[str, bytes, int]]]:
        # cbor library has issuses with big integers serialization
        # before serialization every big integer need to be convert into string
        slots = super().slots()
        if ['nonce', self.nonce] in slots:  # pylint: disable=no-member
            slots[slots.index(['nonce', self.nonce])][1] = str(self.nonce)  # pylint: disable=no-member
        return slots

    def deserialize_slot(self, key: str, value: Any) -> Any:
        value = super().deserialize_slot(key, value)
        if key == 'nonce':
            # Reverse conversion from string to integer
            value = int(value)
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

    SLOTS_TO_CONVERT = ['gasprice', 'startgas', 'value']

    def slots(self) -> List[List[Union[str, bytes, int]]]:
        # cbor library has issuses with big integers serialization
        # before serialization every big integer need to be convert into string
        slots = super().slots()
        for slot in TransactionAbstractMessage.SLOTS_TO_CONVERT:
            slot_variable = getattr(self, slot)
            slots[slots.index([slot, slot_variable])][1] = str(slot_variable)
        return slots

    def deserialize_slot(self, key: str, value: Any) -> Any:
        value = super().deserialize_slot(key, value)
        if key == 'to':
            validate_bytes(
                field_name=key,
                value=value,
                maximum_allowed_length=20,
            )
        if key == 'data':
            validate_bytes(
                field_name=key,
                value=value,
            )
        if key in TransactionAbstractMessage.SLOTS_TO_CONVERT:
            # Reverse conversion from string to integer
            value = int(value)
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
        'from_address',
    ] + TransactionAbstractMessage.__slots__

    def deserialize_slot(self, key: str, value: Any) -> Any:
        value = super().deserialize_slot(key, value)
        if key == 'from_address':
            validate_bytes(
                field_name=key,
                value=value,
                maximum_allowed_length=20,
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

    SLOTS_TO_CONVERT = ['v', 'r', 's']

    def slots(self) -> List[List[Union[str, bytes, int]]]:
        # cbor library has issuses with big integers serialization
        # before serialization every big integer need to be convert into string
        slots = super().slots()
        for slot in SignedTransaction.SLOTS_TO_CONVERT:
            slot_variable = getattr(self, slot)
            slots[slots.index([slot, slot_variable])][1] = str(slot_variable)
        return slots

    def deserialize_slot(self, key: str, value: Any) -> Any:
        value = super().deserialize_slot(key, value)
        if key in SignedTransaction.SLOTS_TO_CONVERT:
            # Reverse conversion from string to integer
            value = int(value)
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
        # The message itself is valid but daily limit of GNTB that went through Signing Service has been exceeded
        DailyLimitExceeded = 'daily_limit_exceeded'

    ENUM_SLOTS = {
        'reason': REASON,
    }

    __slots__ = [
        'reason',
    ] + NonceAbstractMessage.__slots__
