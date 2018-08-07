import socket

from typing import Iterator
from typing import Optional

from middleman_protocol.constants import ESCAPE_CHARACTER
from middleman_protocol.constants import ESCAPE_SEQUENCES
from middleman_protocol.constants import FRAME_SEPARATOR
from middleman_protocol.constants import MAXIMUM_FRAME_LENGTH
from middleman_protocol.constants import RECEIVE_BYTES_PER_LOOP
from middleman_protocol.exceptions import BrokenEscapingInFrameMiddlemanProtocolError
from middleman_protocol.message import AbstractFrame


def append_frame_separator(raw_frame: bytes) -> bytes:
    """ Adds frame separator to raw frame. """
    assert isinstance(raw_frame, bytes)

    return raw_frame + FRAME_SEPARATOR


def remove_frame_separator(raw_message: bytes) -> bytes:
    """ Remove frame separator from raw frame. """
    assert isinstance(raw_message, bytes)
    assert raw_message[-len(FRAME_SEPARATOR):] == FRAME_SEPARATOR

    return raw_message[:-len(FRAME_SEPARATOR)]


def escape_encode_raw_message(raw_message: bytes) -> bytes:
    """ Escapes occurrences of escape character and frame separator in raw message to avoid sending them in message. """
    return raw_message.replace(
        ESCAPE_CHARACTER, ESCAPE_SEQUENCES[ESCAPE_CHARACTER]
    ).replace(
        FRAME_SEPARATOR, ESCAPE_SEQUENCES[FRAME_SEPARATOR]
    )


def escape_decode_raw_message(raw_message: bytes) -> bytes:
    """
    Reverses escaping of occurrences of escape character and frame separator in raw message.
    If there is an escape character which is not a valid escape sequence,
    raise BrokenEscapingInFrameMiddlemanProtocolError.
    This can be checked by comparing sum of occurrences of escape character
    to sum of occurrences of escape sequences. If they are equal, data is escaped correctly.
    """
    if (
        raw_message.count(ESCAPE_CHARACTER) !=
        sum([raw_message.count(escape_sequence) for escape_sequence in ESCAPE_SEQUENCES.values()])
    ):
        raise BrokenEscapingInFrameMiddlemanProtocolError()
    else:
        return raw_message.replace(
            ESCAPE_SEQUENCES[ESCAPE_CHARACTER], ESCAPE_CHARACTER
        ).replace(
            ESCAPE_SEQUENCES[FRAME_SEPARATOR], FRAME_SEPARATOR
        )


def split_stream(connection: socket.socket) -> Iterator[bytes]:
    """
    Lowest level receiver which determines if received data is frame separator,
    which means previously received data should be yielded,
    or if received data is something else and receiver should continue to gather bytes.
    """
    assert isinstance(connection, socket.socket)

    received_data = []  # type: ignore

    try:
        while True:
            next_bytes = connection.recv(RECEIVE_BYTES_PER_LOOP)

            for next_byte in next_bytes:
                if bytes([next_byte]) == FRAME_SEPARATOR:
                    data_to_yield = b''.join(received_data)
                    received_data = []
                    if len(data_to_yield) <= MAXIMUM_FRAME_LENGTH:
                        yield data_to_yield
                else:
                    if MAXIMUM_FRAME_LENGTH < len(received_data):
                        continue
                    received_data.append(bytes([next_byte]))
    finally:
        connection.close()


def unescape_stream(connection: socket.socket) -> Iterator[Optional[bytes]]:
    """
    Top level receiver which determines if received data has broken escaping and yields None to indicate it,
    or reverses escaping and yields unescaped frame.
    """
    assert isinstance(connection, socket.socket)

    for unescaped_data in split_stream(connection=connection):
        assert isinstance(unescaped_data, bytes)
        assert (2 * ESCAPE_CHARACTER) not in ESCAPE_SEQUENCES.values()

        # If broken escaping was detected in received data,
        # yield special value indicating this and continue the outer loop.
        try:
            yield escape_decode_raw_message(unescaped_data)
        except BrokenEscapingInFrameMiddlemanProtocolError:
            yield None


def send_over_stream(connection: socket.socket, raw_message: AbstractFrame, private_key: bytes) -> int:
    """
    Helper for preparing AbstractFrame for sending through socket stream do actual send by doing:
    * serializing,
    * escaping,
    * adding frame separator,
    * sending over the socket.
    """
    assert isinstance(raw_message, AbstractFrame)
    assert isinstance(private_key, bytes)

    return connection.send(
        append_frame_separator(
            escape_encode_raw_message(
                raw_message.serialize(
                    private_key=private_key
                )
            )
        )
    )
