from enum import Enum


CELERY_LOCKED_SUBTASK_DELAY = 60

MAXIMUM_VERIFICATION_RESULT_TASK_RETRIES = 3

# Defines data chunk size in bytes when unpacking archives.
UNPACK_CHUNK_SIZE = 50  # bytes


class VerificationResult(Enum):
    MATCH       = 'match'
    MISMATCH    = 'mismatch'
    ERROR       = 'error'


VERIFICATION_RESULT_SUBTASK_STATE_ACCEPTED_LOG_MESSAGE = (
    'Verification has timed out and a client has already asked about the result '
    'or verification result for subtask with ID {} must have been already processed.'
)


VERIFICATION_RESULT_SUBTASK_STATE_FAILED_LOG_MESSAGE = (
    'Verification result for subtask with ID {} must have been already processed.'
)


VERIFICATION_RESULT_SUBTASK_STATE_UNEXPECTED_LOG_MESSAGE = (
    'Subtask with ID {} is in state {} '
    'instead in states ACCEPTED, FAILED or ADDITIONAL_VERIFICATION while handling verification result.'
)
