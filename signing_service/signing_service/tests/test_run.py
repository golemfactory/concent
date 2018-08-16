import socket

from golem_messages.cryptography import ECCx
import assertpy
import mock
import pytest

from signing_service.constants import SIGNING_SERVICE_RECOVERABLE_ERRORS
from signing_service.signing_service import SigningService


TEST_ETHEREUM_PRIVATE_KEY = '3a1076bf45ab87712ad64ccb3b10217737f7faacbf2872e88fdd9a537d8fe266'

concent_ecc_keys = ECCx(None)
(CONCENT_PRIVATE_KEY, CONCENT_PUBLIC_KEY) = concent_ecc_keys.raw_privkey, concent_ecc_keys.raw_pubkey

signing_service_ecc_keys = ECCx(None)
(SIGNING_SERVICE_PRIVATE_KEY, SIGNING_SERVICE_PUBLIC_KEY) = signing_service_ecc_keys.raw_privkey, signing_service_ecc_keys.raw_pubkey


class TestSigningServiceRun:

    host = None
    port = None
    initial_reconnect_delay = None
    parameters = None

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
        ]

    def test_that_signing_service_should_be_instantiated_correctly_with_all_parameters(self):
        signing_service = SigningService(*self.parameters)

        assertpy.assert_that(signing_service).is_instance_of(SigningService)
        assertpy.assert_that(signing_service.host).is_equal_to(self.host)
        assertpy.assert_that(signing_service.port).is_equal_to(self.port)
        assertpy.assert_that(signing_service.initial_reconnect_delay).is_equal_to(self.initial_reconnect_delay)

    def test_that_signing_service_should_run_full_loop_when_instantiated_with_all_parameters(self):
        with mock.patch('socket.socket.connect') as mock_socket_connect:
            with mock.patch('signing_service.signing_service.SigningService._handle_connection') as mock__handle_connection:
                with mock.patch('socket.socket.close') as mock_socket_close:
                    with mock.patch('signing_service.signing_service.SigningService._was_sigterm_caught', side_effect=[False, True]):
                        signing_service = SigningService(*self.parameters)
                        signing_service.run()

        mock_socket_connect.assert_called_once_with(('127.0.0.1', self.port))
        mock_socket_close.assert_called_once()
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
        assert socket.errno.ECONNREFUSED in SIGNING_SERVICE_RECOVERABLE_ERRORS

        with mock.patch('socket.socket.connect', side_effect=socket.error(socket.errno.ECONNREFUSED)) as mock_socket_connect:
            with mock.patch('signing_service.signing_service.SigningService._was_sigterm_caught', side_effect=[False, False, True]):
                signing_service = SigningService(*self.parameters)
                signing_service.run()

        assertpy.assert_that(mock_socket_connect.call_count).is_equal_to(2)

    def test_that_signing_service_should_reraise_different_socket_erros(self):
        assert socket.errno.EBUSY not in SIGNING_SERVICE_RECOVERABLE_ERRORS

        with mock.patch('socket.socket.connect', side_effect=socket.error(socket.errno.EBUSY)) as mock_socket_connect:
            with mock.patch('socket.socket.close') as mock_socket_close:
                signing_service = SigningService(*self.parameters)
                with pytest.raises(socket.error):
                    signing_service.run()

        mock_socket_connect.assert_called_once_with(('127.0.0.1', self.port))
        mock_socket_close.assert_called_once()
