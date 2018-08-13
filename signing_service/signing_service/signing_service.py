import argparse
import logging.config
import os
import signal
import socket
from contextlib import closing
from time import sleep

from ethereum.transactions import InvalidTransaction
from ethereum.transactions import Transaction
from golem_messages.cryptography import privtopub
from golem_messages.exceptions import MessageError
from mypy.types import Union
from raven import Client

from middleman_protocol.concent_golem_messages.message import SignedTransaction
from middleman_protocol.concent_golem_messages.message import TransactionRejected
from middleman_protocol.concent_golem_messages.message import TransactionSigningRequest
from middleman_protocol.constants import ErrorCode
from middleman_protocol.constants import PayloadType
from middleman_protocol.exceptions import FrameInvalidMiddlemanProtocolError
from middleman_protocol.exceptions import PayloadInvalidMiddlemanProtocolError
from middleman_protocol.exceptions import PayloadTypeInvalidMiddlemanProtocolError
from middleman_protocol.exceptions import RequestIdInvalidTypeMiddlemanProtocolError
from middleman_protocol.exceptions import SignatureInvalidMiddlemanProtocolError
from middleman_protocol.message import AbstractFrame
from middleman_protocol.message import ErrorFrame
from middleman_protocol.message import GolemMessageFrame
from middleman_protocol.stream import send_over_stream
from middleman_protocol.stream import unescape_stream

from signing_service.constants import REQUEST_ID_FOR_RESPONSE_FOR_INVALID_FRAME
from signing_service.constants import SIGNING_SERVICE_DEFAULT_PORT
from signing_service.constants import SIGNING_SERVICE_DEFAULT_INITIAL_RECONNECT_DELAY  # pylint: disable=no-name-in-module
from signing_service.constants import SIGNING_SERVICE_MAXIMUM_RECONNECT_TIME
from signing_service.constants import SIGNING_SERVICE_RECOVERABLE_ERRORS
from signing_service.exceptions import SigningServiceUnexpectedMessageError
from signing_service.exceptions import SigningServiceValidationError
from signing_service.utils import is_private_key_valid
from signing_service.utils import is_public_key_valid
from signing_service.utils import make_secret_provider_factory


logger = logging.getLogger()
crash_logger = logging.getLogger('crash')


