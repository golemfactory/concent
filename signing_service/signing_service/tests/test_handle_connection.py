from contextlib import closing
import socket

from golem_messages.cryptography import ECCx
from golem_messages.cryptography import ecdsa_sign
from golem_messages.message import Ping
import assertpy
import mock
import pytest

from middleman_protocol.concent_golem_messages.message import SignedTransaction
from middleman_protocol.concent_golem_messages.message import TransactionRejected
from middleman_protocol.constants import ErrorCode
from middleman_protocol.constants import FRAME_PAYLOAD_STARTING_BYTE
from middleman_protocol.constants import FRAME_PAYLOAD_TYPE_LENGTH
from middleman_protocol.constants import FRAME_REQUEST_ID_BYTES_LENGTH
from middleman_protocol.constants import FRAME_SIGNATURE_BYTES_LENGTH
from middleman_protocol.constants import REQUEST_ID_FOR_RESPONSE_FOR_INVALID_FRAME
from middleman_protocol.message import AbstractFrame
from middleman_protocol.message import GolemMessageFrame
from middleman_protocol.message import HeartbeatFrame
from middleman_protocol.stream import unescape_stream

from signing_service.constants import MAXIMUM_DAILY_THRESHOLD
from signing_service.constants import SIGNING_SERVICE_DEFAULT_RECONNECT_ATTEMPTS
from signing_service.constants import WARNING_DAILY_THRESHOLD
from signing_service.exceptions import SigningServiceValidationError
from signing_service.signing_service import SigningService
from signing_service.utils import ConsoleNotifier
from .utils import SigningServiceIntegrationTestCase


TEST_ETHEREUM_PRIVATE_KEY = '47a286230c8b3a1c3fa0282f6a65d1d57ffe5147dafaef7cd110d24ed51b462e'

concent_ecc_keys = ECCx(None)
(CONCENT_PRIVATE_KEY, CONCENT_PUBLIC_KEY) = concent_ecc_keys.raw_privkey, concent_ecc_keys.raw_pubkey

signing_service_ecc_keys = ECCx(None)
(SIGNING_SERVICE_PRIVATE_KEY, SIGNING_SERVICE_PUBLIC_KEY) = signing_service_ecc_keys.raw_privkey, signing_service_ecc_keys.raw_pubkey


