import datetime
import math
import time

from decorator import contextmanager
from django.conf                    import settings
from django.db import transaction, OperationalError

from golem_messages                 import message
from golem_messages.helpers         import maximum_download_time
from golem_messages.helpers         import subtask_verification_time
from golem_messages.utils import decode_hex

from core.exceptions import Http400, MaxRetriesExceededError
from common.constants import ErrorCode
from .constants import GOLEM_PUBLIC_KEY_LENGTH
from .constants import GOLEM_PUBLIC_KEY_HEX_LENGTH


def calculate_maximum_download_time(size: int, rate: int) -> int:
    """
    This function calls `maximum_download_time` helper function from golem messages or Concent custom implementation
    of it, depending on CUSTOM_PROTOCOL_TIMES setting value.
    The reason for using custom implementation is because it has hard-coded values and we cannot make it use values
    from our settings.
    """
    assert isinstance(size, int)
    assert isinstance(rate, int)
    assert size > 0
    assert rate > 0
    assert settings.DOWNLOAD_LEADIN_TIME > 0

    if settings.CUSTOM_PROTOCOL_TIMES:
        bytes_per_sec = rate << 10
        download_time = int(
            datetime.timedelta(
                seconds=int(math.ceil(size / bytes_per_sec))
            ).total_seconds()
        )

        return settings.DOWNLOAD_LEADIN_TIME + download_time
    else:
        return int(maximum_download_time(size, rate).total_seconds())


def calculate_subtask_verification_time(report_computed_task: message.ReportComputedTask) -> int:
    """
    This function calls `subtask_verification_time` helper function from golem messages or Concent custom implementation
    of it, depending on CUSTOM_PROTOCOL_TIMES setting value.
    The reason for using custom implementation is because it has hard-coded values and we cannot make it use values
    from our settings.
    """
    assert isinstance(report_computed_task, message.ReportComputedTask)

    if settings.CUSTOM_PROTOCOL_TIMES:
        mdt = calculate_maximum_download_time(
            size=report_computed_task.size,
            rate=settings.MINIMUM_UPLOAD_RATE
        )
        ttc_dt = datetime.datetime.utcfromtimestamp(
            report_computed_task.task_to_compute.timestamp,
        )
        subtask_dt = datetime.datetime.utcfromtimestamp(
            report_computed_task.task_to_compute.compute_task_def['deadline'],
        )
        subtask_timeout = subtask_dt - ttc_dt

        return int(
            (4 * settings.CONCENT_MESSAGING_TIME) +
            (3 * mdt) +
            (0.5 * subtask_timeout.total_seconds())
        )
    else:
        return int(subtask_verification_time(report_computed_task).total_seconds())


def calculate_additional_verification_call_time(
    subtask_results_rejected_timestamp: int,
    task_to_compute_deadline: int,
    task_to_compute_timestamp: int,
) -> int:
    """
    Calculates additional verification deadline using:
    * SubtaskResultRejected timestamp,
    * TaskToCompute deadline,
    * TaskToCompute timestamp.
    """
    return subtask_results_rejected_timestamp + int(
        (task_to_compute_deadline - task_to_compute_timestamp) *
        (settings.ADDITIONAL_VERIFICATION_TIME_MULTIPLIER / settings.BLENDER_THREADS)
    )


def hex_to_bytes_convert(client_public_key: str):
    if not isinstance(client_public_key, str):
        raise Http400(
            "Client public key must be string",
            error_code=ErrorCode.MESSAGE_VALUE_NOT_STRING
        )
    if not len(client_public_key) == GOLEM_PUBLIC_KEY_HEX_LENGTH:
        raise Http400(
            "Client public key must be length of 128 characters",
            error_code=ErrorCode.MESSAGE_VALUE_WRONG_LENGTH
        )
    key_bytes = decode_hex(client_public_key)
    assert len(key_bytes) == GOLEM_PUBLIC_KEY_LENGTH
    return key_bytes


def retry_handler(max_retries: int):
    next_retry_delay = settings.INITIAL_RETRY_DELAY
    retry_count = 0
    while retry_count <= max_retries:
        yield retry_count
        time.sleep(next_retry_delay)
        retry_count += 1
        next_retry_delay *= 2
    raise MaxRetriesExceededError("Maximum number of retries of handling this Subtask extended",
                                  error_code=ErrorCode.WORKER_MAX_RETRIES_EXCEEDED
                                  )


@contextmanager
def database_lock_rows(Subtask, subtask_id):
    for _ in retry_handler(settings.MAX_RETRIES):
        try:
            with transaction.atomic(using='control'):
                subtask = Subtask.objects.select_for_update(nowait=True).get(subtask_id=subtask_id)
        except OperationalError:
            pass
        else:
            yield subtask
            return
