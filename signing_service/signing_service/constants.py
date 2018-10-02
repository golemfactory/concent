import re
import socket

SIGNING_SERVICE_DEFAULT_PORT = 9055

SIGNING_SERVICE_MAXIMUM_RECONNECT_TIME = 2**6

SIGNING_SERVICE_DEFAULT_INITIAL_RECONNECT_DELAY = 1

SIGNING_SERVICE_RECOVERABLE_ERRORS = [
    # 86 Streams pipe error
    socket.errno.ESTRPIPE,  # type: ignore
    # 90 Message too long
    socket.errno.EMSGSIZE,  # type: ignore
    # 100 Network is down
    socket.errno.ENETDOWN,  # type: ignore
    # 101 Network is unreachable
    socket.errno.ENETUNREACH,  # type: ignore
    # 102 Network dropped connection on reset
    socket.errno.ENETRESET,  # type: ignore
    # 103 Software caused connection abort
    socket.errno.ECONNABORTED,  # type: ignore
    # 104 Connection reset by peer
    socket.errno.ECONNRESET,  # type: ignore
    # 108 Cannot send after transport endpoint shutdown
    socket.errno.ESHUTDOWN,  # type: ignore
    # 110 Connection timed out
    socket.errno.ETIMEDOUT,  # type: ignore
    # 111 Connection refused
    socket.errno.ECONNREFUSED,  # type: ignore
    # 112 Host is down
    socket.errno.EHOSTDOWN,  # type: ignore
    # 113 No route to host
    socket.errno.EHOSTUNREACH,  # type: ignore
]

ETHEREUM_PRIVATE_KEY_REGEXP = re.compile(r'^[a-f0-9]{64}$')

# Defines how much time in seconds should SigningService wait for AuthenticationChallengeFrame.
RECEIVE_AUTHENTICATION_CHALLENGE_TIMEOUT = 20

# Defines how many times Signing Service should try reconnecting on socket error, before giving up and crashing.
SIGNING_SERVICE_DEFAULT_RECONNECT_ATTEMPTS = 10

# Defines how much time in seconds should SigningService wait for connection before deeming it unsuccessful.
CONNECTION_TIMEOUT = 10
