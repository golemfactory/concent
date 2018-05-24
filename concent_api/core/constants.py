import re


# Defines max length of task_id passed in Golem Messages.
MESSAGE_TASK_ID_MAX_LENGTH = 128

# Defines exact length of Ethereum key used to identify Golem clients.
GOLEM_PUBLIC_KEY_LENGTH = 64

# Defines length of Ethereum address
ETHEREUM_ADDRESS_LENGTH = 42

# Defines length of Clients ids, public keys or ethereum public keys
TASK_OWNER_KEY_LENGTH = 64

# Regular expresion of allowed characters in task_id and subtask_id
VALID_ID_REGEX = re.compile(r'[a-zA-Z0-9_-]*')
