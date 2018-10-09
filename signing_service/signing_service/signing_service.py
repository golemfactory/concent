import argparse
import logging.config
import os
import signal
import socket
from contextlib import closing
from time import sleep
from types import FrameType
from typing import Iterator
from typing import Optional

from ethereum.transactions import InvalidTransaction
from ethereum.transactions import Transaction
from golem_messages.cryptography import ecdsa_sign
from golem_messages.cryptography import privtopub
from golem_messages.exceptions import MessageError
from mypy.types import Union
from raven import Client

from middleman_protocol.concent_golem_messages.message import SignedTransaction
from middleman_protocol.concent_golem_messages.message import TransactionRejected
from middleman_protocol.concent_golem_messages.message import TransactionSigningRequest
from middleman_protocol.constants import ErrorCode
from middleman_protocol.constants import PayloadType
from middleman_protocol.constants import REQUEST_ID_FOR_RESPONSE_FOR_INVALID_FRAME
from middleman_protocol.exceptions import FrameInvalidMiddlemanProtocolError
from middleman_protocol.exceptions import MiddlemanProtocolError
from middleman_protocol.exceptions import PayloadInvalidMiddlemanProtocolError
from middleman_protocol.exceptions import PayloadTypeInvalidMiddlemanProtocolError
from middleman_protocol.exceptions import RequestIdInvalidTypeMiddlemanProtocolError
from middleman_protocol.exceptions import SignatureInvalidMiddlemanProtocolError
from middleman_protocol.message import AbstractFrame
from middleman_protocol.message import AuthenticationChallengeFrame
from middleman_protocol.message import AuthenticationResponseFrame
from middleman_protocol.message import ErrorFrame
from middleman_protocol.message import GolemMessageFrame
from middleman_protocol.stream import send_over_stream
from middleman_protocol.stream import unescape_stream

