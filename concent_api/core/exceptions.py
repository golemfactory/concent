from common.exceptions import ConcentBaseException


class UnexpectedResponse(Exception):
    pass


class Http400(ConcentBaseException):
    pass


class FileTransferTokenError(ConcentBaseException):
    pass


class HashingAlgorithmError(ConcentBaseException):
    pass


class GolemMessageValidationError(ConcentBaseException):
    pass


class FrameNumberValidationError(ConcentBaseException):
    pass


class MaxRetriesExceededError(ConcentBaseException):
    pass


class TransactionNonceMismatch(Exception):
    pass
