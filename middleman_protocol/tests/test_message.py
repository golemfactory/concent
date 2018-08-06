import socket
from contextlib import closing

import assertpy
import pytest

from golem_messages.cryptography import ECCx
from golem_messages.cryptography import ecdsa_sign
from golem_messages.message import Ping
from golem_messages.message.concents import ServiceRefused

from middleman_protocol.constants import FRAME_PAYLOAD_STARTING_BYTE
from middleman_protocol.constants import FRAME_REQUEST_ID_BYTES_LENGTH
from middleman_protocol.constants import FRAME_SIGNATURE_BYTES_LENGTH
from middleman_protocol.constants import FRAME_PAYLOAD_TYPE_LENGTH
from middleman_protocol.constants import PayloadType
from middleman_protocol.exceptions import FrameInvalidMiddlemanProtocolError
from middleman_protocol.exceptions import PayloadTypeInvalidMiddlemanProtocolError
from middleman_protocol.exceptions import SignatureInvalidMiddlemanProtocolError
from middleman_protocol.message import AbstractFrame
from middleman_protocol.message import AuthenticationChallengeFrame
from middleman_protocol.message import AuthenticationResponseFrame
from middleman_protocol.message import ErrorFrame
from middleman_protocol.message import GolemMessageFrame
from middleman_protocol.registry import create_middleman_protocol_message
from middleman_protocol.registry import PAYLOAD_TYPE_TO_MIDDLEMAN_MESSAGE_CLASS
from middleman_protocol.stream import receive_frame
from middleman_protocol.stream import send_over_stream


concent_ecc_keys = ECCx(None)
(CONCENT_PRIVATE_KEY, CONCENT_PUBLIC_KEY) = concent_ecc_keys.raw_privkey, concent_ecc_keys.raw_pubkey


