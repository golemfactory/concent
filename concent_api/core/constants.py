from enum import IntEnum
import re

from golem_messages.utils import encode_hex
from ethereum.transactions import Transaction

# Defines available scene file paths for Concent validators
VALID_SCENE_FILE_PREFIXES = ['/golem/resources/']

# Defines available scene file extension for Blender render
SCENE_FILE_EXTENSION = '.blend'

# Defines max length of task_id passed in Golem Messages.
MESSAGE_TASK_ID_MAX_LENGTH = 36

#  Defines regex for database migrations to valid uuid
REGEX_FOR_VALID_UUID = r'^[a-f0-9]{8}-?[a-f0-9]{4}-?4[a-f0-9]{3}-?[89ab][a-f0-9]{3}-?[a-f0-9]{12}\Z'

# Defines exact length of Ethereum key used to identify Golem clients.
GOLEM_PUBLIC_KEY_LENGTH = 64

# Defines length of Clients ids, public keys or ethereum public keys in hex convert
GOLEM_PUBLIC_KEY_HEX_LENGTH = 128

# Defines length of Ethereum address
ETHEREUM_ADDRESS_LENGTH = 42

# Defines length of Ethereum public key.
ETHEREUM_PUBLIC_KEY_LENGTH = 128

# Defines the length of Ethereum transaction's hash
ETHEREUM_TRANSACTION_HASH_LENGTH = 64

# Defines length of Clients ids, public keys or ethereum public keys
TASK_OWNER_KEY_LENGTH = 64

# Regular expresion of allowed characters and length of checksum hash
VALID_SHA1_HASH_REGEX = re.compile(r"^[a-fA-F\d]{40}$")

CELERY_LOCKED_SUBTASK_DELAY = 60

MAXIMUM_VERIFICATION_RESULT_TASK_RETRIES = 3

# Defines how many seconds should SCI callback wait for response from MiddleMan.
SCI_CALLBACK_MAXIMUM_TIMEOUT = 30

VERIFICATION_RESULT_SUBTASK_STATE_ACCEPTED_LOG_MESSAGE = (
    'Verification has timed out and a client has already asked about the result '
    'or verification result for subtask with ID {} must have been already processed.'
)


VERIFICATION_RESULT_SUBTASK_STATE_FAILED_LOG_MESSAGE = (
    'Verification result for subtask with ID {} must have been already processed.'
)


VERIFICATION_RESULT_SUBTASK_STATE_UNEXPECTED_LOG_MESSAGE = (
    'Subtask is in state {} '
    'instead in states ACCEPTED, FAILED or ADDITIONAL_VERIFICATION while handling verification result.'
)


CLIENT_ETH_ADDRESS_WITH_0_DEPOSIT = '0xAeeb9ea087B73Bdb3A100841Bea1c71f66fA8909'


MOCK_TRANSACTION = Transaction(
    nonce=1,
    gasprice=10 ** 6,
    startgas=80000,
    to=b'7917bc33eea648809c28',
    value=10,
    v=1,
    r=11,
    s=12,
    data=b'3078666333323333396130303030303030303030303030303030303030303030303032393662363963383738613734393865663463343531363436353231336564663834666334623330303030303030303030303030303030303030303030303030333431336437363161356332633362656130373531373064333239363566636161386261303533633030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303237313030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303562343336643666',
)

MOCK_TRANSACTION_HASH = encode_hex(MOCK_TRANSACTION.hash)


class VerificationResult(IntEnum):
    MATCH       = 0
    MISMATCH    = 1
    ERROR       = 2
