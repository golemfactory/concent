from contextlib import closing
import socket

from bitcoin import ecdsa_raw_verify
from ethereum.utils import sha3
from ethereum.transactions import UnsignedTransaction
from ethereum.transactions import Transaction
from golem_messages.exceptions import InvalidSignature
from golem_messages.exceptions import MessageError
from rlp import encode

from django.conf import settings

from common.helpers import generate_ethereum_address_from_ethereum_public_key_bytes
from core.constants import SCI_CALLBACK_MAXIMUM_TIMEOUT
from core.exceptions import SCICallbackFrameError
from core.exceptions import SCICallbackPayloadError
from core.exceptions import SCICallbackPayloadSignatureError
from core.exceptions import SCICallbackRequestIdError
from core.exceptions import SCICallbackTimeoutError
from core.exceptions import SCICallbackTransactionSignatureError

from middleman_protocol.concent_golem_messages.message import SignedTransaction
from middleman_protocol.concent_golem_messages.message import TransactionRejected
from middleman_protocol.concent_golem_messages.message import TransactionSigningRequest
from middleman_protocol.exceptions import MiddlemanProtocolError
from middleman_protocol.message import ErrorFrame
from middleman_protocol.message import GolemMessageFrame
from middleman_protocol.stream import send_over_stream
from middleman_protocol.stream import unescape_stream


class RequestIDGenerator:

    _request_id = 0

    @classmethod
    def generate_request_id(cls) -> int:
        cls._request_id += 1
        return cls._request_id


def sci_callback(transaction: Transaction) -> Transaction:
    """
    This is callback that submits the transaction to the Signing Service
    and does not rely on having access to the private key.

    Returns signed Ethereum Transaction.
    """
    assert isinstance(transaction, Transaction)

    # Create a TransactionSigningRequest.
    transaction_signing_request = create_transaction_signing_request(transaction)

    # Generate request ID.
    request_id = RequestIDGenerator.generate_request_id()

    # Create a MiddleMan Protocol Golem Message Frame.
    middleman_message = GolemMessageFrame(
        payload=transaction_signing_request,
        request_id=request_id,
    )

    # Send Frame to MiddleMan through MiddleMan Protocol and receive response.
    raw_response = send_request_to_middleman(middleman_message)

    # Deserialize received Frame and its payload and handle related errors.
    signed_transaction = deserialize_response_and_handle_errors(raw_response, request_id)

    assert isinstance(signed_transaction, SignedTransaction)

    # Verify received SignedTransaction signature and handle related errors.
    verify_data_and_signature(signed_transaction, transaction)

    # If the response is a valid SignedTransaction, copy received signature into Transaction.
    copy_transaction_signature(signed_transaction, transaction)
    return transaction


def create_transaction_signing_request(transaction: Transaction) -> TransactionSigningRequest:
    """ Create TransactionSigningRequest message from given Ethereum Transaction object. """

    assert isinstance(transaction, Transaction)

    transaction_signing_request = TransactionSigningRequest(
        nonce    = transaction.nonce,
        gasprice = transaction.gasprice,
        startgas = transaction.startgas,
        to       = transaction.to,
        value    = transaction.value,
        data     = transaction.data,
    )

    setattr(
        transaction_signing_request,
        'from',
        generate_ethereum_address_from_ethereum_public_key_bytes(settings.CONCENT_ETHEREUM_PUBLIC_KEY),
    )

    return transaction_signing_request


def send_request_to_middleman(middleman_message: GolemMessageFrame) -> bytes:
    """
    Opens socket connection to Middleman, sends Frame to MiddleMan through MiddleMan Protocol and receive response.

    Returns raw Frame as bytes.
    """

    assert isinstance(middleman_message, GolemMessageFrame)

    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as client_socket:
        client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
        client_socket.connect((settings.MIDDLEMAN_ADDRESS, settings.MIDDLEMAN_PORT))
        client_socket.settimeout(SCI_CALLBACK_MAXIMUM_TIMEOUT)

        # Send the TransactionSigningRequest.
        try:
            send_over_stream(
                connection=client_socket,
                raw_message=middleman_message,
                private_key=settings.CONCENT_PRIVATE_KEY,
            )

            # Read the response and close the connection.
            return next(unescape_stream(connection=client_socket))
        # Connection with Middleman times out before a complete response is received.
        except socket.timeout as exception:
            raise SCICallbackTimeoutError() from exception


