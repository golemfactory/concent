from typing import Optional

from common.constants import ErrorCode
from common.exceptions import ConcentBaseException


class VerificationError(ConcentBaseException):
    def __init__(
        self,
        error_message: Optional[str],
        error_code: ErrorCode,
        subtask_id: str,
    ) -> None:
        super().__init__(error_message, error_code)
        assert isinstance(subtask_id, str)
        self.subtask_id = subtask_id


class VerificationMismatch(Exception):
    def __init__(
        self,
        subtask_id: str,
    ) -> None:
        super().__init__()
        assert isinstance(subtask_id, str)
        self.subtask_id = subtask_id
