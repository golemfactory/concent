from typing             import Union
from golem_messages     import message

from core.constants     import GOLEM_PUBLIC_KEY_LENGTH
from core.constants     import MESSAGE_TASK_ID_MAX_LENGTH
from core.exceptions    import Http400


def validate_golem_message_reject(
    golem_message: Union[message.CannotComputeTask, message.TaskFailure, message.TaskToCompute]
):
    if not isinstance(golem_message, (message.CannotComputeTask, message.TaskFailure, message.TaskToCompute)):
        raise Http400("Expected CannotComputeTask, TaskFailure or TaskToCompute.")

    if isinstance(golem_message, message.CannotComputeTask):
        validate_id_value(golem_message.task_to_compute.compute_task_def['task_id'], 'task_id')

    if isinstance(golem_message, (message.TaskToCompute, message.TaskFailure)):
        if golem_message.compute_task_def['task_id'] == '':
            raise Http400("task_id cannot be blank.")

        golem_message.compute_task_def['deadline'] = validate_int_value(golem_message.compute_task_def['deadline'])


def validate_int_value(value):
    """
    Checks if value is an integer. If not, tries to cast it to an integer.
    Then checks if value is non-negative.

    """
    if not isinstance(value, int):
        try:
            value = int(value)
        except (ValueError, TypeError):
            raise Http400("Wrong type, expected a value that can be converted to an integer.")
    if value < 0:
        raise Http400("Wrong type, expected non-negative integer but negative integer provided.")
    return value


def validate_id_value(value, field_name):
    if not isinstance(value, str):
        raise Http400("{} must be string.".format(field_name))

    if value == '':
        raise Http400("{} cannot be blank.".format(field_name))

    if len(value) > MESSAGE_TASK_ID_MAX_LENGTH:
        raise Http400("{} cannot be longer than {} chars.".format(field_name, MESSAGE_TASK_ID_MAX_LENGTH))


def validate_public_key(value, field_name):
    assert isinstance(field_name, str)

    if not isinstance(value, bytes):
        raise Http400("{} must be string.".format(field_name))

    if len(value) != GOLEM_PUBLIC_KEY_LENGTH:
        raise Http400("The length of {} must be exactly {} characters.".format(field_name, GOLEM_PUBLIC_KEY_LENGTH))


def validate_golem_message_task_to_compute(golem_message: message.base.Message):
    if not isinstance(golem_message, message.TaskToCompute):
        raise Http400("Expected TaskToCompute.")

    golem_message.compute_task_def['deadline'] = validate_int_value(golem_message.compute_task_def['deadline'])

    validate_id_value(golem_message.compute_task_def['task_id'], 'task_id')

    validate_public_key(golem_message.provider_public_key, 'provider_public_key')
    validate_public_key(golem_message.requestor_public_key, 'requestor_public_key')