class TestSigningServiceHandleConnection(SigningServiceIntegrationTestCase):

    @pytest.fixture(autouse=True)
    def setUp(self, unused_tcp_port_factory):
        self.host = '127.0.0.1'
        self.port = unused_tcp_port_factory()
        self.initial_reconnect_delay = 2
        self.signing_service_port = unused_tcp_port_factory()

    def test_that__handle_connection_should_send_golem_message_signed_transaction_if_frame_is_correct(self):
        middleman_message = GolemMessageFrame(
            payload=self._get_deserialized_transaction_signing_request(),
            request_id=99,
        )
        middleman_message.payload.value = WARNING_DAILY_THRESHOLD
        raw_message = middleman_message.serialize(private_key=CONCENT_PRIVATE_KEY)

        def handle_connection_wrapper(signing_service, connection, receive_frame_generator):
            with mock.patch(
                'signing_service.signing_service.SigningService._get_signed_transaction',
                return_value=self._get_deserialized_signed_transaction(),
            ):
                with mock.patch(
                    'signing_service.signing_service.SigningService._add_payload_value_to_daily_transactions_sum'
                ):
                    signing_service._handle_connection(receive_frame_generator, connection)

        raw_message_received = self._prepare_and_execute_handle_connection(
            raw_message,
            handle_connection_wrapper,
        )

        deserialized_message = AbstractFrame.deserialize(
            raw_message=raw_message_received,
            public_key=SIGNING_SERVICE_PUBLIC_KEY,
        )

        assertpy.assert_that(deserialized_message.payload).is_instance_of(SignedTransaction)

    def test_that__handle_connection_should_send_golem_message_signed_transaction_if_warning_daily_threshold_exceeded(self):
        middleman_message = GolemMessageFrame(
            payload=self._get_deserialized_transaction_signing_request(),
            request_id=99,
        )
        middleman_message.payload.value = WARNING_DAILY_THRESHOLD + 1
        raw_message = middleman_message.serialize(private_key=CONCENT_PRIVATE_KEY)

        def handle_connection_wrapper(signing_service, connection, receive_frame_generator):
            with mock.patch(
                'signing_service.signing_service.SigningService._get_signed_transaction',
                return_value=self._get_deserialized_signed_transaction(),
            ):
                with mock.patch(
                    'signing_service.signing_service.SigningService._add_payload_value_to_daily_transactions_sum'
                ):
                    signing_service._handle_connection(receive_frame_generator, connection)

        raw_message_received = self._prepare_and_execute_handle_connection(
            raw_message,
            handle_connection_wrapper,
        )

        deserialized_message = AbstractFrame.deserialize(
            raw_message=raw_message_received,
            public_key=SIGNING_SERVICE_PUBLIC_KEY,
        )

        assertpy.assert_that(deserialized_message.payload).is_instance_of(SignedTransaction)

    def test_that__handle_connection_should_send_golem_message_reject_if_max_daily_threshold_exceeded(self):
        middleman_message = GolemMessageFrame(
            payload=self._get_deserialized_transaction_signing_request(),
            request_id=99,
        )
        middleman_message.payload.value = MAXIMUM_DAILY_THRESHOLD + 1
        raw_message = middleman_message.serialize(private_key=CONCENT_PRIVATE_KEY)

        def handle_connection_wrapper(signing_service, connection, receive_frame_generator):
            with mock.patch(
                'signing_service.signing_service.SigningService._get_signed_transaction',
                return_value=self._get_deserialized_signed_transaction(),
            ):
                signing_service._handle_connection(receive_frame_generator, connection)

        raw_message_received = self._prepare_and_execute_handle_connection(
            raw_message,
            handle_connection_wrapper,
        )

        deserialized_message = AbstractFrame.deserialize(
            raw_message=raw_message_received,
            public_key=SIGNING_SERVICE_PUBLIC_KEY,
        )

        assertpy.assert_that(deserialized_message.payload).is_instance_of(TransactionRejected)

    def test_that__handle_connection_should_send_error_frame_if_frame_signature_is_wrong(self):
        # Prepare message with wrong signature.
        middleman_message = GolemMessageFrame(
            payload=self._get_deserialized_transaction_signing_request(),
            request_id=99,
        )
        raw_message = middleman_message.serialize(private_key=CONCENT_PRIVATE_KEY)
        first_byte = 2 if raw_message[0] == 0 else raw_message[0]
        malformed_raw_message = bytes(bytearray([first_byte - 1])) + raw_message[1:]

        raw_message_received = self._prepare_and_execute_handle_connection(malformed_raw_message)

        deserialized_message = AbstractFrame.deserialize(
            raw_message=raw_message_received,
            public_key=SIGNING_SERVICE_PUBLIC_KEY,
        )

        assertpy.assert_that(deserialized_message.payload).is_instance_of(tuple)
        assertpy.assert_that(deserialized_message.payload).is_length(2)
        assertpy.assert_that(deserialized_message.payload[0]).is_equal_to(ErrorCode.InvalidFrameSignature)
        assertpy.assert_that(deserialized_message.request_id).is_equal_to(REQUEST_ID_FOR_RESPONSE_FOR_INVALID_FRAME)

    def test_that__handle_connection_should_send_error_frame_if_payload_type_is_invalid(self):
        # Prepare frame with malformed payload_type.
        middleman_message = GolemMessageFrame(
            payload=self._get_deserialized_transaction_signing_request(),
            request_id=99,
        )
        raw_message = middleman_message.serialize(private_key=CONCENT_PRIVATE_KEY)

        payload_type_position = FRAME_SIGNATURE_BYTES_LENGTH + FRAME_REQUEST_ID_BYTES_LENGTH
        invalid_payload_type = 100

        # Replace bytes with payload length.
        malformed_raw_message = (
            raw_message[:payload_type_position] +
            bytes(bytearray([invalid_payload_type])) +
            raw_message[payload_type_position + FRAME_PAYLOAD_TYPE_LENGTH:]
        )

        # Replace message signature
        new_signature = ecdsa_sign(CONCENT_PRIVATE_KEY, malformed_raw_message[FRAME_SIGNATURE_BYTES_LENGTH:])
        malformed_raw_message_with_new_signature = new_signature + malformed_raw_message[FRAME_SIGNATURE_BYTES_LENGTH:]

        raw_message_received = self._prepare_and_execute_handle_connection(malformed_raw_message_with_new_signature)

        deserialized_message = AbstractFrame.deserialize(
            raw_message=raw_message_received,
            public_key=SIGNING_SERVICE_PUBLIC_KEY,
        )

        assertpy.assert_that(deserialized_message.payload).is_instance_of(tuple)
        assertpy.assert_that(deserialized_message.payload).is_length(2)
        assertpy.assert_that(deserialized_message.payload[0]).is_equal_to(ErrorCode.InvalidFrame)
        assertpy.assert_that(deserialized_message.request_id).is_equal_to(REQUEST_ID_FOR_RESPONSE_FOR_INVALID_FRAME)

    def test_that__handle_connection_should_send_error_frame_if_payload_is_invalid(self):
        # Prepare frame payload which is not Golem message.
        middleman_message = GolemMessageFrame(
            payload=Ping(),
            request_id=99,
        )
        raw_message = middleman_message.serialize(private_key=CONCENT_PRIVATE_KEY)
        malformed_raw_message = (
            raw_message[:FRAME_PAYLOAD_STARTING_BYTE] +
            AbstractFrame.get_frame_format().signed_part_of_the_frame.payload.build(b'\x00' * 100)
        )

        # Replace message signature
        new_signature = ecdsa_sign(CONCENT_PRIVATE_KEY, malformed_raw_message[FRAME_SIGNATURE_BYTES_LENGTH:])
        malformed_raw_message_with_new_signature = new_signature + malformed_raw_message[FRAME_SIGNATURE_BYTES_LENGTH:]

        raw_message_received = self._prepare_and_execute_handle_connection(malformed_raw_message_with_new_signature)

        deserialized_message = AbstractFrame.deserialize(
            raw_message=raw_message_received,
            public_key=SIGNING_SERVICE_PUBLIC_KEY,
        )

        assertpy.assert_that(deserialized_message.payload).is_instance_of(tuple)
        assertpy.assert_that(deserialized_message.payload).is_length(2)
        assertpy.assert_that(deserialized_message.payload[0]).is_equal_to(ErrorCode.InvalidPayload)
        assertpy.assert_that(deserialized_message.request_id).is_equal_to(REQUEST_ID_FOR_RESPONSE_FOR_INVALID_FRAME)

    def test_that__handle_connection_should_send_error_frame_if_payload_golem_message_type_cannot_be_deserialized(self):
        # Prepare frame payload which is Golem message that cannot be deserialized.
        middleman_message = GolemMessageFrame(
            payload=self._get_deserialized_transaction_signing_request(
                nonce='not_int_nonce_which_will_fail_on_deserialization_causing_message_error'
            ),
            request_id=99,
        )
        raw_message = middleman_message.serialize(private_key=CONCENT_PRIVATE_KEY)

        raw_message_received = self._prepare_and_execute_handle_connection(raw_message)

        deserialized_message = AbstractFrame.deserialize(
            raw_message=raw_message_received,
            public_key=SIGNING_SERVICE_PUBLIC_KEY,
        )

        assertpy.assert_that(deserialized_message.payload).is_instance_of(tuple)
        assertpy.assert_that(deserialized_message.payload).is_length(2)
        assertpy.assert_that(deserialized_message.payload[0]).is_equal_to(ErrorCode.InvalidPayload)
        assertpy.assert_that(deserialized_message.request_id).is_equal_to(REQUEST_ID_FOR_RESPONSE_FOR_INVALID_FRAME)

    def test_that__handle_connection_should_send_error_frame_if_payload_golem_message_type_is_unexpected(self):
        # Prepare frame payload which is Golem message other than TransactionSigningRequest.
        middleman_message = GolemMessageFrame(
            payload=Ping(),
            request_id=99,
        )
        raw_message = middleman_message.serialize(private_key=CONCENT_PRIVATE_KEY)

        raw_message_received = self._prepare_and_execute_handle_connection(raw_message)

        deserialized_message = AbstractFrame.deserialize(
            raw_message=raw_message_received,
            public_key=SIGNING_SERVICE_PUBLIC_KEY,
        )

        assertpy.assert_that(deserialized_message.payload).is_instance_of(tuple)
        assertpy.assert_that(deserialized_message.payload).is_length(2)
        assertpy.assert_that(deserialized_message.payload[0]).is_equal_to(ErrorCode.UnexpectedMessage)
        assertpy.assert_that(deserialized_message.request_id).is_equal_to(REQUEST_ID_FOR_RESPONSE_FOR_INVALID_FRAME)

    def test_that__handle_connection_should_continue_loop_when_heartbeat_frame_is_received(self):
        heartbeat_frame = HeartbeatFrame(
            payload=None,
            request_id=777,
        )
        raw_message = heartbeat_frame.serialize(private_key=CONCENT_PRIVATE_KEY)
        with mock.patch('signing_service.signing_service.send_over_stream') as send_mock:
            with mock.patch('signing_service.signing_service.logger') as logger_mock:
                response = self._prepare_and_execute_handle_connection(raw_message, expect_response_from_scoket=False)

                assertpy.assert_that(response).is_equal_to(mock.sentinel.no_response)
                send_mock.assert_not_called()
                logger_mock.info.assert_not_called()

    def _prepare_and_execute_handle_connection(
        self,
        raw_message,
        handle_connection_wrapper=None,
        expect_response_from_scoket=True
    ):
        def mocked_generator():
            yield raw_message
            raise SigningServiceValidationError()

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
                    client_socket.setblocking(False)

                    with pytest.raises(SigningServiceValidationError):
                        if handle_connection_wrapper is not None:
                            handle_connection_wrapper(signing_service, connection, mocked_generator())
                        else:
                            signing_service._handle_connection(mocked_generator(), connection)

                    if expect_response_from_scoket:
                        response = next(unescape_stream(connection=client_socket))
                    else:
                        # We do not expect to get anything from the socket, dummy response is returned.
                        response = mock.sentinel.no_response

        return response
