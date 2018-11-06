from contextlib import closing
import os
import socket

from golem_messages.cryptography import ECCx
from golem_messages.cryptography import ecdsa_verify
import assertpy
import mock
import pytest

from middleman_protocol.message import AbstractFrame
from middleman_protocol.message import AuthenticationChallengeFrame
from middleman_protocol.message import AuthenticationResponseFrame
from middleman_protocol.stream import unescape_stream

from signing_service.constants import SIGNING_SERVICE_DEFAULT_RECONNECT_ATTEMPTS
from signing_service.signing_service import SigningService
from signing_service.utils import ConsoleNotifier
from .utils import SigningServiceIntegrationTestCase


TEST_ETHEREUM_PRIVATE_KEY = '3a1076bf45ab87712ad64ccb3b10217737f7faacbf2872e88fdd9a537d8fe266'

concent_ecc_keys = ECCx(None)
(CONCENT_PRIVATE_KEY, CONCENT_PUBLIC_KEY) = concent_ecc_keys.raw_privkey, concent_ecc_keys.raw_pubkey

signing_service_ecc_keys = ECCx(None)
(SIGNING_SERVICE_PRIVATE_KEY, SIGNING_SERVICE_PUBLIC_KEY) = signing_service_ecc_keys.raw_privkey, signing_service_ecc_keys.raw_pubkey


class TestSigningServiceAuthenticate(SigningServiceIntegrationTestCase):

    @pytest.fixture(autouse=True)
    def setUp(self, unused_tcp_port_factory):
        self.host = '127.0.0.1'
        self.port = unused_tcp_port_factory()
        self.initial_reconnect_delay = 2
        self.signing_service_port = unused_tcp_port_factory()
        self.authentication_challenge = bytes(os.urandom(1000))

    def test_that_authenticate_should_send_authentication_response_if_authentication_challenge_is_correct(self):
        middleman_message = AuthenticationChallengeFrame(
            payload=self.authentication_challenge,
            request_id=99,
        )
        raw_message = middleman_message.serialize(private_key=CONCENT_PRIVATE_KEY)

        raw_message_received = self._prepare_and_execute_handle_connection(
            raw_message,
        )

        deserialized_message = AbstractFrame.deserialize(
            raw_message=raw_message_received,
            public_key=SIGNING_SERVICE_PUBLIC_KEY,
        )

        assertpy.assert_that(deserialized_message).is_instance_of(AuthenticationResponseFrame)
        assertpy.assert_that(deserialized_message.payload).is_instance_of(bytes)
        assertpy.assert_that(
            ecdsa_verify(
                SIGNING_SERVICE_PUBLIC_KEY,
                deserialized_message.payload,
                self.authentication_challenge,
            )
        ).is_true()

    def test_that_authenticate_should_raise_socket_error_if_received_frame_is_not_authentication_challenge(self):
        middleman_message = AuthenticationResponseFrame(
            payload=self.authentication_challenge,
            request_id=99,
        )
        raw_message = middleman_message.serialize(private_key=CONCENT_PRIVATE_KEY)

        with pytest.raises(socket.error):
            self._prepare_and_execute_handle_connection(
                raw_message,
            )

    def test_that_authenticate_should_raise_socket_error_if_received_frame_is_invalid(self):
        middleman_message = AuthenticationResponseFrame(
            payload=self.authentication_challenge,
            request_id=99,
        )
        raw_message = middleman_message.serialize(private_key=CONCENT_PRIVATE_KEY)
        malformed_raw_message = raw_message[:-1]

        with pytest.raises(socket.error):
            self._prepare_and_execute_handle_connection(
                malformed_raw_message,
            )

    def test_that_authenticate_should_raise_socket_error_if_receiving_frame_is_timeouted(self):
        with mock.patch('signing_service.signing_service.send_over_stream', side_effect=socket.timeout()):
            with pytest.raises(socket.error):
                self._prepare_and_execute_handle_connection(
                    b'',
                )

    def test_that_authenticate_should_raise_socket_error_if_socket_error_is_raised_after_sending_authentication_response(self):
        middleman_message = AuthenticationChallengeFrame(
            payload=self.authentication_challenge,
            request_id=99,
        )
        raw_message = middleman_message.serialize(private_key=CONCENT_PRIVATE_KEY)

        with mock.patch('signing_service.signing_service.send_over_stream', side_effect=socket.error()):
            with pytest.raises(socket.error):
                self._prepare_and_execute_handle_connection(
                    raw_message,
                )

    def _prepare_and_execute_handle_connection(self, raw_message):
        def mocked_generator():
            yield raw_message

        with mock.patch('signing_service.signing_service.SigningService.run'):
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
                        TEST_ETHEREUM_PRIVATE_KEY,
                        SIGNING_SERVICE_DEFAULT_RECONNECT_ATTEMPTS,
                        ConsoleNotifier(),
                    )

                    # For test purposes we reverse roles, so signing service works as server.
                    signing_service_socket.bind(('127.0.0.1', self.signing_service_port))
                    signing_service_socket.listen(1)
                    client_socket.connect(('127.0.0.1', self.signing_service_port))
                    (connection, _address) = signing_service_socket.accept()

                    signing_service._authenticate(mocked_generator(), connection)
                    raw_message_received = next(unescape_stream(connection=client_socket))

        return raw_message_received
