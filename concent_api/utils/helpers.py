import calendar
import base64
import binascii
import datetime
import time

from django.utils   import timezone

from golem_messages import message


def is_base64(data: str) -> bool:
    """
    Checks if given data is properly base64-encoded data.

    :returns bool
    """
    try:
        base64.b64decode(data, validate=True)
        return True
    except binascii.Error:
        return False


def decode_key(key: str) -> bytes:
    return base64.b64decode(key.encode('ascii'), validate = True)


def get_current_utc_timestamp() -> int:
    """
    Returns current timestamp as int.
    Returned timestamp is guaranteed to be in UTC on systems where epoch is January 1, 1970, 00:00:00 (UTC).

    """
    current_timestamp = int(timezone.now().timestamp())
    assert calendar.timegm(time.gmtime()) - current_timestamp <= 1
    return current_timestamp


def parse_datetime_to_timestamp(date_time: datetime.datetime) -> int:
    """
    Returns timestamp in UTC as int from given datetime.
    Returned timestamp is relative to UNIX epoch and should works the same on all operating systems.
    It works for both naive and timezone-aware datetime object. Naive datetime is interpreted as if it was in UTC.

    """
    if date_time.tzinfo is None:
        return int(date_time.replace(tzinfo = timezone.utc).timestamp())
    else:
        return int(date_time.astimezone(timezone.utc).timestamp())


def get_task_id_from_message(golem_message: message.base.Message) -> str:
    """
    Returns task_id nested inside given Golem Message depending on its type.

    Returns None if task_id is not available.
    """

    if isinstance(golem_message,            message.ComputeTaskDef):
        return golem_message['task_id']

    elif isinstance(golem_message,          message.TaskToCompute):
        return golem_message.compute_task_def['task_id']

    elif isinstance(golem_message,          message.concents.ForceGetTaskResult):
        return golem_message.report_computed_task.task_to_compute.compute_task_def['task_id'],

    elif isinstance(golem_message,          message.concents.ForceGetTaskResultUpload):
        return golem_message.force_get_task_result.report_computed_task.task_to_compute.compute_task_def['task_id']

    elif isinstance(golem_message, (
                                            message.VerdictReportComputedTask,
                                            message.concents.ForceSubtaskResults,
    )):
        return golem_message.ack_report_computed_task.task_to_compute.compute_task_def['task_id']

    elif isinstance(golem_message, (
                                            message.ForceReportComputedTask,
                                            message.AckReportComputedTask,
                                            message.concents.ForceGetTaskResultFailed,
    )):
        return golem_message.task_to_compute.compute_task_def['task_id']

    elif isinstance(golem_message,          message.RejectReportComputedTask):
        if isinstance(golem_message.cannot_compute_task, message.tasks.CannotComputeTask):
            return golem_message.cannot_compute_task.task_to_compute.compute_task_def['task_id']
        elif isinstance(golem_message.task_to_compute, message.tasks.TaskToCompute):
            return golem_message.task_to_compute.compute_task_def['task_id']

    elif isinstance(golem_message,          message.concents.ForceSubtaskResultsResponse):
        if isinstance(golem_message.subtask_results_accepted,   message.tasks.SubtaskResultsAccepted):
            return golem_message.subtask_results_accepted.subtask_id
        elif isinstance(golem_message.subtask_results_rejected, message.tasks.SubtaskResultsRejected):
            return golem_message.subtask_results_rejected.report_computed_task.subtask_id

    return None