from signing_service.constants import CONNECTION_TIMEOUT
from signing_service.constants import RECEIVE_AUTHENTICATION_CHALLENGE_TIMEOUT
from signing_service.constants import SIGNING_SERVICE_DEFAULT_INITIAL_RECONNECT_DELAY
from signing_service.constants import SIGNING_SERVICE_DEFAULT_PORT
from signing_service.constants import SIGNING_SERVICE_DEFAULT_RECONNECT_ATTEMPTS
from signing_service.constants import SIGNING_SERVICE_MAXIMUM_RECONNECT_TIME
from signing_service.exceptions import SigningServiceMaximumReconnectionAttemptsExceeded
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
        'reconnection_counter',
        'maximum_reconnection_attempts',
    )

    def __init__(
        self,
        host: str,
        port: int,
        initial_reconnect_delay: int,
        concent_public_key: bytes,
        signing_service_private_key: bytes,
        ethereum_private_key: str,
        maximum_reconnect_attempts: int,
    ) -> None:
        assert isinstance(host, str)
        assert isinstance(port, int)
        assert isinstance(initial_reconnect_delay, int)
        assert isinstance(concent_public_key, bytes)
        assert isinstance(signing_service_private_key, bytes)
        assert isinstance(ethereum_private_key, str)
        self.host = host  # type: str
        self.port = port  # type: int
        self.initial_reconnect_delay: int = initial_reconnect_delay
        self.concent_public_key = concent_public_key  # type: bytes
        self.signing_service_private_key = signing_service_private_key  # type: bytes
        self.signing_service_public_key = privtopub(signing_service_private_key)
        self.ethereum_private_key = ethereum_private_key  # type: str
        self.current_reconnect_delay: Union[int, None] = None
        self.was_sigterm_caught: bool = False
        self.reconnection_counter = 0
        self.maximum_reconnection_attempts = maximum_reconnect_attempts

        self._validate_arguments()

        def _set_was_sigterm_caught_true(signum: int, frame: Optional[FrameType]) -> None:  # pylint: disable=unused-argument
            logger.info('Closing connection and exiting on SIGTERM.')
            self.was_sigterm_caught = True

        # Handle shutdown signal.
        signal.signal(signal.SIGTERM, _set_was_sigterm_caught_true)

    def run(self) -> None:
        """
        Handles main connection loop and its exceptions.

        If connection is interrupted due to a failure, it should try to reconnect.
        If connection is closed by other side, exit gracefully.
        If a shutdown signal or KeyboardInterrupt is caught, exit gracefully.
        If there was an unrecognized exception, it logs it and report to Sentry, then reraise and crash.
        """
        while not self._was_sigterm_caught():
            with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as tcp_socket:
                try:
                    self._connect(tcp_socket)
                except (socket.error, socket.timeout) as exception:
                    logger.error(f'Socket error occurred: {exception}')

                    self._attempt_reconnection()
                except KeyboardInterrupt:
                    # Handle keyboard interrupt.
                    logger.info('Closing connection and exiting on KeyboardInterrupt.')
                    break
                except Exception as exception:
                    # If there was an unrecognized exception, log it and report to Sentry.
                    crash_logger.error(f'Unrecognized exception occurred: {exception}')
                    raise

    def _attempt_reconnection(self) -> None:
        # Increase delay and reconnect if the connection is interrupted due to a failure.
        self._increase_delay()
        self.reconnection_counter += 1
        if self.reconnection_counter > self.maximum_reconnection_attempts:
            crash_logger.error("Maximum reconnection attempts exceeded.")
            raise SigningServiceMaximumReconnectionAttemptsExceeded
        logger.info(f'Reconnecting... (attempt: {self.reconnection_counter}/{self.maximum_reconnection_attempts})')

    def _connect(self, tcp_socket: socket.socket) -> None:
        """ Creates socket and connects to given HOST and PORT. """
        if self.current_reconnect_delay is not None:
            logger.info(f'Waiting {self.current_reconnect_delay} before connecting.')
            sleep(self.current_reconnect_delay)

        logger.info(f'Connecting to {self.host}:{self.port}.')
        tcp_socket.settimeout(CONNECTION_TIMEOUT)
        tcp_socket.connect((self.host, self.port))
        logger.info(f'Connection established.')
        # Frame generator must be created here and passed to _authenticate() and _handle_connection(), because upon its
        # destruction it closes the socket.
        receive_frame_generator = unescape_stream(connection=tcp_socket)

        self._authenticate(receive_frame_generator, tcp_socket)
        # Reset delay and reconnection counter on successful authentication and set flag that connection is established.
        self.current_reconnect_delay = None
        self.reconnection_counter = 0
        self._handle_connection(receive_frame_generator, tcp_socket)

    def _authenticate(
        self,
        receive_frame_generator: Iterator[Optional[bytes]],
        tcp_socket: socket.socket
    ) -> None:
        """ Handles authentication challenge. """

        # Set timeout on socket, after which, if AuthenticationChallengeFrame is not received,
        # SigningService will have to reconnect.
        tcp_socket.settimeout(RECEIVE_AUTHENTICATION_CHALLENGE_TIMEOUT)

        # After establishing a TCP connection start listening for the AuthenticationChallengeFrame.
        try:
            raw_message_received = next(receive_frame_generator)
            authentication_challenge_frame = AbstractFrame.deserialize(
                raw_message_received,
                public_key=self.concent_public_key,
            )
            # If SigningService receive any other message that AuthenticationChallengeFrame
            # disconnect, log the incident and treat it as a failure to connect.
            if not isinstance(authentication_challenge_frame, AuthenticationChallengeFrame):
                logger.info(
                    f'SigningService received {type(authentication_challenge_frame)} instead of AuthenticationChallengeFrame.'
                )
                raise socket.error()
        # If received message is invalid or
        # if nothing was received in a predefined time,
        # disconnect, log the incident and treat it as a failure to connect.
        except (MiddlemanProtocolError, socket.timeout) as exception:
            logger.info(f'SigningService failed to receive AuthenticationChallengeFrame with exception: {exception}.')
            raise socket.error()

        # If you receive a valid challenge, sign it with the private key of the service and
        # send AuthenticationResponseFrame with signature as payload.
        authentication_response_frame = AuthenticationResponseFrame(
            payload=self._get_authentication_challenge_signature(
                authentication_challenge_frame.payload,
            ),
            request_id=authentication_challenge_frame.request_id,
        )

        try:
            send_over_stream(
                connection=tcp_socket,
                raw_message=authentication_response_frame,
                private_key=self.signing_service_private_key,
            )
        # If the server disconnects, log the incident and treat it as a failure to connect.
        except socket.error as exception:
            logger.info(
                f'MiddleMan server disconnects after receiving AuthenticationResponseFrame with exception: {exception}.'
            )
            raise socket.error()
        logger.info('Authentication successful. ')

    def _handle_connection(
        self,
        receive_frame_generator: Iterator[Optional[bytes]],
        tcp_socket: socket.socket
    ) -> None:
        """ Inner loop that handles data exchange over socket. """
        # Set socket back blocking mode.
        tcp_socket.setblocking(True)
        for raw_message_received in receive_frame_generator:
            try:
                middleman_message = AbstractFrame.deserialize(
                    raw_message_received,
                    public_key=self.concent_public_key,
                )
                # Heartbeat is received: connection is still active and Signing Service doesn't have to respond.
                if middleman_message.payload_type == PayloadType.HEARTBEAT:
                    continue

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
    def _prepare_error_response(error_code: ErrorCode, exception_object: Exception) -> ErrorFrame:
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
            self.current_reconnect_delay = self.initial_reconnect_delay
        else:
            self.current_reconnect_delay = min(self.current_reconnect_delay * 2, SIGNING_SERVICE_MAXIMUM_RECONNECT_TIME)

    def _was_sigterm_caught(self) -> bool:
        """ Helper function which checks if SIGTERM signal was caught. """
        return self.was_sigterm_caught

    def _validate_arguments(self) -> None:
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

    def _get_authentication_challenge_signature(self, authentication_challenge: bytes) -> bytes:
        """ Returns signed authentication challenge with SigningService private key. """
        assert isinstance(authentication_challenge, bytes)

        return ecdsa_sign(
            self.signing_service_private_key,
            authentication_challenge,
        )


