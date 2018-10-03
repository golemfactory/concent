import socket
from contextlib import closing
from unittest import TestCase

import assertpy
import mock
import pytest

from golem_messages.cryptography import ECCx
from golem_messages.message import Ping

from middleman_protocol.constants import FRAME_PAYLOAD_STARTING_BYTE
from middleman_protocol.constants import FRAME_SEPARATOR
from middleman_protocol.constants import ESCAPE_CHARACTER
from middleman_protocol.constants import ESCAPE_SEQUENCES
from middleman_protocol.exceptions import BrokenEscapingInFrameMiddlemanProtocolError
from middleman_protocol.message import AbstractFrame
from middleman_protocol.message import AuthenticationChallengeFrame
from middleman_protocol.message import AuthenticationResponseFrame
from middleman_protocol.message import ErrorFrame
from middleman_protocol.message import GolemMessageFrame
from middleman_protocol.stream import append_frame_separator
from middleman_protocol.stream import escape_decode_raw_message
from middleman_protocol.stream import escape_encode_raw_message
from middleman_protocol.stream import remove_frame_separator
from middleman_protocol.stream import send_over_stream
from middleman_protocol.stream import split_stream
from middleman_protocol.stream import unescape_stream

from .utils import assertpy_bytes_starts_with


concent_ecc_keys = ECCx(None)
(CONCENT_PRIVATE_KEY, CONCENT_PUBLIC_KEY) = concent_ecc_keys.raw_privkey, concent_ecc_keys.raw_pubkey


class TestEscapingAndHandlingSeparatorMiddlemanProtocol(TestCase):

    def test_that_append_frame_separator_should_add_frame_separator_to_given_bytes(self):
        raw = b'12345'

        assert FRAME_SEPARATOR not in raw

        raw_with_separator = append_frame_separator(raw)

        self.assertIn(FRAME_SEPARATOR, raw_with_separator)

    def test_that_remove_frame_separator_should_remove_frame_separator_from_given_bytes(self):
        raw_with_separator = append_frame_separator(b'12345')

        assert FRAME_SEPARATOR in raw_with_separator

        raw = remove_frame_separator(raw_with_separator)

        self.assertNotIn(FRAME_SEPARATOR, raw)

    def test_that_remove_frame_separator_should_remove_frame_separator_from_given_bytes_only_at_the_end(self):
        raw_with_separator = FRAME_SEPARATOR + append_frame_separator(b'12345')

        assert FRAME_SEPARATOR in raw_with_separator

        raw = remove_frame_separator(raw_with_separator)

        self.assertTrue(raw.startswith(FRAME_SEPARATOR))
        self.assertFalse(raw.endswith(FRAME_SEPARATOR))

    def test_that_remove_frame_separator_should_raise_exception_if_separator_is_not_at_the_end(self):
        raw_with_separator = append_frame_separator(b'12345') + b'1'

        assert FRAME_SEPARATOR in raw_with_separator

        with self.assertRaises(AssertionError):
            remove_frame_separator(raw_with_separator)

    def test_that_escape_encode_raw_message_should_replace_occurrences_of_frame_separator_and_escape_character(self):
        raw = FRAME_SEPARATOR + b'123' + ESCAPE_CHARACTER

        raw_escaped = escape_encode_raw_message(raw)

        self.assertEqual(raw_escaped, ESCAPE_SEQUENCES[FRAME_SEPARATOR] + b'123' + ESCAPE_SEQUENCES[ESCAPE_CHARACTER])

    def test_that_escape_decode_raw_message_should_replace_occurrences_of_escape_sequences(self):
        raw = FRAME_SEPARATOR + b'123' + ESCAPE_CHARACTER

        raw_escaped = escape_encode_raw_message(raw)
        raw_unescaped = escape_decode_raw_message(raw_escaped)

        self.assertEqual(raw, raw_unescaped)

    def test_that_escape_decode_raw_message_with_broken_escaping_should_raise_exception(self):
        wrong_escape_sequence = ESCAPE_CHARACTER + b'\xff'

        assert wrong_escape_sequence not in ESCAPE_SEQUENCES.values()

        with self.assertRaises(BrokenEscapingInFrameMiddlemanProtocolError):
            escape_decode_raw_message(wrong_escape_sequence)

    def test_that_escape_character_followed_by_related_escape_sequence_should_be_encoded_and_decoded_correctly(self):
        raw = ESCAPE_CHARACTER + ESCAPE_SEQUENCES[ESCAPE_CHARACTER]

        raw_escaped = escape_encode_raw_message(raw)
        raw_unescaped = escape_decode_raw_message(raw_escaped)

        self.assertEqual(raw, raw_unescaped)

    def test_that_frame_separator_followed_by_related_escape_sequence_should_be_encoded_and_decoded_correctly(self):
        raw = FRAME_SEPARATOR + ESCAPE_SEQUENCES[FRAME_SEPARATOR]

        raw_escaped = escape_encode_raw_message(raw)
        raw_unescaped = escape_decode_raw_message(raw_escaped)

        self.assertEqual(raw, raw_unescaped)


