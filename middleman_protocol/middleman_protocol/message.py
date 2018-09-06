from abc import ABC
from abc import abstractmethod

from mypy.types import Any

from construct import Byte
from construct import Bytes
from construct import BytesInteger
from construct import Container
from construct import Enum
from construct import GreedyBytes
from construct import Int16ub
from construct import PascalString
from construct import Prefixed
from construct import StreamError
from construct import Struct
from construct import VarInt

from golem_messages.cryptography import ecdsa_sign
from golem_messages.cryptography import ecdsa_verify
from golem_messages.exceptions import InvalidSignature
from golem_messages.message.base import Message as BaseGolemMessage

from .constants import FRAME_PAYLOAD_TYPE_LENGTH
from .constants import FRAME_PAYLOAD_STARTING_BYTE
from .constants import FRAME_REQUEST_ID_BYTES_LENGTH
from .constants import FRAME_SIGNATURE_BYTES_LENGTH
from .constants import PayloadType
from .exceptions import FrameInvalidMiddlemanProtocolError
from .exceptions import PayloadInvalidMiddlemanProtocolError
from .exceptions import PayloadTypeInvalidMiddlemanProtocolError
from .exceptions import RequestIdInvalidTypeMiddlemanProtocolError
from .exceptions import SignatureInvalidMiddlemanProtocolError
from .registry import PAYLOAD_TYPE_TO_MIDDLEMAN_MESSAGE_CLASS
from .registry import register


class AbstractFrame(ABC):
    """
    Abstract class for inheriting by Middleman protocol messages.

    Contains base functionality like:
    - serialization,
    - deserialization,
    - frame validation.

    Subclasses must implement:
    - parsing payload to bytes on serialization,
    - parsing serialized bytes payload back to original format on deserialization,
    - validation of original payload before serialization.

    """

    __slots__ = [
        'payload',
        'payload_type',
        'request_id',
    ]

    def __init__(self, payload: Any, request_id: int) -> None:
        self._validate_request_id(request_id)
        self.request_id = request_id

        self._validate_payload(payload)
        self.payload = payload

    def __eq__(self, other: Any) -> bool:
        """Overrides the default implementation for our tests"""
        if isinstance(other, AbstractFrame):
            return (
                self.payload == other.payload and
                self.payload_type == other.payload_type and  # type: ignore
                self.request_id == other.request_id
            )
        return False

    @classmethod
    @abstractmethod
    def _deserialize_payload(cls, payload: bytes) -> Any:
        pass

    @abstractmethod
    def _serialize_payload(self, payload: Any) -> bytes:
        pass

    @abstractmethod
    def _validate_payload(self, payload: Any) -> None:
        pass

    @classmethod
    def get_frame_format(cls) -> Struct:
        """ Returns Struct object containing frame structure. """
        frame_format = Struct(
            frame_signature=Bytes(FRAME_SIGNATURE_BYTES_LENGTH),
            signed_part_of_the_frame=Struct(
                request_id=BytesInteger(FRAME_REQUEST_ID_BYTES_LENGTH),
                payload_type=Enum(Byte, PayloadType),
                payload=Prefixed(VarInt, GreedyBytes),
            ),
        )

        assert FRAME_PAYLOAD_STARTING_BYTE == (
            frame_format.frame_signature.subcon.length +
            frame_format.signed_part_of_the_frame.request_id.subcon.length +
            FRAME_PAYLOAD_TYPE_LENGTH
        )

        return frame_format

    @classmethod
    def deserialize(cls, raw_message: bytes, public_key: bytes) -> 'AbstractFrame':
        """
        Parses and validates received message in bytes.
        Returns deserialized frame with deserialized payload.
        """
        assert isinstance(raw_message, bytes)
        assert isinstance(public_key, bytes)

        # Parse frame
        frame_format = cls.get_frame_format()
        try:
            frame = frame_format.parse(raw_message)
        except StreamError as exception:
            raise FrameInvalidMiddlemanProtocolError(
                f'Protocol frame is malformed and could not be deserialized: {exception}.'
            )

        raw_signed_part_of_the_frame = frame_format.signed_part_of_the_frame.build(
            frame.signed_part_of_the_frame
        )

        # Validate
        cls._validate_signature(raw_signed_part_of_the_frame, frame.frame_signature, public_key)
        cls._validate_payload_type(frame.signed_part_of_the_frame.payload_type)

        # Get class related to current payload type
        message_class = PAYLOAD_TYPE_TO_MIDDLEMAN_MESSAGE_CLASS[
            PayloadType[str(frame.signed_part_of_the_frame.payload_type)]
        ]

        # Deserialize payload
        deserialized_payload = message_class._deserialize_payload(frame.signed_part_of_the_frame.payload)

        # Recreate original message
        message = message_class(
            payload=deserialized_payload,
            request_id=frame.signed_part_of_the_frame.request_id
        )

        return message

    @classmethod
    def _validate_payload_type(cls, payload_type: int) -> None:
        if (
            not hasattr(PayloadType, str(payload_type)) or
            PayloadType[str(payload_type)] not in PAYLOAD_TYPE_TO_MIDDLEMAN_MESSAGE_CLASS
        ):
            raise PayloadTypeInvalidMiddlemanProtocolError(
                f'Payload type {payload_type} is not valid or not registered.'
            )

    @classmethod
    def _validate_request_id(cls, request_id: int) -> None:
        if not isinstance(request_id, int):
            raise RequestIdInvalidTypeMiddlemanProtocolError(
                f'request_id is {type(request_id)} instead of int.'
            )

    @classmethod
    def _validate_signature(cls, raw_signed_part_of_the_frame: bytes, signature: bytes, public_key: bytes) -> None:
        try:
            ecdsa_verify(
                pubkey=public_key,
                signature=signature,
                message=raw_signed_part_of_the_frame,
            )
        except InvalidSignature:
            raise SignatureInvalidMiddlemanProtocolError(
                'Frame signature does not match its content.'
            )

    def serialize(self, private_key: bytes) -> bytes:
        """ Parses payload into bytes message. """
        serialized_payload = self._serialize_payload(self.payload)

        assert isinstance(serialized_payload, bytes)

        frame_format = self.get_frame_format()

        # Create and build part of the frame which will be signed
        signed_part_of_the_frame = Container(
            request_id=self.request_id,
            payload_type=self.payload_type,  # type: ignore  # pylint: disable=no-member
            payload=serialized_payload,
        )
        raw_signed_part_of_the_frame = frame_format.signed_part_of_the_frame.build(
            signed_part_of_the_frame
        )

        # Create signature of part of the frame
        frame_signature = ecdsa_sign(privkey=private_key, msghash=raw_signed_part_of_the_frame)

        # Create frame with signature
        frame = Container(
            frame_signature=frame_signature,
            signed_part_of_the_frame=signed_part_of_the_frame,
        )
        raw_frame = frame_format.build(frame)

        return raw_frame


