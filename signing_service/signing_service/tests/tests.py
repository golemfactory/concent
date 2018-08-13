from base64 import b64encode
from contextlib import closing
from unittest import TestCase
import os
import socket
import sys
import tempfile

from golem_messages.cryptography import ECCx
from golem_messages.message import Ping
import assertpy
import mock
import pytest

from middleman_protocol.constants import ErrorCode
from middleman_protocol.message import AbstractFrame
from middleman_protocol.message import GolemMessageFrame
from middleman_protocol.stream import append_frame_separator
from middleman_protocol.stream import escape_encode_raw_message
from middleman_protocol.stream import unescape_stream

from signing_service.constants import REQUEST_ID_FOR_RESPONSE_FOR_INVALID_FRAME
from signing_service.constants import SIGNING_SERVICE_DEFAULT_PORT
from signing_service.constants import SIGNING_SERVICE_DEFAULT_INITIAL_RECONNECT_DELAY
from signing_service.constants import SIGNING_SERVICE_RECOVERABLE_ERRORS
from signing_service.constants import SIGNING_SERVICE_MAXIMUM_RECONNECT_TIME
from signing_service.exceptions import SigningServiceValidationError
from signing_service.signing_service import _parse_arguments
from signing_service.signing_service import SigningService
from signing_service.utils import is_valid_public_key


concent_ecc_keys = ECCx(None)
(CONCENT_PRIVATE_KEY, CONCENT_PUBLIC_KEY) = concent_ecc_keys.raw_privkey, concent_ecc_keys.raw_pubkey

signing_service_ecc_keys = ECCx(None)
(SIGNING_SERVICE_PRIVATE_KEY, SIGNING_SERVICE_PUBLIC_KEY) = signing_service_ecc_keys.raw_privkey, signing_service_ecc_keys.raw_pubkey


class TestSigningServiceRun:

    host = None
    port = None
    initial_reconnect_delay = None

    @pytest.fixture(autouse=True)
    def setUp(self, unused_tcp_port_factory):
        self.host = '127.0.0.1'
        self.port = unused_tcp_port_factory()
        self.initial_reconnect_delay = 2

    def test_that_signing_service_should_be_instantiated_correctly_with_all_parameters(self):
        signing_service = SigningService(
            self.host,
            self.port,
            self.initial_reconnect_delay,
            CONCENT_PUBLIC_KEY,
            SIGNING_SERVICE_PRIVATE_KEY,
        )

        assertpy.assert_that(signing_service).is_instance_of(SigningService)
        assertpy.assert_that(signing_service.host).is_equal_to(self.host)
        assertpy.assert_that(signing_service.port).is_equal_to(self.port)
        assertpy.assert_that(signing_service.initial_reconnect_delay).is_equal_to(self.initial_reconnect_delay)

    def test_that_signing_service_should_run_full_loop_when_instantiated_with_all_parameters(self):
        with mock.patch('socket.socket.connect') as mock_socket_connect:
            with mock.patch('signing_service.signing_service.SigningService._handle_connection') as mock__handle_connection:
                with mock.patch('socket.socket.close') as mock_socket_close:
                    with mock.patch('signing_service.signing_service.SigningService._was_sigterm_caught', side_effect=[False, True]):
                        signing_service = SigningService(
                            self.host,
                            self.port,
                            self.initial_reconnect_delay,
                            CONCENT_PUBLIC_KEY,
                            SIGNING_SERVICE_PRIVATE_KEY,
                        )
                        signing_service.run()

        mock_socket_connect.assert_called_once_with(('127.0.0.1', self.port))
        mock_socket_close.assert_called_once()
        mock__handle_connection.assert_called_once()

    def test_that_signing_service_should_exit_gracefully_on_keyboard_interrupt(self):
        with mock.patch('socket.socket.connect', side_effect=KeyboardInterrupt()) as mock_socket_connect:
            with mock.patch('socket.socket.close') as mock_socket_close:
                signing_service = SigningService(
                    self.host,
                    self.port,
                    self.initial_reconnect_delay,
                    CONCENT_PUBLIC_KEY,
                    SIGNING_SERVICE_PRIVATE_KEY,
                )
                signing_service.run()

        mock_socket_connect.assert_called_once_with(('127.0.0.1', self.port))
        mock_socket_close.assert_called_once()

    def test_that_signing_service_should_reraise_unrecognized_exception(self):
        with mock.patch('socket.socket.connect', side_effect=Exception()) as mock_socket_connect:
            with mock.patch('socket.socket.close') as mock_socket_close:
                signing_service = SigningService(
                    self.host,
                    self.port,
                    self.initial_reconnect_delay,
                    CONCENT_PUBLIC_KEY,
                    SIGNING_SERVICE_PRIVATE_KEY,
                )
                with pytest.raises(Exception):
                    signing_service.run()

        mock_socket_connect.assert_called_once_with(('127.0.0.1', self.port))
        mock_socket_close.assert_called_once()

    def test_that_signing_service_should_reconnect_when_expected_socket_error_was_caught(self):
        assert socket.errno.ECONNREFUSED in SIGNING_SERVICE_RECOVERABLE_ERRORS

        with mock.patch('socket.socket.connect', side_effect=socket.error(socket.errno.ECONNREFUSED)) as mock_socket_connect:
            with mock.patch('signing_service.signing_service.SigningService._was_sigterm_caught', side_effect=[False, False, True]):
                signing_service = SigningService(
                    self.host,
                    self.port,
                    self.initial_reconnect_delay,
                    CONCENT_PUBLIC_KEY,
                    SIGNING_SERVICE_PRIVATE_KEY,
                )
                signing_service.run()

        assertpy.assert_that(mock_socket_connect.call_count).is_equal_to(2)

    def test_that_signing_service_should_reraise_different_socket_erros(self):
        assert socket.errno.EBUSY not in SIGNING_SERVICE_RECOVERABLE_ERRORS

        with mock.patch('socket.socket.connect', side_effect=socket.error(socket.errno.EBUSY)) as mock_socket_connect:
            with mock.patch('socket.socket.close') as mock_socket_close:
                signing_service = SigningService(
                    self.host,
                    self.port,
                    self.initial_reconnect_delay,
                    CONCENT_PUBLIC_KEY,
                    SIGNING_SERVICE_PRIVATE_KEY,
                )
                with pytest.raises(socket.error):
                    signing_service.run()

        mock_socket_connect.assert_called_once_with(('127.0.0.1', self.port))
        mock_socket_close.assert_called_once()