class TestUnescapeStreamHelperMiddlemanProtocol:

    request_id = 99

    @pytest.mark.parametrize(('middleman_message_type', 'payload'), [
        (GolemMessageFrame,            Ping()),
        (ErrorFrame,                   (111, 'error_message')),
        (AuthenticationChallengeFrame, b'random_bytes'),
        (AuthenticationResponseFrame,  b'TODO'),
    ])
    def test_that_receiving_any_message_should_be_handled_correctly(
        self,
        middleman_message_type,
        payload,
        unused_tcp_port,
    ):
        middleman_message = middleman_message_type(payload, self.request_id)

        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as server_socket:
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
            with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as client_socket:
                client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
                server_socket.bind(('127.0.0.1', unused_tcp_port))
                server_socket.listen(1)

                client_socket.connect(('127.0.0.1', unused_tcp_port))

                (connection, _address) = server_socket.accept()

                send_over_stream(
                    connection=client_socket,
                    raw_message=middleman_message,
                    private_key=CONCENT_PRIVATE_KEY
                )
                raw_message_received = next(unescape_stream(connection=connection))

        deserialized_message = AbstractFrame.deserialize(
            raw_message=raw_message_received,
            public_key=CONCENT_PUBLIC_KEY,
        )

        assertpy.assert_that(deserialized_message).is_instance_of(middleman_message_type)
        assertpy.assert_that(deserialized_message.payload).is_equal_to(payload)

    def test_that_receiving_a_series_of_messages_should_be_handled_correctly(self, unused_tcp_port):
        payload = Ping()
        middleman_message = GolemMessageFrame(payload, self.request_id)

        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as server_socket:
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
            with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as client_socket:
                client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
                server_socket.bind(('127.0.0.1', unused_tcp_port))
                server_socket.listen(1)

                client_socket.connect(('127.0.0.1', unused_tcp_port))

                (connection, _address) = server_socket.accept()

                for _i in range(10):
                    send_over_stream(
                        connection=client_socket,
                        raw_message=middleman_message,
                        private_key=CONCENT_PRIVATE_KEY
                    )

                unescape_stream_generator = unescape_stream(connection=connection)

                for _i in range(10):
                    raw_message_received = next(unescape_stream_generator)

                    deserialized_message = AbstractFrame.deserialize(
                        raw_message=raw_message_received,
                        public_key=CONCENT_PUBLIC_KEY,
                    )

                    assertpy.assert_that(deserialized_message).is_instance_of(GolemMessageFrame)
                    assertpy.assert_that(deserialized_message.payload).is_instance_of(Ping)
                    assertpy.assert_that(deserialized_message.payload).is_equal_to(payload)

    def test_that_receiving_encoded_message_should_decode_on_the_fly(self, unused_tcp_port):
        middleman_message = GolemMessageFrame(Ping(), self.request_id)
        raw_message = append_frame_separator(
            middleman_message.serialize(private_key=CONCENT_PRIVATE_KEY)
        )

        raw_message = raw_message[:10] + ESCAPE_CHARACTER + raw_message[len(ESCAPE_CHARACTER) + 10:]
        raw_message_encoded = escape_encode_raw_message(raw_message)

        assert FRAME_SEPARATOR not in raw_message_encoded

        raw_message_encoded = append_frame_separator(raw_message_encoded)

        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as server_socket:
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
            with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as client_socket:
                client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
                server_socket.bind(('127.0.0.1', unused_tcp_port))
                server_socket.listen(1)

                client_socket.connect(('127.0.0.1', unused_tcp_port))

                (connection, _address) = server_socket.accept()

                client_socket.send(raw_message_encoded)
                raw_message_received = next(unescape_stream(connection=connection))

        assertpy_bytes_starts_with(raw_message, raw_message_received)
        assertpy.assert_that(len(raw_message_received)).is_greater_than_or_equal_to(FRAME_PAYLOAD_STARTING_BYTE)

    def test_that_receiving_wrongly_encoded_message_should_return_none(self, unused_tcp_port):
        middleman_message = GolemMessageFrame(Ping(), self.request_id)
        raw_message = middleman_message.serialize(
            private_key=CONCENT_PRIVATE_KEY,
        )

        raw_message_encoded = escape_encode_raw_message(raw_message)
        raw_message_encoded = raw_message_encoded + ESCAPE_CHARACTER + b'\xff'
        raw_message_encoded = append_frame_separator(raw_message_encoded)

        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as server_socket:
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
            with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as client_socket:
                client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
                server_socket.bind(('127.0.0.1', unused_tcp_port))
                server_socket.listen(1)

                client_socket.connect(('127.0.0.1', unused_tcp_port))

                (connection, _address) = server_socket.accept()

                client_socket.send(raw_message_encoded)
                raw_message_received = next(unescape_stream(connection=connection))

        assertpy.assert_that(raw_message_received).is_none()

    def test_that_exceeding_maximum_frame_length_should_treat_exceeded_frame_as_invalid(self, unused_tcp_port):
        first_middleman_message = GolemMessageFrame(Ping(), self.request_id)
        first_raw_message = append_frame_separator(
            escape_encode_raw_message(
                first_middleman_message.serialize(
                    private_key=CONCENT_PRIVATE_KEY
                )
            )
        )
        second_middleman_message = AuthenticationChallengeFrame(
            payload=b'',
            request_id=100,
        )
        second_raw_message = append_frame_separator(
            escape_encode_raw_message(
                second_middleman_message.serialize(
                    private_key=CONCENT_PRIVATE_KEY
                )
            )
        )

        assert len(first_raw_message) > len(second_raw_message) + 10

        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as server_socket:
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
            with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as client_socket:
                client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
                server_socket.bind(('127.0.0.1', unused_tcp_port))
                server_socket.listen(1)

                client_socket.connect(('127.0.0.1', unused_tcp_port))

                (connection, _address) = server_socket.accept()

                client_socket.send(first_raw_message)
                client_socket.send(second_raw_message)

                with mock.patch('middleman_protocol.stream.MAXIMUM_FRAME_LENGTH', len(first_raw_message) - 10):
                    raw_message_received = next(unescape_stream(connection=connection))

        deserialized_message = AbstractFrame.deserialize(
            raw_message=raw_message_received,
            public_key=CONCENT_PUBLIC_KEY,
        )

        assertpy.assert_that(deserialized_message.request_id).is_equal_to(100)


