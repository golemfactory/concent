
class SigningServiceValidationError(Exception):
    pass


class SigningServiceUnexpectedMessageError(Exception):
    pass


class SigningServiceMaximumReconnectionAttemptsExceeded(Exception):
    pass


class Base64DecodeError(Exception):
    pass
