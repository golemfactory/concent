import argparse
import logging.config
import os
import signal
import socket
from contextlib import closing
from time import sleep

from exceptions import SigningServiceValidationError  # pylint: disable=no-name-in-module
from raven import Client

from constants import SIGNING_SERVICE_DEFAULT_PORT  # pylint: disable=no-name-in-module
from constants import SIGNING_SERVICE_MAXIMUM_RECONNECT_TIME  # pylint: disable=no-name-in-module
from constants import SIGNING_SERVICE_RECOVERABLE_ERRORS  # pylint: disable=no-name-in-module


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
    )

    def __init__(self, host, port, initial_reconnect_delay) -> None:
        assert isinstance(host, str)
        assert isinstance(port, int)
        assert isinstance(initial_reconnect_delay, int)
        self.host = host
        self.port = port
        self.initial_reconnect_delay = initial_reconnect_delay
        self.current_reconnect_delay = None
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

    def _handle_connection(self, tcp_socket: socket.socket) -> None:  # pylint: disable=no-self-use
        """ Inner loop that handles data exchange over socket. """
        while True:
            data = tcp_socket.recv(1024)
            tcp_socket.send(data)

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


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        'concent_cluster_host',
        help='Host or IP address of a service on Concent cluster, to which SigningService connects over TCP.',
    )
    parser.add_argument(
        'initial_reconnect_delay',
        type=int,
        help='Initial delay between reconnections, doubles after each unsuccessful attempt and is reset after success.',
    )
    parser.add_argument(
        '--concent-cluster-port',
        default=SIGNING_SERVICE_DEFAULT_PORT,
        dest='concent_cluster_port',
        type=int,
        help=f'Port on which Concent cluster is listening (default: {SIGNING_SERVICE_DEFAULT_PORT}).',
    )
    parser.add_argument(
        '--sentry-dsn',
        default='',
        dest='sentry_dsn',
        help=f'Sentry DSN for error reporting.',
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

    SigningService(arg_host, arg_port, arg_initial_reconnect_delay).run()
