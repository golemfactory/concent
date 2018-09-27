from collections import namedtuple

DEFAULT_INTERNAL_PORT = 9054
DEFAULT_EXTERNAL_PORT = 9055
LOCALHOST_IP = "127.0.0.1"
ERROR_ADDRESS_ALREADY_IN_USE = "Error: address already in use"
CONNECTION_COUNTER_LIMIT = 987654321
PROCESSING_TIMEOUT = 5
STANDARD_ERROR_MESSAGE = "This connection has been already added"
WRONG_TYPE_ERROR_MESSAGE = "QueuePool can only contain mapping between connection ID (int) and response queue (asyncio.Queue)"
AUTHENTICATION_CHALLENGE_SIZE = 128

RequestQueueItem = namedtuple(
    "RequestQueueItem",
    (
        "connection_id",
        "concent_request_id",
        "message",
        "timestamp",
    )
)

ResponseQueueItem = namedtuple(
    "ResponseQueueItem",
    (
        "message",
        "concent_request_id",
        "timestamp",
    )
)

MessageTrackerItem = namedtuple(
    "MessageTrackerItem",
    (
        "concent_request_id",
        "connection_id",
        "message",
        "timestamp",
    )
)