def deserialize_response_and_handle_errors(raw_response: bytes, request_id: int) -> SignedTransaction:
    """
    Deserialize received Frame and its payload and handle related errors.

    Returns SignedTransaction message.
    """

    assert isinstance(raw_response, bytes)
    assert isinstance(request_id, int)

    try:
        deserialized_message = GolemMessageFrame.deserialize(
            raw_message=raw_response,
            public_key=settings.CONCENT_PUBLIC_KEY,
        )
    # Received data frame is invalid or the signature does not match its content.
    except MiddlemanProtocolError as exception:
        raise SCICallbackFrameError() from exception
    # If the received Golem message is malformed.
    except MessageError as exception:
        raise SCICallbackPayloadError() from exception

    if deserialized_message.request_id != request_id:
        raise SCICallbackRequestIdError('MiddleMan response request_id does not match requested.')

    if isinstance(deserialized_message, ErrorFrame):
        raise SCICallbackPayloadError(
            'Received frame is ErrorFrame.'
        )

    if isinstance(deserialized_message.payload, TransactionRejected):
        raise SCICallbackPayloadError(
            'Received frame is contains Golem message TransactionRejected.'
        )

    if not isinstance(deserialized_message.payload, SignedTransaction):
        raise SCICallbackPayloadError('Received frame payload is not Golem message SignedTransaction instance.')

    # If the received Golem message is not signed by the Signing Service.
    try:
        deserialized_message.payload.verify_signature(settings.SIGNING_SERVICE_PUBLIC_KEY)
    except InvalidSignature as exception:
        raise SCICallbackPayloadSignatureError() from exception

    return deserialized_message.payload


def verify_data_and_signature(signed_transaction: SignedTransaction, transaction: Transaction) -> None:
    """
    Verify received SignedTransaction data and signature and handle related errors.

    1. Check if received SignedTransaction data match original Ethereum Transacion.
    2. Check if received signature is created for given message with given keys pair.
    """

    assert isinstance(signed_transaction, SignedTransaction)
    assert isinstance(transaction, Transaction)

    if not is_signed_transaction_data_equal_to_transaction_data(signed_transaction, transaction):
        raise SCICallbackPayloadError('Received SignedTransaction does not match TransactionSigningRequest.')

    # If the Ethereum signature in SignedTransaction is not a valid signature or
    # or the transaction in SignedTransaction is not signed with the right Ethereum private key.
    message_hash = sha3(encode(transaction, UnsignedTransaction))

    if not ecdsa_raw_verify(
        message_hash,
        (
            signed_transaction.v,
            signed_transaction.r,
            signed_transaction.s,
        ),
        settings.CONCENT_ETHEREUM_PUBLIC_KEY,
    ):
        raise SCICallbackTransactionSignatureError(
            'Received SignedTransaction signature data is not signed by right Ethereum private key.'
        )


def is_signed_transaction_data_equal_to_transaction_data(
    signed_transaction: SignedTransaction,
    transaction: Transaction
) -> bool:
    """ Compare SignedTransaction message data with Ethereum Transaction data. """

    assert isinstance(signed_transaction, SignedTransaction)
    assert isinstance(transaction, Transaction)

    return (
        signed_transaction.nonce == transaction.nonce and
        signed_transaction.gasprice == transaction.gasprice and
        signed_transaction.startgas == transaction.startgas and
        signed_transaction.to == transaction.to and
        signed_transaction.value == transaction.value and
        signed_transaction.data == transaction.data
    )


def copy_transaction_signature(signed_transaction: SignedTransaction, transaction: Transaction) -> Transaction:
    """ Copy signature from SignedTransaction into Ethereum Transaction. """

    assert isinstance(signed_transaction, SignedTransaction)
    assert isinstance(transaction, Transaction)

    transaction.v = signed_transaction.v
    transaction.r = signed_transaction.r
    transaction.s = signed_transaction.s
