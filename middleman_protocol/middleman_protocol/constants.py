from enum import IntEnum
from enum import unique

from middleman_protocol import exceptions


@unique
class PayloadType(IntEnum):
    GOLEM_MESSAGE               = 0  # A serialized Golem message.
    ERROR                       = 1  # An error code and an error message.
    AUTHENTICATION_CHALLENGE    = 2  # A random string of bytes.
    AUTHENTICATION_RESPONSE     = 3  # A digital signature of the content sent as authentication challenge.


@unique
class ErrorCode(IntEnum):
    InvalidFrame            = 0
    InvalidFrameSignature   = 1
    DuplicateFrame          = 2
    InvalidPayload          = 3
    UnexpectedMessage       = 4
    AuthenticationFailure   = 5
    ConnectionLimitExceeded = 6
    MessageLost             = 7
    ConnectionTimeout       = 8
    Unknown                 = 9


# Random sequence of bytes used as separator between messages. Should be placed after frame.
FRAME_SEPARATOR = b'\x1d'

assert len(FRAME_SEPARATOR) == 1

FRAME_SIGNATURE_BYTES_LENGTH = 65
FRAME_REQUEST_ID_BYTES_LENGTH = 4
FRAME_PAYLOAD_TYPE_LENGTH = 1

FRAME_PAYLOAD_STARTING_BYTE = (
    FRAME_SIGNATURE_BYTES_LENGTH +
    FRAME_REQUEST_ID_BYTES_LENGTH +
    FRAME_PAYLOAD_TYPE_LENGTH
)

ESCAPE_CHARACTER = b'\xa2'
ESCAPE_SEQUENCES = {
    ESCAPE_CHARACTER: ESCAPE_CHARACTER + b'\x00',
    FRAME_SEPARATOR: ESCAPE_CHARACTER + b'\x01',
}

assert len(ESCAPE_CHARACTER) == 1
assert ESCAPE_CHARACTER != FRAME_SEPARATOR
assert len(set(ESCAPE_SEQUENCES.values())) == len(ESCAPE_SEQUENCES)
assert all([FRAME_SEPARATOR not in escape_sequence for escape_sequence in ESCAPE_SEQUENCES.values()])

RECEIVE_BYTES_PER_LOOP = 1
MAXIMUM_FRAME_LENGTH = 1000

MIDDLEMAN_EXCEPTION_TO_ERROR_CODE_MAP = {
    exceptions.PayloadTypeInvalidMiddlemanProtocolError: ErrorCode.InvalidPayload,
    exceptions.RequestIdInvalidTypeMiddlemanProtocolError: ErrorCode.InvalidFrame,
    exceptions.SignatureInvalidMiddlemanProtocolError: ErrorCode.InvalidFrameSignature,
    exceptions.PayloadInvalidMiddlemanProtocolError: ErrorCode.InvalidPayload,
    exceptions.FrameInvalidMiddlemanProtocolError: ErrorCode.InvalidFrame,
    exceptions.MiddlemanProtocolError: ErrorCode.Unknown,
}