class TestSigningServiceHandleConnection:

    host = None
    port = None
    initial_reconnect_delay = None

    @pytest.fixture(autouse=True)
    def setUp(self, unused_tcp_port_factory):
        self.host = '127.0.0.1'
        self.port = unused_tcp_port_factory()
        self.initial_reconnect_delay = 2

    def test_that__handle_connection_should_send_error_frame_if_frame_is_invalid(self, unused_tcp_port_factory):
        # Prepare message with wrong signature
        middleman_message = GolemMessageFrame(Ping(), 1)
        raw_message = append_frame_separator(
            escape_encode_raw_message(
                middleman_message.serialize(
                    private_key=CONCENT_PRIVATE_KEY,
                )
            )
        )
        first_byte = 2 if raw_message[0] == 0 else raw_message[0]
        malformed_raw_message = bytes(bytearray([first_byte - 1])) + raw_message[1:]

        def mocked_generator(connection):  # pylint: disable=unused-argument
            yield malformed_raw_message
            raise SigningServiceValidationError()

        with mock.patch('signing_service.signing_service.SigningService.run'):
            with mock.patch(
                'signing_service.signing_service.unescape_stream',
                side_effect=mocked_generator,
            ):
                with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as signing_service_socket:
                    signing_service_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as client_socket:
                        client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                        signing_service = SigningService(
                            self.host,
                            self.port,
                            self.initial_reconnect_delay,
                            CONCENT_PUBLIC_KEY,
                            SIGNING_SERVICE_PRIVATE_KEY,
                        )

                        # For test purposes we reverse roles, so signing service works as server.
                        siging_service_port = unused_tcp_port_factory()
                        signing_service_socket.bind(('127.0.0.1', siging_service_port))
                        signing_service_socket.listen(1)
                        client_socket.connect(('127.0.0.1', siging_service_port))
                        (connection, _address) = signing_service_socket.accept()

                        with pytest.raises(SigningServiceValidationError):
                            signing_service._handle_connection(connection)

                        raw_message_received = next(unescape_stream(connection=client_socket))

        deserialized_message = AbstractFrame.deserialize(
            raw_message=raw_message_received,
            public_key=SIGNING_SERVICE_PUBLIC_KEY,
        )

        assertpy.assert_that(deserialized_message.payload).is_instance_of(tuple)
        assertpy.assert_that(deserialized_message.payload).is_length(2)
        assertpy.assert_that(deserialized_message.payload[0]).is_equal_to(ErrorCode.InvalidFrameSignature)
        assertpy.assert_that(deserialized_message.request_id).is_equal_to(REQUEST_ID_FOR_RESPONSE_FOR_INVALID_FRAME)


