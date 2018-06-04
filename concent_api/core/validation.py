from typing import List
from typing import Union
from golem_messages                 import message
from golem_messages.exceptions      import MessageError

from core.constants                 import ETHEREUM_ADDRESS_LENGTH
from core.constants                 import GOLEM_PUBLIC_KEY_LENGTH
from core.constants                 import GOLEM_PUBLIC_KEY_HEX_LENGTH
from core.constants                 import MESSAGE_TASK_ID_MAX_LENGTH
from core.constants                 import VALID_ID_REGEX
from core.exceptions                import Http400
from utils.constants                import ErrorCode


def validate_int_value(value):
    """
    Checks if value is an integer. If not, tries to cast it to an integer.
    Then checks if value is non-negative.

    """
    if not isinstance(value, int):
        try:
            value = int(value)
        except (ValueError, TypeError):
            raise Http400(
                "Wrong type, expected a value that can be converted to an integer.",
                error_code=ErrorCode.MESSAGE_VALUE_NOT_INTEGER,
            )
    if value < 0:
        raise Http400(
            "Wrong type, expected non-negative integer but negative integer provided.",
            error_code=ErrorCode.MESSAGE_VALUE_WRONG_TYPE,
        )
    return value


def validate_id_value(value, field_name):
    if not isinstance(value, str):
        raise Http400(
            "{} must be string.".format(field_name),
            error_code=ErrorCode.MESSAGE_VALUE_WRONG_TYPE,
        )

    if value == '':
        raise Http400(
            "{} cannot be blank.".format(field_name),
            error_code=ErrorCode.MESSAGE_VALUE_BLANK,
        )

    if len(value) > MESSAGE_TASK_ID_MAX_LENGTH:
        raise Http400(
            "{} cannot be longer than {} chars.".format(field_name, MESSAGE_TASK_ID_MAX_LENGTH),
            error_code=ErrorCode.MESSAGE_VALUE_WRONG_LENGTH,
        )

    if VALID_ID_REGEX.fullmatch(value) is None:
        raise Http400(
            f'{field_name} must contain only alphanumeric chars.',
            error_code=ErrorCode.MESSAGE_VALUE_NOT_ALLOWED,
        )


def validate_hex_public_key(value, field_name):
    validate_key_with_desired_parameters(field_name, value, str, GOLEM_PUBLIC_KEY_HEX_LENGTH)


def validate_bytes_public_key(value, field_name):
    validate_key_with_desired_parameters(field_name, value, bytes, GOLEM_PUBLIC_KEY_LENGTH)


def validate_key_with_desired_parameters(
        key_name: str,
        key_value,
        expected_type: Union,
        expected_lenght: int
):

    if not isinstance(key_value, expected_type):
        raise Http400(
            "{} must be {}.".format(key_name, str(expected_type)),
            error_code=ErrorCode.MESSAGE_VALUE_WRONG_TYPE,
        )

    if len(key_value) != expected_lenght:
        raise Http400(
            "The length of {} must be exactly {} characters.".format(key_name, expected_lenght),
            error_code=ErrorCode.MESSAGE_VALUE_WRONG_LENGTH,
        )


def validate_task_to_compute(task_to_compute: message.TaskToCompute):
    if not isinstance(task_to_compute, message.TaskToCompute):
        raise Http400(
            f"Expected TaskToCompute instead of {type(task_to_compute).__name__}.",
            error_code=ErrorCode.MESSAGE_INVALID,
        )

    if any(map(lambda x: x is None, [getattr(task_to_compute, attribute) for attribute in [
        'compute_task_def',
        'provider_public_key',
        'requestor_public_key'
    ]])):
        raise Http400(
            "Invalid TaskToCompute",
            error_code=ErrorCode.MESSAGE_WRONG_FIELDS,
        )
    task_to_compute.compute_task_def['deadline'] = validate_int_value(task_to_compute.compute_task_def['deadline'])

    validate_id_value(task_to_compute.compute_task_def['task_id'], 'task_id')
    validate_id_value(task_to_compute.compute_task_def['subtask_id'], 'subtask_id')

    validate_hex_public_key(task_to_compute.provider_public_key, 'provider_public_key')
    validate_hex_public_key(task_to_compute.requestor_public_key, 'requestor_public_key')
    validate_subtask_price_task_to_compute(task_to_compute)


def validate_report_computed_task_time_window(report_computed_task):
    assert isinstance(report_computed_task, message.ReportComputedTask)

    if report_computed_task.timestamp < report_computed_task.task_to_compute.timestamp:
        raise Http400(
            "ReportComputedTask timestamp is older then nested TaskToCompute.",
            error_code=ErrorCode.MESSAGE_TIMESTAMP_TOO_OLD,
        )


