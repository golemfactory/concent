from collections import namedtuple

DEFAULT_INTERNAL_PORT = 9054
DEFAULT_EXTERNAL_PORT = 9055
LOCALHOST_IP = "127.0.0.1"
ERROR_ADDRESS_ALREADY_IN_USE = "Error: address already in use"

RequestQueueItem = namedtuple(
    "RequestQueueItem",
    (
        "connection_id",
        "request_id",
        "message",
        "timestamp",
    )
)

ResponseQueueItem = namedtuple(
    "ResponseQueueItem",
    (
        "message",
        "request_id",
        "timestamp",
    )
)