class TestSigningServiceIncreaseDelay:

    signing_service = None

    @pytest.fixture(autouse=True)
    def setUp(self, unused_tcp_port_factory):
        self.signing_service = SigningService(
            '127.0.0.1',
            unused_tcp_port_factory(),
            2,
            CONCENT_PUBLIC_KEY,
            SIGNING_SERVICE_PRIVATE_KEY,
        )

    def test_that_initial_reconnect_delay_should_be_set_to_passed_value(self):
        assertpy.assert_that(self.signing_service.current_reconnect_delay).is_equal_to(None)
        assertpy.assert_that(self.signing_service.initial_reconnect_delay).is_equal_to(2)

    def test_that_current_reconnect_delay_should_be_set_to_reconnect_delay_after_first_call_to__increase_delay(self):
        self.signing_service._increase_delay()
        assertpy.assert_that(self.signing_service.current_reconnect_delay).is_equal_to(2)

    def test_that_current_reconnect_delay_should_be_doubled_after_next_call_to__increase_delay(self):
        self.signing_service._increase_delay()
        self.signing_service._increase_delay()
        assertpy.assert_that(self.signing_service.current_reconnect_delay).is_equal_to(2 * 2)

    def test_that_current_reconnect_delay_should_be_set_to_allowed_maximum_after_it_extends_it(self):
        self.signing_service.current_reconnect_delay = SIGNING_SERVICE_MAXIMUM_RECONNECT_TIME - 1
        self.signing_service._increase_delay()
        assertpy.assert_that(self.signing_service.current_reconnect_delay).is_equal_to(SIGNING_SERVICE_MAXIMUM_RECONNECT_TIME)


class SigningServiceParseArgumentsTestCase(TestCase):

    def setUp(self):
        # ArgumentParser takes values directly from sys.argv, but the test runner has its own arguments,
        # so they have to be replaced.
        sys.argv = sys.argv[:1]
        self.concent_public_key_encoded = b64encode(CONCENT_PUBLIC_KEY).decode()
        self.signing_service_private_key_encoded = b64encode(SIGNING_SERVICE_PRIVATE_KEY).decode()
        self.sentry_dsn = 'http://test.sentry@dsn.com'
        self.ethereum_private_key = b'test_ethereum_private_key'

    def test_that_argument_parser_should_parse_correct_input(self):
        sys.argv += [
            '127.0.0.1',
            self.concent_public_key_encoded,
            '--initial_reconnect_delay', '2',
            '--concent-cluster-port', '8000',
            '--sentry-dsn', self.sentry_dsn,
            '--ethereum-private-key', b64encode(self.ethereum_private_key).decode('ascii'),
            '--signing-service-private-key', self.signing_service_private_key_encoded,
        ]

        args = _parse_arguments()

        self.assertEqual(args.concent_cluster_host, '127.0.0.1')
        self.assertEqual(args.concent_cluster_port, 8000)
        self.assertEqual(args.initial_reconnect_delay, 2)
        self.assertEqual(args.concent_public_key, CONCENT_PUBLIC_KEY)
        self.assertEqual(args.sentry_dsn, self.sentry_dsn)
        self.assertEqual(args.ethereum_private_key, self.ethereum_private_key)
        self.assertEqual(args.signing_service_private_key, SIGNING_SERVICE_PRIVATE_KEY)

    def test_that_argument_parser_should_parse_correct_input_and_use_default_values(self):
        sys.argv += [
            '127.0.0.1',
            self.concent_public_key_encoded,
            '--ethereum-private-key', b64encode(self.ethereum_private_key).decode('ascii'),
            '--signing-service-private-key', self.signing_service_private_key_encoded,
        ]

        args = _parse_arguments()

        self.assertEqual(args.concent_cluster_port, SIGNING_SERVICE_DEFAULT_PORT)
        self.assertEqual(args.initial_reconnect_delay, SIGNING_SERVICE_DEFAULT_INITIAL_RECONNECT_DELAY)

    def test_that_argument_parser_should_fail_if_port_cannot_be_casted_to_int(self):
        sys.argv += [
            '127.0.0.1',
            self.concent_public_key_encoded,
            '--concent-cluster-port', 'abc',
            '--ethereum-private-key', b64encode(self.ethereum_private_key).decode('ascii'),
            '--signing-service-private-key', self.signing_service_private_key_encoded,
        ]

        with self.assertRaises(SystemExit):
            _parse_arguments()

    def test_that_argument_parser_should_parse_correct_secrets_from_env_variables(self):
        sys.argv += [
            '127.0.0.1',
            self.concent_public_key_encoded,
            '--sentry-dsn-from-env',
            '--ethereum-private-key-from-env',
            '--signing-service-private-key-from-env',
        ]

        with mock.patch.dict(os.environ, {
            'SENTRY_DSN': self.sentry_dsn,
            'ETHEREUM_PRIVATE_KEY': b64encode(self.ethereum_private_key).decode('ascii'),
            'SIGNING_SERVICE_PRIVATE_KEY': self.signing_service_private_key_encoded,
        }):
            args = _parse_arguments()

        self.assertEqual(args.sentry_dsn, self.sentry_dsn)
        self.assertEqual(args.ethereum_private_key, self.ethereum_private_key)
        self.assertEqual(args.signing_service_private_key, SIGNING_SERVICE_PRIVATE_KEY)

    def test_that_argument_parses_should_fail_if_file_with_secrets_is_missing(self):
        sys.argv += ['127.0.0.1', self.concent_public_key_encoded, '--sentry-dsn-path', '/not_existing_path/file.txt']
        with self.assertRaises(FileNotFoundError):
            _parse_arguments()

    def test_that_argument_parser_should_parse_parameters_if_passed_files_exist(self):
        sentry_tmp_file = os.path.join(tempfile.gettempdir(), "sentry_tmp_file.txt")
        ethereum_private_key_tmp_file = os.path.join(tempfile.gettempdir(), "ethereum_private_key_tmp_file.txt")
        signing_service_private_key_tmp_file = os.path.join(tempfile.gettempdir(), "signing_service_private_key_tmp_file.txt")

        sys.argv += [
            '127.0.0.1',
            self.concent_public_key_encoded,
            '--ethereum-private-key-path', ethereum_private_key_tmp_file,
            '--sentry-dsn-path', sentry_tmp_file,
            '--signing-service-private-key-path', signing_service_private_key_tmp_file,
        ]

        with open(sentry_tmp_file, "w") as file:
            file.write(self.sentry_dsn)

        with open(ethereum_private_key_tmp_file, "w") as file:
            file.write(b64encode(self.ethereum_private_key).decode('ascii'))

        with open(signing_service_private_key_tmp_file, "w") as file:
            file.write(self.signing_service_private_key_encoded)

        args =_parse_arguments()

        self.assertEqual(args.sentry_dsn, self.sentry_dsn)
        self.assertEqual(args.ethereum_private_key, self.ethereum_private_key)
        self.assertEqual(args.signing_service_private_key, SIGNING_SERVICE_PRIVATE_KEY)
        os.remove(sentry_tmp_file)
        os.remove(ethereum_private_key_tmp_file)
        os.remove(signing_service_private_key_tmp_file)


