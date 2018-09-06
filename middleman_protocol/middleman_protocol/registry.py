from mypy.types import Any
from mypy.types import Callable

from middleman_protocol.constants import PayloadType


PAYLOAD_TYPE_TO_MIDDLEMAN_MESSAGE_CLASS = {}  # type: ignore


def register(cls) -> Callable:  # type: ignore
    """
    This is decorator used to create registry of subclasses of middleman_protocol.message.AbstractFrame.

    Registry is used to get proper subclass depending on value from middleman_protocol.constants.PayloadType enum.
    It cannot be done directly as a dict because of circular import problem.
    """
    assert hasattr(cls, 'payload_type')
    assert cls.payload_type in PayloadType
    assert cls.payload_type not in PAYLOAD_TYPE_TO_MIDDLEMAN_MESSAGE_CLASS

    PAYLOAD_TYPE_TO_MIDDLEMAN_MESSAGE_CLASS[cls.payload_type] = cls
    return cls


def create_middleman_protocol_message(payload_type: PayloadType, payload: Any, request_id: int):  # type: ignore
    """ Helper function for creating Middleman protocol message depending on payload type. """
    assert payload_type in PayloadType
    assert payload_type in PAYLOAD_TYPE_TO_MIDDLEMAN_MESSAGE_CLASS

    return PAYLOAD_TYPE_TO_MIDDLEMAN_MESSAGE_CLASS[payload_type](payload, request_id)
