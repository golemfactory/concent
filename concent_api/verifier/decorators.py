from functools import wraps

from core.constants import VerificationResult
from core.tasks import verification_result
from verifier.exceptions import VerificationError


def handle_verification_errors(task):
    @wraps(task)
    def wrapper(*args, **kwargs):
        try:
            return task(*args, **kwargs)
        except VerificationError as exception:
            verification_result.delay(
                exception.subtask_id,
                VerificationResult.ERROR.name,
                exception.error_message,
                exception.error_code.name
            )
    return wrapper
