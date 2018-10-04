from common.exceptions import ConcentBaseException


class VerificationRequestAlreadyAcknowledgedError(ConcentBaseException):
    pass


class VerificationRequestAlreadyInitiatedError(ConcentBaseException):
    pass