@register
class GolemMessageFrame(AbstractFrame):
    """ Subclass of AbstractFrame for handling Golem Message payload type. """

    payload_type = PayloadType.GOLEM_MESSAGE

    @classmethod
    def _deserialize_payload(cls, payload: bytes) -> BaseGolemMessage:
        return BaseGolemMessage.deserialize(payload, None, check_time=False)

    def _serialize_payload(self, payload: BaseGolemMessage) -> bytes:
        return payload.serialize()

    def _validate_payload(self, payload: BaseGolemMessage) -> None:
        if not isinstance(payload, BaseGolemMessage):
            raise PayloadInvalidMiddlemanProtocolError(
                f'Trying to create GolemMessageFrame but the received payload type is {type(payload)} '
                f'instead of Golem Message.'
            )


@register
class ErrorFrame(AbstractFrame):
    """ Subclass of AbstractFrame for handling error code with error message payload type. """

    payload_type = PayloadType.ERROR

    @classmethod
    def _deserialize_payload(cls, payload: bytes) -> tuple:
        error_payload_format = cls.get_error_payload_format()
        error_payload = error_payload_format.parse(payload)
        return (error_payload.error_code, error_payload.error_message)

    def _serialize_payload(self, payload: tuple) -> bytes:
        error_payload_format = self.get_error_payload_format()
        error_payload = Container(
            error_code=payload[0],
            error_message=payload[1],
        )
        raw_error_payload = error_payload_format.build(error_payload)
        return raw_error_payload

    def _validate_payload(self, payload: tuple) -> None:
        if not isinstance(payload, tuple):
            raise PayloadInvalidMiddlemanProtocolError(
                f'Trying to create ErrorFrame but passed type payload is '
                f'{type(payload)} instead of tuple. It must be pair of error code and error message.'
            )
        if len(payload) != 2:
            raise PayloadInvalidMiddlemanProtocolError(
                f'Trying to create ErrorFrame but passed payload tuple has length '
                f'{len(payload)} instead of 2. It must be pair of error code and error message.'
            )
        if not isinstance(payload[0], int):
            raise PayloadInvalidMiddlemanProtocolError(
                f'First element of payload tuple passed to ErrorFrame must be error code integer '
                f'instead of {type(payload[0])}.'
            )
        if not isinstance(payload[1], str):
            raise PayloadInvalidMiddlemanProtocolError(
                f'Second element of payload tuple passed to ErrorFrame must be error message string '
                f'instead of {type(payload[1])}.'
            )

    @classmethod
    def get_error_payload_format(cls) -> Struct:
        return Struct(
            error_code=Int16ub,
            error_message=PascalString(VarInt, 'utf8'),
        )


@register
class AuthenticationChallengeFrame(AbstractFrame):
    """ Subclass of AbstractFrame for handling authentication challenge payload type. """

    payload_type = PayloadType.AUTHENTICATION_CHALLENGE

    @classmethod
    def _deserialize_payload(cls, payload: bytes) -> bytes:
        return payload

    def _serialize_payload(self, payload: bytes) -> bytes:
        return payload

    def _validate_payload(self, payload: bytes) -> None:
        pass


@register
class AuthenticationResponseFrame(AbstractFrame):
    """ Subclass of AbstractFrame for handling authentication response payload type. """

    payload_type = PayloadType.AUTHENTICATION_RESPONSE

    @classmethod
    def _deserialize_payload(cls, payload: bytes) -> bytes:
        return payload

    def _serialize_payload(self, payload: bytes) -> bytes:
        return payload

    def _validate_payload(self, payload: bytes) -> None:
        pass
