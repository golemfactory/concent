import socket

from golem_messages.cryptography import ECCx
import assertpy
import mock
import pytest

from signing_service.constants import SIGNING_SERVICE_DEFAULT_RECONNECT_ATTEMPTS
from signing_service.signing_service import SigningService
from signing_service.utils import ConsoleNotifier

TEST_ETHEREUM_PRIVATE_KEY = '47a286230c8b3a1c3fa0282f6a65d1d57ffe5147dafaef7cd110d24ed51b462e'

concent_ecc_keys = ECCx(None)
(CONCENT_PRIVATE_KEY, CONCENT_PUBLIC_KEY) = concent_ecc_keys.raw_privkey, concent_ecc_keys.raw_pubkey

signing_service_ecc_keys = ECCx(None)
(SIGNING_SERVICE_PRIVATE_KEY, SIGNING_SERVICE_PUBLIC_KEY) = signing_service_ecc_keys.raw_privkey, signing_service_ecc_keys.raw_pubkey


class TestSigningServiceRun:

    @pytest.fixture(autouse=True)
    def setUp(self, unused_tcp_port_factory):
        self.host = '127.0.0.1'
        self.port = unused_tcp_port_factory()
        self.initial_reconnect_delay = 2
        self.parameters = [
            self.host,
            self.port,
            self.initial_reconnect_delay,
            CONCENT_PUBLIC_KEY,
            SIGNING_SERVICE_PRIVATE_KEY,
            TEST_ETHEREUM_PRIVATE_KEY,
            SIGNING_SERVICE_DEFAULT_RECONNECT_ATTEMPTS,
            ConsoleNotifier(),
        ]

    def test_that_signing_service_should_be_instantiated_correctly_with_all_parameters(self):
        signing_service = SigningService(*self.parameters)

        assertpy.assert_that(signing_service).is_instance_of(SigningService)
        assertpy.assert_that(signing_service.host).is_equal_to(self.host)
        assertpy.assert_that(signing_service.port).is_equal_to(self.port)
        assertpy.assert_that(signing_service.initial_reconnect_delay).is_equal_to(self.initial_reconnect_delay)

    def test_that_signing_service_should_run_full_loop_when_instantiated_with_all_parameters(self):
        with mock.patch('socket.socket.connect') as mock_socket_connect:
            with mock.patch('signing_service.signing_service.SigningService._authenticate') as mock___authenticate:
                with mock.patch('signing_service.signing_service.SigningService._get_signing_service_daily_transaction_sum_so_far') as mock_daily_transaction_sum:
                    with mock.patch('signing_service.signing_service.SigningService._handle_connection') as mock__handle_connection:
                        with mock.patch('socket.socket.close') as mock_socket_close:
                            with mock.patch('signing_service.signing_service.SigningService._was_sigterm_caught', side_effect=[False, True]):
                                signing_service = SigningService(*self.parameters)
                                signing_service.run()

        mock_socket_connect.assert_called_once_with(('127.0.0.1', self.port))
        mock_socket_close.assert_called_once()
        mock___authenticate.assert_called_once()
        mock_daily_transaction_sum.assert_called_once()
        mock__handle_connection.assert_called_once()

    def test_that_signing_service_should_exit_gracefully_on_keyboard_interrupt(self):
        with mock.patch('socket.socket.connect', side_effect=KeyboardInterrupt()) as mock_socket_connect:
            with mock.patch('socket.socket.close') as mock_socket_close:
                signing_service = SigningService(*self.parameters)
                signing_service.run()

        mock_socket_connect.assert_called_once_with(('127.0.0.1', self.port))
        mock_socket_close.assert_called_once()

    def test_that_signing_service_should_reraise_unrecognized_exception(self):
        with mock.patch('socket.socket.connect', side_effect=Exception()) as mock_socket_connect:
            with mock.patch('socket.socket.close') as mock_socket_close:
                signing_service = SigningService(*self.parameters)
                with pytest.raises(Exception):
                    signing_service.run()

        mock_socket_connect.assert_called_once_with(('127.0.0.1', self.port))
        mock_socket_close.assert_called_once()

    def test_that_signing_service_should_reconnect_when_expected_socket_error_was_caught(self):
        with mock.patch('socket.socket.connect', side_effect=socket.error()) as mock_socket_connect:
            with mock.patch('signing_service.signing_service.SigningService._was_sigterm_caught', side_effect=[False, False, True]):
                signing_service = SigningService(*self.parameters)
                signing_service.run()

        assertpy.assert_that(mock_socket_connect.call_count).is_equal_to(2)

    def test_that_signing_service_will_reconnect_on_socket_errors_and_exit_gracefully_when_exceeds_maximum_number_of_reconnection_attempts(self):
        with mock.patch('socket.socket.connect', side_effect=socket.error()) as mock_socket_connect:
            with mock.patch('socket.socket.close') as mock_socket_close:
                with mock.patch('signing_service.signing_service.sleep'):
                    signing_service = SigningService(*self.parameters)
                    with mock.patch('signing_service.signing_service.logger.error') as mock_logger_error:
                        signing_service.run()
        assertpy.assert_that(mock_socket_connect.call_count).is_equal_to(SIGNING_SERVICE_DEFAULT_RECONNECT_ATTEMPTS + 1)
        assertpy.assert_that(mock_socket_close.call_count).is_equal_to(SIGNING_SERVICE_DEFAULT_RECONNECT_ATTEMPTS + 1)
        assertpy.assert_that(
            mock_logger_error.call_args_list[mock_logger_error.call_count - 1],
            ['Maximum number of reconnection exceeded.'],
        )

    def test_that_signing_service_will_reconnect_after_authentication_fails(self):
        with mock.patch('socket.socket.connect') as mock_socket_connect:
            with mock.patch('socket.socket.close') as mock_socket_close:
                with mock.patch('signing_service.signing_service.SigningService._authenticate', side_effect=socket.error()) as mock___authenticate:
                    with mock.patch('signing_service.signing_service.sleep'):
                        signing_service = SigningService(*self.parameters)
                        signing_service.run()
        assertpy.assert_that(mock_socket_connect.call_count).is_equal_to(SIGNING_SERVICE_DEFAULT_RECONNECT_ATTEMPTS + 1)
        assertpy.assert_that(mock_socket_close.call_count).is_equal_to(SIGNING_SERVICE_DEFAULT_RECONNECT_ATTEMPTS + 1)
        assertpy.assert_that(mock___authenticate.call_count).is_equal_to(SIGNING_SERVICE_DEFAULT_RECONNECT_ATTEMPTS + 1)
