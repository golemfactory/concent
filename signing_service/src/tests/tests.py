from unittest import TestCase
import socket
import sys

import mock

from ..constants import SIGNING_SERVICE_DEFAULT_PORT
from ..constants import SIGNING_SERVICE_RECOVERABLE_ERRORS
from ..constants import SIGNING_SERVICE_MAXIMUM_RECONNECT_TIME
from ..signing_service import _parse_arguments
from ..signing_service import SigningService


class SigningServiceMainTestCase(TestCase):

    def setUp(self):
        self.host = '127.0.0.1'
        self.port = 8000
        self.initial_reconnect_delay = 2

    def test_that_signing_service_should_be_instantiated_correctly_with_all_parameters(self):
        signing_service = SigningService(self.host, self.port, self.initial_reconnect_delay)

        self.assertIsInstance(signing_service, SigningService)
        self.assertEqual(signing_service.host, self.host)
        self.assertEqual(signing_service.port, self.port)
        self.assertEqual(signing_service.initial_reconnect_delay, self.initial_reconnect_delay)

    def test_that_signing_service_should_run_full_loop_when_instantiated_with_all_parameters(self):
        with mock.patch('socket.socket.connect') as mock_socket_connect:
            with mock.patch('src.signing_service.SigningService._handle_connection') as mock__handle_connection:
                with mock.patch('socket.socket.close') as mock_socket_close:
                    with mock.patch('src.signing_service.SigningService._was_sigterm_caught', side_effect=[False, True]):
                        signing_service = SigningService(self.host, self.port, self.initial_reconnect_delay)
                        signing_service.run()

        mock_socket_connect.assert_called_once_with(('127.0.0.1', 8000))
        mock_socket_close.assert_called_once()
        mock__handle_connection.assert_called_once()

    def test_that_signing_service_should_exit_gracefully_on_keyboard_interrupt(self):
        with mock.patch('socket.socket.connect', side_effect=KeyboardInterrupt()) as mock_socket_connect:
            with mock.patch('socket.socket.close') as mock_socket_close:
                signing_service = SigningService(self.host, self.port, self.initial_reconnect_delay)
                signing_service.run()

        mock_socket_connect.assert_called_once_with(('127.0.0.1', 8000))
        mock_socket_close.assert_called_once()

    def test_that_signing_service_should_reraise_unrecognized_exception(self):
        with mock.patch('socket.socket.connect', side_effect=Exception()) as mock_socket_connect:
            with mock.patch('socket.socket.close') as mock_socket_close:
                signing_service = SigningService(self.host, self.port, self.initial_reconnect_delay)
                with self.assertRaises(Exception):
                    signing_service.run()

        mock_socket_connect.assert_called_once_with(('127.0.0.1', 8000))
        mock_socket_close.assert_called_once()

    def test_that_signing_service_should_reconnect_when_expected_socket_error_was_caught(self):
        assert socket.errno.ECONNREFUSED in SIGNING_SERVICE_RECOVERABLE_ERRORS

        with mock.patch('socket.socket.connect', side_effect=socket.error(socket.errno.ECONNREFUSED)) as mock_socket_connect:
            with mock.patch('src.signing_service.SigningService._was_sigterm_caught', side_effect=[False, False, True]):
                signing_service = SigningService(self.host, self.port, self.initial_reconnect_delay)
                signing_service.run()

        self.assertEqual(mock_socket_connect.call_count, 2)

    def test_that_signing_service_should_reraise_different_socket_erros(self):
        assert socket.errno.EBUSY not in SIGNING_SERVICE_RECOVERABLE_ERRORS

        with mock.patch('socket.socket.connect', side_effect=socket.error(socket.errno.EBUSY)) as mock_socket_connect:
            with mock.patch('socket.socket.close') as mock_socket_close:
                signing_service = SigningService(self.host, self.port, self.initial_reconnect_delay)
                with self.assertRaises(socket.error):
                    signing_service.run()

        mock_socket_connect.assert_called_once_with(('127.0.0.1', 8000))
        mock_socket_close.assert_called_once()


class SigningServiceIncreaseDelayTestCase(TestCase):

    def setUp(self):
        self.signing_service = SigningService('127.0.0.1', 8000, 2)

    def test_that_initial_reconnect_delay_should_be_set_to_passed_value(self):
        self.assertEqual(self.signing_service.current_reconnect_delay, None)
        self.assertEqual(self.signing_service.initial_reconnect_delay, 2)

    def test_that_current_reconnect_delay_should_be_set_to_reconnect_delay_after_first_call_to__increase_delay(self):
        self.signing_service._increase_delay()
        self.assertEqual(self.signing_service.current_reconnect_delay, 2)

    def test_that_current_reconnect_delay_should_be_doubled_after_next_call_to__increase_delay(self):
        self.signing_service._increase_delay()
        self.signing_service._increase_delay()
        self.assertEqual(self.signing_service.current_reconnect_delay, 2 * 2)

    def test_that_current_reconnect_delay_should_be_set_to_allowed_maximum_after_it_extends_it(self):
        self.signing_service.current_reconnect_delay = SIGNING_SERVICE_MAXIMUM_RECONNECT_TIME - 1
        self.signing_service._increase_delay()
        self.assertEqual(self.signing_service.current_reconnect_delay, SIGNING_SERVICE_MAXIMUM_RECONNECT_TIME)


class SigningServiceParseArgumentsTestCase(TestCase):

    def setUp(self):
        super().setUp()
        # ArgumentParser takes values directly from sys.argv, but the test runner has its own arguments,
        # so they have to be replaced.
        sys.argv = sys.argv[:1]

    def test_that_argument_parser_should_parse_correct_input(self):
        sys.argv += ['127.0.0.1', '1', '--concent-cluster-port', '8000']

        args = _parse_arguments()

        self.assertEqual(args.concent_cluster_host, '127.0.0.1')
        self.assertEqual(args.concent_cluster_port, 8000)

    def test_that_argument_parser_should_parse_correct_input_and_use_default_port(self):
        sys.argv += ['127.0.0.1', '1']

        args = _parse_arguments()

        self.assertEqual(args.concent_cluster_host, '127.0.0.1')
        self.assertEqual(args.concent_cluster_port, SIGNING_SERVICE_DEFAULT_PORT)

    def test_that_argument_parser_should_fail_if_port_cannot_be_casted_to_int(self):
        sys.argv += ['127.0.0.1', '1', '--concent-cluster-port', 'abc']

        with self.assertRaises(SystemExit):
            _parse_arguments()

    def test_that_argument_parser_should_fail_if_host_is_missing(self):
        with self.assertRaises(SystemExit):
            _parse_arguments()
