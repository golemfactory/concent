from typing                         import Union
from typing                         import List
from golem_messages                 import message
from golem_messages.cryptography    import ecdsa_verify
from golem_messages.exceptions      import MessageError

from core.constants                 import GOLEM_PUBLIC_KEY_LENGTH
from core.constants                 import MESSAGE_TASK_ID_MAX_LENGTH
from core.exceptions                import Http400


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
        raise Http400("{} must be bytes.".format(field_name))

    if len(value) != GOLEM_PUBLIC_KEY_LENGTH:
        raise Http400("The length of {} must be exactly {} characters.".format(field_name, GOLEM_PUBLIC_KEY_LENGTH))


def validate_golem_message_task_to_compute(golem_message: message.base.Message):
    if not isinstance(golem_message, message.TaskToCompute):
        raise Http400("Expected TaskToCompute.")

    golem_message.compute_task_def['deadline'] = validate_int_value(golem_message.compute_task_def['deadline'])

    validate_id_value(golem_message.compute_task_def['task_id'], 'task_id')

    validate_public_key(golem_message.provider_public_key, 'provider_public_key')
    validate_public_key(golem_message.requestor_public_key, 'requestor_public_key')


def validate_report_computed_task_time_window(report_computed_task):
    assert isinstance(report_computed_task, message.ReportComputedTask)

    if report_computed_task.timestamp < report_computed_task.task_to_compute.timestamp:
        raise Http400("ReportComputedTask timestamp is older then nested TaskToCompute.")


def validate_golem_message_client_authorization(golem_message: message.concents.ClientAuthorization):
    if not isinstance(golem_message, message.concents.ClientAuthorization):
        raise Http400('Expected ClientAuthorization.')

    validate_public_key(golem_message.client_public_key, 'client_public_key')


def validate_list_of_identical_task_to_compute(list_of_task_to_compute: List[message.TaskToCompute]):
    assert isinstance(list_of_task_to_compute, list)
    assert all([isinstance(task_to_compute, message.TaskToCompute) for task_to_compute in list_of_task_to_compute])

    if len(list_of_task_to_compute) <= 1:
        return True

    base_task_to_compute = list_of_task_to_compute[0]

    for i, task_to_compute in enumerate(list_of_task_to_compute[1:], start = 1):
        for slot in message.TaskToCompute.__slots__:
            if getattr(base_task_to_compute, slot) != getattr(task_to_compute, slot):
                raise Http400(
                    'TaskToCompute messages are not identical. '
                    'There is a difference between messages with index 0 on passed list and with index {}'
                    'The difference is on field {}: {} is not equal {}'.format(
                        i,
                        slot,
                        getattr(base_task_to_compute, slot),
                        getattr(task_to_compute, slot),
                    )
                )

    return True


def validate_golem_message_signed_with_key(
    golem_message: message.base.Message,
    public_key: bytes,
):
    assert isinstance(golem_message,    message.base.Message)

    validate_public_key(public_key, 'public_key')

    try:
        ecdsa_verify(public_key, golem_message.sig, golem_message.get_short_hash())
    except MessageError:
        raise Http400(
            'There was an exception when validating if golem_message {} is signed with public key {}'.format(
                golem_message.TYPE,
                public_key
            )
        )
