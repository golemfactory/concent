from typing import Optional
from typing import Union

from .constants import ErrorCode


class ConcentInSoftShutdownMode(Exception):
    pass


class ConcentFeatureIsNotAvailable(Exception):
    pass


class ConcentPendingTransactionError(Exception):
    pass


class ConcentBaseException(Exception):

    def __init__(self, error_message: Optional[str], error_code: ErrorCode) -> None:
        assert isinstance(error_message, Union[str, None].__args__)
        assert isinstance(error_code, ErrorCode)
        self.error_code = error_code
        self.error_message = '' if error_message is None else error_message
        super().__init__(error_message)


class ConcentValidationError(ConcentBaseException):
    pass


class NonPositivePriceTaskToComputeError(ConcentBaseException):
    pass
