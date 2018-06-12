from mypy.types import Optional

from utils.constants import ErrorCode


class UnexpectedResponse(Exception):
    pass


class ConcentInSoftShutdownMode(Exception):
    pass


class ConcentFeatureIsNotAvailable(Exception):
    pass


class ConcentBaseException(Exception):

    def __init__(self, error_message: Optional[str], error_code: ErrorCode) -> None:
        assert isinstance(error_message, (str, None))
        assert isinstance(error_code, ErrorCode)
        self.error_code = error_code
        self.error_message = '' if error_message is None else error_message
        super().__init__(error_message)


class Http400(ConcentBaseException):
    pass


class FileTransferTokenError(ConcentBaseException):
    pass


class HashingAlgorithmError(ConcentBaseException):
    pass