class TestMessageMiddlemanProtocol:

    request_id = 99

    @pytest.mark.parametrize(('expected_middleman_message_type', 'payload_type', 'payload'), [
        (GolemMessageFrame,            PayloadType.GOLEM_MESSAGE,            Ping()),
        (ErrorFrame,                   PayloadType.ERROR,                    (111, 'error_message')),
        (AuthenticationChallengeFrame, PayloadType.AUTHENTICATION_CHALLENGE, b'random_bytes'),
        (AuthenticationResponseFrame,  PayloadType.AUTHENTICATION_RESPONSE,  b'TODO'),
    ])
    def test_that_create_middleman_protocol_message_with_various_payload_types_should_create_proper_middleman_message(
        self,
        expected_middleman_message_type,
        payload_type,
        payload,
    ):
        message = create_middleman_protocol_message(
            payload_type,
            payload,
            self.request_id,
        )

        assertpy.assert_that(message).is_instance_of(expected_middleman_message_type)
        assertpy.assert_that(message.payload_type).is_equal_to(payload_type)

    def test_that_abstract_middleman_message_instantiation_should_raise_exception(self):
        with pytest.raises(TypeError):
            AbstractFrame(  # pylint: disable=abstract-class-instantiated
                Ping(),
                self.request_id,
            )

    @pytest.mark.parametrize(('middleman_message_type', 'payload'), [
        (GolemMessageFrame,            Ping()),
        (ErrorFrame,                   (111, 'error_message')),
        (AuthenticationChallengeFrame, b'random_bytes'),
        (AuthenticationResponseFrame,  b'TODO'),
    ])
    def test_that_serializing_and_deserializing_message_should_preserve_original_data(
        self,
        middleman_message_type,
        payload,
    ):
        middleman_message = middleman_message_type(payload, self.request_id)
        raw_message = middleman_message.serialize(private_key=CONCENT_PRIVATE_KEY)
        deserialized_message = AbstractFrame.deserialize(
            raw_message,
            public_key=CONCENT_PUBLIC_KEY,
        )

        assertpy.assert_that(deserialized_message).is_instance_of(middleman_message_type)
        assertpy.assert_that(deserialized_message.payload).is_instance_of(type(payload))
        assertpy.assert_that(deserialized_message.payload).is_equal_to(payload)

    @pytest.mark.parametrize(('middleman_message_type', 'payload'), [
        (GolemMessageFrame,            Ping()),
        (ErrorFrame,                   (111, 'error_message')),
        (AuthenticationChallengeFrame, b'random_bytes'),
        (AuthenticationResponseFrame,  b'TODO'),
    ])
    def test_that_sending_message_over_tcp_socket_should_preserve_original_data(
        self,
        middleman_message_type,
        payload,
    ):
        middleman_message = middleman_message_type(payload, self.request_id)

        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as server_socket:
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
            with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as client_socket:
                client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
                server_socket.bind(('127.0.0.1', 8001))
                server_socket.listen(1)

                client_socket.connect(('127.0.0.1', 8001))

                (connection, _address) = server_socket.accept()

                send_over_stream(
                    connection=client_socket,
                    raw_message=middleman_message,
                    private_key=CONCENT_PRIVATE_KEY
                )
                raw_message_received = next(receive_frame(connection=connection))

        deserialized_message = AbstractFrame.deserialize(
            raw_message=raw_message_received,
            public_key=CONCENT_PUBLIC_KEY,
        )

        assertpy.assert_that(deserialized_message).is_instance_of(middleman_message_type)
        assertpy.assert_that(deserialized_message.payload).is_instance_of(type(payload))
        assertpy.assert_that(deserialized_message.payload).is_equal_to(payload)

    def test_that_serializing_different_golem_message_middleman_messages_should_keep_part_of_header_the_same(self):
        message_1 = GolemMessageFrame(
            ServiceRefused(reason=ServiceRefused.REASON.InvalidRequest),
            self.request_id
        ).serialize(
            private_key=CONCENT_PRIVATE_KEY
        )
        message_2 = GolemMessageFrame(Ping(), self.request_id).serialize(private_key=CONCENT_PRIVATE_KEY)

        assertpy.assert_that(
            message_1[FRAME_SIGNATURE_BYTES_LENGTH:FRAME_PAYLOAD_STARTING_BYTE]
        ).is_equal_to(
            message_2[FRAME_SIGNATURE_BYTES_LENGTH:FRAME_PAYLOAD_STARTING_BYTE]
        )

    @pytest.mark.parametrize(('middleman_message_type', 'payload'), [
        (GolemMessageFrame,            Ping()),
        (ErrorFrame,                   (111, 'error_message')),
        (AuthenticationChallengeFrame, b'random_bytes'),
        (AuthenticationResponseFrame,  b'TODO'),
    ])
    def test_that_serializing_and_deserializing_message_with_wrong_signature_should_raise_exception(
        self,
        middleman_message_type,
        payload,
    ):
        middleman_message = middleman_message_type(payload, self.request_id)
        raw_message = middleman_message.serialize(private_key=CONCENT_PRIVATE_KEY)

        first_byte = raw_message[1] if raw_message[1] != 0 else 0
        malformed_raw_message = bytes(bytearray([first_byte - 1])) + raw_message[1:]

        with pytest.raises(SignatureInvalidMiddlemanProtocolError):
            AbstractFrame.deserialize(
                malformed_raw_message,
                CONCENT_PUBLIC_KEY,
            )

    def test_that_serializing_and_deserializing_message_with_wrong_payload_type_should_raise_exception(self):
        middleman_message = GolemMessageFrame(Ping(), self.request_id)
        raw_message = middleman_message.serialize(private_key=CONCENT_PRIVATE_KEY)

        payload_type_position = FRAME_SIGNATURE_BYTES_LENGTH + FRAME_REQUEST_ID_BYTES_LENGTH
        invalid_payload_type = 100

        # Sanity check for payload type in this case to be between expected bytes
        assert raw_message[payload_type_position:payload_type_position + 1] == b'\x00'
        assert invalid_payload_type not in PAYLOAD_TYPE_TO_MIDDLEMAN_MESSAGE_CLASS

        # Replace bytes with payload length
        raw_message = (
            raw_message[:payload_type_position] +
            bytes(bytearray([invalid_payload_type])) +
            raw_message[payload_type_position + FRAME_PAYLOAD_TYPE_LENGTH:]
        )

        # Replace message signature
        new_signature = ecdsa_sign(CONCENT_PRIVATE_KEY, raw_message[FRAME_SIGNATURE_BYTES_LENGTH:])
        raw_message_with_new_signature = new_signature + raw_message[FRAME_SIGNATURE_BYTES_LENGTH:]

        with pytest.raises(PayloadTypeInvalidMiddlemanProtocolError):
            AbstractFrame.deserialize(raw_message_with_new_signature, CONCENT_PUBLIC_KEY)

    @pytest.mark.parametrize(('middleman_message_type', 'payload'), [
        (GolemMessageFrame,            Ping()),
        (ErrorFrame,                   (111, 'error_message')),
        (AuthenticationChallengeFrame, b'random_bytes'),
        (AuthenticationResponseFrame,  b'TODO'),
    ])
    def test_that_serializing_and_deserializing_message_too_short_should_raise_exception(
        self,
        middleman_message_type,
        payload,
    ):
        middleman_message = middleman_message_type(payload, self.request_id)
        raw_message = middleman_message.serialize(private_key=CONCENT_PRIVATE_KEY)

        malformed_raw_message = raw_message[:-1]

        with pytest.raises(FrameInvalidMiddlemanProtocolError):
            AbstractFrame.deserialize(
                malformed_raw_message,
                CONCENT_PUBLIC_KEY,
            )