def _parse_arguments() -> argparse.Namespace:

    parser = argparse.ArgumentParser()
    parser.add_argument(
        'concent_cluster_host',
        help='Host or IP address of a service on Concent cluster, to which SigningService connects over TCP.',
    )
    parser.add_argument(  # type: ignore
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
        '-m',
        '--max-reconnect-attempts',
        default=SIGNING_SERVICE_DEFAULT_RECONNECT_ATTEMPTS,
        type=int,
        help='Maximum number of reconnect attempts after socket error.',
    )
    parser.add_argument(
        '-p',
        '--concent-cluster-port',
        default=SIGNING_SERVICE_DEFAULT_PORT,
        dest='concent_cluster_port',
        type=int,
        help=f'Port on which Concent cluster is listening (default: {SIGNING_SERVICE_DEFAULT_PORT}).',
    )
    parser.add_argument(
        '-e',
        '--sentry-environment',
        dest='sentry_environment',
        type=str,
        help=f'Environment which will be set in Raven client config `environment` parameter.',
    )

    ethereum_private_key_parser_group = parser.add_mutually_exclusive_group(required=True)
    ethereum_private_key_parser_group.add_argument(  # type: ignore
        '--ethereum-private-key',
        dest='ethereum_private_key',
        action=make_secret_provider_factory(read_command_line=True, base64_convert=True, string_decode=True),
        help='Ethereum private key for Singing Service.',
    )
    ethereum_private_key_parser_group.add_argument(  # type: ignore
        '--ethereum-private-key-path',
        dest='ethereum_private_key',
        action=make_secret_provider_factory(use_file=True, base64_convert=True, string_decode=True),
        help='Ethereum private key for Singing Service.',
    )
    ethereum_private_key_parser_group.add_argument(  # type: ignore
        '--ethereum-private-key-from-env',
        dest='ethereum_private_key',
        action=make_secret_provider_factory(env_variable_name='ETHEREUM_PRIVATE_KEY', base64_convert=True, string_decode=True),
        help='Ethereum private key for Singing Service.',
    )

    signing_service_private_key_parser_group = parser.add_mutually_exclusive_group(required=True)
    signing_service_private_key_parser_group.add_argument(  # type: ignore
        '--signing-service-private-key',
        dest='signing_service_private_key',
        action=make_secret_provider_factory(read_command_line=True, base64_convert=True),
        help='Singing Service private key.',
    )
    signing_service_private_key_parser_group.add_argument(  # type: ignore
        '--signing-service-private-key-path',
        dest='signing_service_private_key',
        action=make_secret_provider_factory(use_file=True, base64_convert=True),
        help='Singing Service private key.',
    )
    signing_service_private_key_parser_group.add_argument(  # type: ignore
        '--signing-service-private-key-from-env',
        dest='signing_service_private_key',
        action=make_secret_provider_factory(env_variable_name='SIGNING_SERVICE_PRIVATE_KEY', base64_convert=True),
        help='Singing Service private key.',
    )

    sentry_dsn_parser_group = parser.add_mutually_exclusive_group()
    sentry_dsn_parser_group.add_argument(  # type: ignore
        '-s',
        '--sentry-dsn',
        dest='sentry_dsn',
        action=make_secret_provider_factory(read_command_line=True),
        help='Sentry DSN for error reporting.',
    )
    sentry_dsn_parser_group.add_argument(  # type: ignore
        '--sentry-dsn-path',
        dest='sentry_dsn',
        action=make_secret_provider_factory(use_file=True),
        help='Sentry DSN for error reporting.',
    )
    sentry_dsn_parser_group.add_argument(  # type: ignore
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

    raven_client = Client(
        dsn=args.sentry_dsn,
        environment=args.sentry_environment,
        tags={
            'component': 'signing-service',
        },
    )
    crash_logger.handlers[0].client = raven_client  # type: ignore

    SigningService(
        args.concent_cluster_host,
        args.concent_cluster_port,
        args.initial_reconnect_delay,
        args.concent_public_key,
        args.signing_service_private_key,
        args.ethereum_private_key,
        args.max_reconnect_attempts,
    ).run()