class SigningServiceValidateArgumentsTestCase(TestCase):

    def setUp(self):
        super().setUp()
        self.host = '127.0.0.1'
        self.port = 8000
        self.initial_reconnect_delay = 2

        self.signing_service = SigningService(
            self.host,
            self.port,
            self.initial_reconnect_delay,
            CONCENT_PUBLIC_KEY,
            SIGNING_SERVICE_PRIVATE_KEY,
        )

    def test_that_signing_service__validate_arguments_should_raise_exception_on_port_number_below_or_above_range(self):
        for wrong_port in [0, 65535 + 1]:
            self.signing_service.port = wrong_port

            with self.assertRaises(SigningServiceValidationError):
                self.signing_service._validate_arguments()

    def test_that_signing_service__validate_arguments_should_raise_exception_on_initial_reconnect_delay_lower_than_zero(self):
        self.signing_service.initial_reconnect_delay = -1

        with self.assertRaises(SigningServiceValidationError):
            self.signing_service._validate_arguments()

    def test_that_signing_service__validate_arguments_should_raise_exception_on_wrong_length_of_concent_public_key(self):
        self.signing_service.concent_public_key = CONCENT_PUBLIC_KEY[:-1]

        with self.assertRaises(SigningServiceValidationError):
            self.signing_service._validate_arguments()


class SigningServiceIsValidPulicKeyTestCase(TestCase):

    def test_that_is_valid_public_key_should_return_true_for_correct_public_key_length(self):
        public_key = b'x' * 64

        self.assertTrue(is_valid_public_key(public_key))

    def test_that_is_valid_public_key_should_return_true_for_too_short_public_key_length(self):
        public_key = b'x' * 63

        self.assertFalse(is_valid_public_key(public_key))

    def test_that_is_valid_public_key_should_return_true_for_too_long_public_key_length(self):
        public_key = b'x' * 65

        self.assertFalse(is_valid_public_key(public_key))