class TestSplitStreamHelperMiddlemanProtocol:

    request_id = 99

    @pytest.mark.parametrize(('middleman_message_type', 'payload'), [
        (GolemMessageFrame,            Ping()),
        (ErrorFrame,                   (111, 'error_message')),
        (AuthenticationChallengeFrame, b'random_bytes'),
        (AuthenticationResponseFrame,  b'TODO'),
    ])
    def test_that_receiving_any_message_should_be_handled_correctly(
        self,
        middleman_message_type,
        payload,
        unused_tcp_port,
    ):
        middleman_message = middleman_message_type(payload, self.request_id)
        raw_message = escape_encode_raw_message(
            middleman_message.serialize(private_key=CONCENT_PRIVATE_KEY)
        )
        raw_message_with_separator = append_frame_separator(raw_message)

        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as server_socket:
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
            with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as client_socket:
                client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
                server_socket.bind(('127.0.0.1', unused_tcp_port))
                server_socket.listen(1)

                client_socket.connect(('127.0.0.1', unused_tcp_port))

                (connection, _address) = server_socket.accept()

                client_socket.send(raw_message_with_separator)
                raw_message_received = next(split_stream(connection=connection))

        assertpy.assert_that(raw_message).is_equal_to(raw_message_received)

    def test_that_receiving_a_series_of_messages_should_be_handled_correctly(self, unused_tcp_port):
        payload = Ping()
        middleman_message = GolemMessageFrame(payload, self.request_id)
        raw_message = escape_encode_raw_message(
            middleman_message.serialize(private_key=CONCENT_PRIVATE_KEY)
        )
        raw_message_with_separator = append_frame_separator(raw_message)

        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as server_socket:
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
            with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as client_socket:
                client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
                server_socket.bind(('127.0.0.1', unused_tcp_port))
                server_socket.listen(1)

                client_socket.connect(('127.0.0.1', unused_tcp_port))

                (connection, _address) = server_socket.accept()

                for _i in range(10):
                    client_socket.send(raw_message_with_separator)

                split_stream_generator = split_stream(connection=connection)

                for _i in range(10):
                    raw_message_received = next(split_stream_generator)

                    assertpy.assert_that(raw_message).is_equal_to(raw_message_received)

    def test_that_raising_error_in_generator_should_call_close_on_socket(self, unused_tcp_port):
        payload = Ping()
        middleman_message = GolemMessageFrame(payload, self.request_id)

        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as server_socket:
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
            with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as client_socket:
                client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
                server_socket.bind(('127.0.0.1', unused_tcp_port))
                server_socket.listen(1)

                client_socket.connect(('127.0.0.1', unused_tcp_port))

                (connection, _address) = server_socket.accept()

                send_over_stream(
                    connection=client_socket,
                    raw_message=middleman_message,
                    private_key=CONCENT_PRIVATE_KEY
                )

                split_stream_generator = split_stream(connection=connection)

                with mock.patch('middleman_protocol.stream.socket.socket.recv', side_effect=Exception()):
                    with mock.patch('middleman_protocol.stream.socket.socket.close') as mock_socket_close:
                        with pytest.raises(Exception):
                            next(split_stream_generator)

                mock_socket_close.assert_called_once()

    def test_that_when_socket_receives_no_bytes_socket_error_is_raised(self, unused_tcp_port):  # pylint: disable=no-self-use
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as server_socket:
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
            with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as client_socket:
                client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
                server_socket.bind(('127.0.0.1', unused_tcp_port))
                server_socket.listen(1)

                client_socket.connect(('127.0.0.1', unused_tcp_port))

                (connection, _address) = server_socket.accept()

                # Closing client socket will cause that socket.recv() function will read 0 bytes.
                client_socket.close()
                with pytest.raises(socket.error):
                    next(split_stream(connection=connection))
