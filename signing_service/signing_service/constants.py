import re

SIGNING_SERVICE_DEFAULT_PORT = 9055

SIGNING_SERVICE_MAXIMUM_RECONNECT_TIME = 2**6

SIGNING_SERVICE_DEFAULT_INITIAL_RECONNECT_DELAY = 1

ETHEREUM_PRIVATE_KEY_REGEXP = re.compile(r'^[a-f0-9]{64}$')

# Defines how much time in seconds should SigningService wait for AuthenticationChallengeFrame.
RECEIVE_AUTHENTICATION_CHALLENGE_TIMEOUT = 20

# Defines how many times Signing Service should try reconnecting on socket error, before giving up and crashing.
SIGNING_SERVICE_DEFAULT_RECONNECT_ATTEMPTS = 10

# Defines how much time in seconds should SigningService wait for connection before deeming it unsuccessful.
CONNECTION_TIMEOUT = 10

# Daily limits for transactions sums in GNTB.
WARNING_DAILY_THRESHOLD = 1000

MAXIMUM_DAILY_THRESHOLD = 10000