class SigningService:
    """
    The Signing Service connects to Middleman as a client but then listens for requests coming from Concent via
    Middleman. The underlying protocol is TCP and data sent over that is expected to conform to the Wire protocol.
    """

    __slots__ = (
        'host',
        'port',
        'initial_reconnect_delay',
        'current_reconnect_delay',
        'socket',
        'was_sigterm_caught',
        'concent_public_key',
        'signing_service_private_key',
        'signing_service_public_key',
        'ethereum_private_key',
    )

    def __init__(
        self,
        host: str,
        port: int,
        initial_reconnect_delay: int,
        concent_public_key: bytes,
        signing_service_private_key: bytes,
        ethereum_private_key: bytes,
    ) -> None:
        assert isinstance(host, str)
        assert isinstance(port, int)
        assert isinstance(initial_reconnect_delay, int)
        assert isinstance(concent_public_key, bytes)
        assert isinstance(signing_service_private_key, bytes)
        assert isinstance(ethereum_private_key, str)
        self.host = host  # type: str
        self.port = port  # type: int
        self.initial_reconnect_delay = initial_reconnect_delay
        self.concent_public_key = concent_public_key  # type: bytes
        self.signing_service_private_key = signing_service_private_key  # type: bytes
        self.signing_service_public_key = privtopub(signing_service_private_key)
        self.ethereum_private_key = ethereum_private_key  # type: str
        self.current_reconnect_delay = None  # type: Union[int, None]
        self.was_sigterm_caught = False

        self._validate_arguments()

    def run(self) -> None:
        """
        Handles main connection loop and its exceptions.

        If connection is interrupted due to a failure, it should try to reconnect.
        If connection is closed by other side, exit gracefully.
        If a shutdown signal or KeyboardInterrupt is caught, exit gracefully.
        If there was an unrecognized exception, it logs it and report to Sentry, then reraise and crash.
        """

        def _set_was_sigterm_caught_true(signum, frame):  # pylint: disable=unused-argument
            logger.info('Closing connection and exiting on SIGTERM.')
            self.was_sigterm_caught = True

        # Handle shutdown signal.
        signal.signal(signal.SIGTERM, _set_was_sigterm_caught_true)

        while not self._was_sigterm_caught():
            with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as tcp_socket:
                try:
                    self._connect(tcp_socket)
                except socket.error as exception:
                    logger.error(f'Socket error occurred: {exception}')

                    # Only predefined list of exceptions should cause reconnect, others should be reraised.
                    if isinstance(exception.args, tuple) and exception.args[0] not in SIGNING_SERVICE_RECOVERABLE_ERRORS:  # type: ignore
                        raise

                    # Increase delay and reconnect if the connection is interrupted due to a failure.
                    self._increase_delay()
                except KeyboardInterrupt:
                    # Handle keyboard interrupt.
                    logger.info('Closing connection and exiting on KeyboardInterrupt.')
                    break
                except Exception as exception:
                    # If there was an unrecognized exception, log it and report to Sentry.
                    crash_logger.error(f'Unrecognized exception occurred: {exception}')
                    raise

    def _connect(self, tcp_socket: socket.socket) -> None:
        """ Creates socket and connects to given HOST and PORT. """
        if self.current_reconnect_delay is not None:
            logger.info(f'Waiting {self.current_reconnect_delay} before connecting.')
            sleep(self.current_reconnect_delay)

        logger.info(f'Connecting to {self.host}:{self.port}.')
        tcp_socket.connect((self.host, self.port))
        logger.info(f'Connection established.')

        # Reset delay on successful connection and set flag that connection is established.
        self.current_reconnect_delay = None
        self._handle_connection(tcp_socket)

    def _handle_connection(self, tcp_socket: socket.socket) -> None:
        """ Inner loop that handles data exchange over socket. """
        receive_frame_generator = unescape_stream(connection=tcp_socket)

        for raw_message_received in receive_frame_generator:
            try:
                middleman_message = AbstractFrame.deserialize(
                    raw_message_received,
                    public_key=self.concent_public_key,
                )

                if (
                    not middleman_message.payload_type == PayloadType.GOLEM_MESSAGE or
                    not isinstance(middleman_message.payload, TransactionSigningRequest)
                ):
                    raise SigningServiceUnexpectedMessageError

            # Is the frame correct according to the protocol? If not, error code is InvalidFrame.
            except (
                FrameInvalidMiddlemanProtocolError,
                PayloadTypeInvalidMiddlemanProtocolError,
                RequestIdInvalidTypeMiddlemanProtocolError,
            ) as exception:
                middleman_message_response = self._prepare_error_response(ErrorCode.InvalidFrame, exception)
            # Is frame signature correct? If not, error code is InvalidFrameSignature.
            except SignatureInvalidMiddlemanProtocolError as exception:
                middleman_message_response = self._prepare_error_response(ErrorCode.InvalidFrameSignature, exception)
            # Is the content of the message valid? Do types match the schema and all values are within allowed ranges?
            # If not, error code is InvalidPayload.
            # Can the payload be decoded as a Golem message? If not, error code is InvalidPayload.
            # Is payload message signature correct? If not, error code is InvalidPayload.
            except (MessageError, PayloadInvalidMiddlemanProtocolError) as exception:
                middleman_message_response = self._prepare_error_response(ErrorCode.InvalidPayload, exception)
            # Is frame type GOLEM_MESSAGE? If not, error code is UnexpectedMessage.
            # Is Golem message type TransactionSigningRequest? If not, error code is UnexpectedMessage.
            except SigningServiceUnexpectedMessageError as exception:
                middleman_message_response = self._prepare_error_response(ErrorCode.UnexpectedMessage, exception)
            # If received frame is correct, validate transaction.
            else:
                golem_message_response = self._get_signed_transaction(middleman_message.payload)
                golem_message_response.sign_message(private_key=self.signing_service_private_key)
                middleman_message_response = GolemMessageFrame(
                    payload=golem_message_response,
                    request_id=middleman_message.request_id,
                )

            logger.info(
                f'Sending Middleman protocol message with request_id: {middleman_message_response.request_id}.'
            )
            send_over_stream(
                connection=tcp_socket,
                raw_message=middleman_message_response,
                private_key=self.signing_service_private_key,
            )

    @staticmethod
    def _prepare_error_response(error_code, exception_object):
        logger.info(
            f'Deserializing received Middleman protocol message failed with exception: {exception_object}.'
        )
        return ErrorFrame(
            payload=(error_code, str(exception_object)),
            request_id=REQUEST_ID_FOR_RESPONSE_FOR_INVALID_FRAME,
        )

    def _increase_delay(self) -> None:
        """ Increase current delay if connection cannot be established. """
        assert self.current_reconnect_delay is None or self.current_reconnect_delay >= 0

        if self.current_reconnect_delay is None:
            self.current_reconnect_delay = self.initial_reconnect_delay  # type: ignore
        else:
            self.current_reconnect_delay = min(self.current_reconnect_delay * 2, SIGNING_SERVICE_MAXIMUM_RECONNECT_TIME)

    def _was_sigterm_caught(self):
        """ Helper function which checks if SIGTERM signal was caught. """
        return self.was_sigterm_caught

    def _validate_arguments(self):
        if not 0 < self.port < 65535:
            raise SigningServiceValidationError('Port must be 0-65535.')

        if self.initial_reconnect_delay < 0:
            raise SigningServiceValidationError('reconnect_delay must be non-negative integer.')

        if not is_public_key_valid(self.concent_public_key):
            raise SigningServiceValidationError('concent_public_key is not valid public key.')

        if not is_private_key_valid(self.ethereum_private_key):
            raise SigningServiceValidationError('ethereum_private_key is not valid private key.')

    def _get_signed_transaction(
        self,
        transaction_signing_request: TransactionSigningRequest
    ) -> Union[SignedTransaction, TransactionRejected]:
        """
        This function verifies if data in received TransactionSigningRequest can be used to correctly instantiate
        Ethereum Transaction object, signs this transaction, and handles related errors.

        Returns Golem messages SignedTransaction if transaction was signed correctly, otherwise TransactionRejected.

        """
        assert isinstance(transaction_signing_request, TransactionSigningRequest)

        try:
            transaction = Transaction(
                nonce    = transaction_signing_request.nonce,
                gasprice = transaction_signing_request.gasprice,
                startgas = transaction_signing_request.startgas,
                to       = transaction_signing_request.to,
                value    = transaction_signing_request.value,
                data     = transaction_signing_request.data,
            )
        except (InvalidTransaction, TypeError):
            # Is it possible to load the transaction using the library we're using to sign it?
            # If not, rejection reason is InvalidTransaction
            return TransactionRejected(
                reason=TransactionRejected.REASON.InvalidTransaction,
            )

        # If transaction is correct, sign it.
        try:
            transaction.sign(self.ethereum_private_key)
        except (InvalidTransaction, TypeError):
            # Does the transaction execute a function from the contract that the service has the private key for?
            # If not, rejection reason is UnauthorizedAccount.
            return TransactionRejected(
                reason=TransactionRejected.REASON.UnauthorizedAccount,
            )

        assert transaction.v is not None
        assert transaction.r is not None
        assert transaction.s is not None

        # Respond with SignedTransaction.
        return SignedTransaction(
            nonce    = transaction_signing_request.nonce,
            gasprice = transaction_signing_request.gasprice,
            startgas = transaction_signing_request.startgas,
            to       = transaction_signing_request.to,
            value    = transaction_signing_request.value,
            data     = transaction_signing_request.data,
            v        = transaction.v,
            r        = transaction.r,
            s        = transaction.s,
        )