def validate_golem_message_client_authorization(golem_message: message.concents.ClientAuthorization):
    if not isinstance(golem_message, message.concents.ClientAuthorization):
        raise Http400(
            'Expected ClientAuthorization.',
            error_code=ErrorCode.AUTH_CLIENT_AUTH_MESSAGE_MISSING,
        )

    validate_bytes_public_key(golem_message.client_public_key, 'client_public_key')


def validate_all_messages_identical(golem_messages_list: List[message.Message]):
    assert isinstance(golem_messages_list, list)
    assert len(golem_messages_list) >= 1
    assert all(isinstance(golem_message, message.Message) for golem_message in golem_messages_list)
    assert len(set(type(golem_message) for golem_message in golem_messages_list)) == 1

    base_golem_message = golem_messages_list[0]

    for i, golem_message in enumerate(golem_messages_list[1:], start=1):
        for slot in base_golem_message.__slots__:
            if getattr(base_golem_message, slot) != getattr(golem_message, slot):
                raise Http400(
                    '{} messages are not identical. '
                    'There is a difference between messages with index 0 on passed list and with index {}'
                    'The difference is on field {}: {} is not equal {}'.format(
                        type(base_golem_message).__name__,
                        i,
                        slot,
                        getattr(base_golem_message, slot),
                        getattr(golem_message, slot),
                    ),
                    error_code=ErrorCode.MESSAGES_NOT_IDENTICAL,
                )


def validate_golem_message_signed_with_key(
    golem_message: message.base.Message,
    public_key: bytes,
):
    assert isinstance(golem_message, message.base.Message)

    validate_bytes_public_key(public_key, 'public_key')

    try:
        golem_message.verify_signature(public_key)
    except MessageError:
        raise Http400(
            'There was an exception when validating if golem_message {} is signed with public key {}'.format(
                golem_message.TYPE,
                public_key
            ),
            error_code=ErrorCode.MESSAGE_SIGNATURE_WRONG,
        )


def validate_golem_message_subtask_results_rejected(subtask_results_rejected: message.tasks.SubtaskResultsRejected):
    if not isinstance(subtask_results_rejected,  message.tasks.SubtaskResultsRejected):
        raise Http400(
            "subtask_results_rejected should be of type:  SubtaskResultsRejected",
            error_code=ErrorCode.MESSAGE_INVALID,
        )
    validate_task_to_compute(subtask_results_rejected.report_computed_task.task_to_compute)


def validate_subtask_price_task_to_compute(task_to_compute: message.tasks.TaskToCompute):
    if not isinstance(task_to_compute.price, int):
        raise Http400(
            "Price must be a integer",
            error_code=ErrorCode.MESSAGE_VALUE_NOT_INTEGER,
        )
    if task_to_compute.price < 0:
        raise Http400(
            "Price cannot be a negative value",
            error_code=ErrorCode.MESSAGE_VALUE_NEGATIVE,
        )


def validate_ethereum_addresses(requestor_ethereum_address, provider_ethereum_address):
    if not isinstance(requestor_ethereum_address, str):
        raise Http400(
            "Requestor's ethereum address must be a string",
            error_code=ErrorCode.MESSAGE_VALUE_NOT_STRING,
        )

    if not isinstance(provider_ethereum_address, str):
        raise Http400(
            "Provider's ethereum address must be a string",
            error_code=ErrorCode.MESSAGE_VALUE_NOT_STRING,
        )

    if not len(requestor_ethereum_address) == ETHEREUM_ADDRESS_LENGTH:
        raise Http400(
            f"Requestor's ethereum address must contains exactly {ETHEREUM_ADDRESS_LENGTH} characters ",
            error_code=ErrorCode.MESSAGE_VALUE_WRONG_LENGTH,
        )

    if not len(provider_ethereum_address) == ETHEREUM_ADDRESS_LENGTH:
        raise Http400(
            f"Provider's ethereum address must contains exactly {ETHEREUM_ADDRESS_LENGTH} characters ",
            error_code=ErrorCode.MESSAGE_VALUE_WRONG_LENGTH,
        )


def validate_list_task_to_compute_ids(subtask_results_accepted_list):
    subtask_ids = []
    for task_to_compute in subtask_results_accepted_list:
        subtask_ids.append(task_to_compute.subtask_id + ':' + task_to_compute.task_id)
    return len(subtask_ids) == len(set(subtask_ids))
