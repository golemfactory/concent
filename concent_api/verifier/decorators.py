import time
from functools import wraps

from django.conf import settings
from django.db import DatabaseError

from common.constants import ErrorCode
from core.constants import VerificationResult
from core.exceptions import Http500
from core.tasks import verification_result
from verifier.exceptions import VerificationError
from verifier.utils import clean_directory


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
        finally:
            # Remove any files left in VERIFIER_STORAGE_PATH.
            clean_directory(settings.VERIFIER_STORAGE_PATH)
    return wrapper


def ensure_retry_of_locked_calls(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        repeat_handler = RepeatHandler()
        wait_time_in_sec = 0.05
        should_repeat = True
        result = None

        while should_repeat:
            try:
                result = func(*args, **kwargs)
                should_repeat = False
            except DatabaseError:
                repeat_handler.is_max_number_of_tries_exceeded()
                time.sleep(wait_time_in_sec)
        return result
    return wrapper


class RepeatHandler:

    def __init__(self):
        self.max_number_of_retries = 100
        self.current_number_of_retries = 0

    def is_max_number_of_tries_exceeded(self):
        if self.current_number_of_retries < self.max_number_of_retries:
            self.current_number_of_retries = self.current_number_of_retries + 1
        else:
            raise Http500(
                "Maximum number of retries of function updating Subtask extended",
                error_code=ErrorCode.CONCENT_APPLICATION_CRASH,
            )