def _parse_arguments() -> argparse.Namespace:

    parser = argparse.ArgumentParser()
    parser.add_argument(
        'concent_cluster_host',
        help='Host or IP address of a service on Concent cluster, to which SigningService connects over TCP.',
    )
    parser.add_argument(
        'concent_public_key',
        action=make_secret_provider_factory(read_command_line=True, base64_convert=True),
        help="Concent's public key.",
    )
    parser.add_argument(
        '-i',
        '--initial_reconnect_delay',
        default=SIGNING_SERVICE_DEFAULT_INITIAL_RECONNECT_DELAY,
        type=int,
        help='Initial delay between reconnections, doubles after each unsuccessful attempt and is reset after success.',
    )
    parser.add_argument(
        '-p',
        '--concent-cluster-port',
        default=SIGNING_SERVICE_DEFAULT_PORT,
        dest='concent_cluster_port',
        type=int,
        help=f'Port on which Concent cluster is listening (default: {SIGNING_SERVICE_DEFAULT_PORT}).',
    )

    ethereum_private_key_parser_group = parser.add_mutually_exclusive_group(required=True)
    ethereum_private_key_parser_group.add_argument(
        '--ethereum-private-key',
        dest='ethereum_private_key',
        action=make_secret_provider_factory(read_command_line=True, base64_convert=True, string_decode=True),
        help='Ethereum private key for Singing Service.',
    )
    ethereum_private_key_parser_group.add_argument(
        '--ethereum-private-key-path',
        dest='ethereum_private_key',
        action=make_secret_provider_factory(use_file=True, base64_convert=True, string_decode=True),
        help='Ethereum private key for Singing Service.',
    )
    ethereum_private_key_parser_group.add_argument(
        '--ethereum-private-key-from-env',
        dest='ethereum_private_key',
        action=make_secret_provider_factory(env_variable_name='ETHEREUM_PRIVATE_KEY', base64_convert=True, string_decode=True),
        help='Ethereum private key for Singing Service.',
    )

    signing_service_private_key_parser_group = parser.add_mutually_exclusive_group(required=True)
    signing_service_private_key_parser_group.add_argument(
        '--signing-service-private-key',
        dest='signing_service_private_key',
        action=make_secret_provider_factory(read_command_line=True, base64_convert=True),
        help='Singing Service private key.',
    )
    signing_service_private_key_parser_group.add_argument(
        '--signing-service-private-key-path',
        dest='signing_service_private_key',
        action=make_secret_provider_factory(use_file=True, base64_convert=True),
        help='Singing Service private key.',
    )
    signing_service_private_key_parser_group.add_argument(
        '--signing-service-private-key-from-env',
        dest='signing_service_private_key',
        action=make_secret_provider_factory(env_variable_name='SIGNING_SERVICE_PRIVATE_KEY', base64_convert=True),
        help='Singing Service private key.',
    )

    sentry_dsn_parser_group = parser.add_mutually_exclusive_group()
    sentry_dsn_parser_group.add_argument(
        '-s',
        '--sentry-dsn',
        dest='sentry_dsn',
        action=make_secret_provider_factory(read_command_line=True),
        help='Sentry DSN for error reporting.',
    )
    sentry_dsn_parser_group.add_argument(
        '--sentry-dsn-path',
        dest='sentry_dsn',
        action=make_secret_provider_factory(use_file=True),
        help='Sentry DSN for error reporting.',
    )
    sentry_dsn_parser_group.add_argument(
        '--sentry-dsn-from-env',
        dest='sentry_dsn',
        action=make_secret_provider_factory(env_variable_name='SENTRY_DSN'),
        help='Sentry DSN for error reporting.',
    )

    return parser.parse_args()


if __name__ == '__main__':
    logging.config.fileConfig(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'logging.ini'))

    # Parse required arguments.
    args = _parse_arguments()

    raven_client = Client(dsn=args.sentry_dsn)
    crash_logger.handlers[0].client = raven_client  # type: ignore

    arg_host = args.concent_cluster_host
    arg_port = args.concent_cluster_port
    arg_initial_reconnect_delay = args.initial_reconnect_delay
    arg_concent_public_key = args.concent_public_key
    arg_signing_service_private_key = args.signing_service_private_key
    arg_ethereum_private_key = args.ethereum_private_key

    SigningService(
        arg_host,
        arg_port,
        arg_initial_reconnect_delay,
        arg_concent_public_key,
        arg_signing_service_private_key,
        arg_ethereum_private_key,
    ).run()
