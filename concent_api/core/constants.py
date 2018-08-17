from enum import IntEnum
import re

# Defines available scene file paths for Concent validators
VALID_SCENE_FILE_PREFIXES = ['/golem/resources/']

# Defines available scene file extension for Blender render
SCENE_FILE_EXTENSION = '.blend'

# Defines max length of task_id passed in Golem Messages.
MESSAGE_TASK_ID_MAX_LENGTH = 128

# Defines exact length of Ethereum key used to identify Golem clients.
GOLEM_PUBLIC_KEY_LENGTH = 64

# Defines length of Clients ids, public keys or ethereum public keys in hex convert
GOLEM_PUBLIC_KEY_HEX_LENGTH = 128

# Defines length of Ethereum address
ETHEREUM_ADDRESS_LENGTH = 42

# Defines length of Ethereum public key.
ETHEREUM_PUBLIC_KEY_LENGTH = 128

# Defines length of Clients ids, public keys or ethereum public keys
TASK_OWNER_KEY_LENGTH = 64

# Regular expresion of allowed characters in task_id and subtask_id
VALID_ID_REGEX = re.compile(r'[a-zA-Z0-9_-]*')

# Regular expresion of allowed characters and length of checksum hash
VALID_SHA1_HASH_REGEX = re.compile(r"^[a-fA-F\d]{40}$")

CELERY_LOCKED_SUBTASK_DELAY = 60

MAXIMUM_VERIFICATION_RESULT_TASK_RETRIES = 3


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


class VerificationResult(IntEnum):
    MATCH       = 0
    MISMATCH    = 1
    ERROR       = 2
