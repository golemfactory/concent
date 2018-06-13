import json
from base64 import b64encode
from logging import Logger
from typing import Optional

from golem_messages.message import FileTransferToken
from golem_messages.message import TaskToCompute
from golem_messages.message.base import Message

from core.models import Subtask
from utils.constants import MessageIdField
from utils.helpers import get_field_from_message


def replace_element_to_unavailable_instead_of_none(log_function):
    def wrap(*args, **kwargs):
        args_list = [arg if arg is not None else '-not available-' for arg in args]
        kwargs = {key: value if value is not None else '-not available-' for (key, value) in kwargs.items()}
        log_function(*args_list, **kwargs)
    return wrap


@replace_element_to_unavailable_instead_of_none
def log_message_received(
    logger: Logger,
    message: Message,
    client_public_key: bytes
):
    task_id = _get_field_value_from_messages_for_logging(MessageIdField.TASK_ID, message)
    subtask_id = _get_field_value_from_messages_for_logging(MessageIdField.SUBTASK_ID, message)
    logger.info(
        f'A message has been received in `send/` -- MESSAGE_TYPE: {_get_message_type(message)} -- '
        f'TASK_ID: {task_id} -- '
        f'SUBTASK_ID: {subtask_id} -- '
        f'CLIENT PUBLIC KEY: {client_public_key}'
    )


@replace_element_to_unavailable_instead_of_none
def log_message_returned(
    logger: Logger,
    response_message: Message,
    client_public_key: bytes
):
    task_id = _get_field_value_from_messages_for_logging(MessageIdField.TASK_ID, response_message)
    subtask_id = _get_field_value_from_messages_for_logging(MessageIdField.SUBTASK_ID, response_message)

    logger.info(
        f"A message has been returned from `send/` -- MESSAGE_TYPE: {_get_message_type(response_message)} -- "
        f"TASK_ID: {task_id} -- "
        f"SUBTASK_ID: {subtask_id} -- "
        f"CLIENT PUBLIC KEY: {client_public_key}"
    )


@replace_element_to_unavailable_instead_of_none
def log_message_accepted(
    logger: Logger,
    message: Message,
    client_public_key: bytes
):
    task_id = _get_field_value_from_messages_for_logging(MessageIdField.TASK_ID, message)
    subtask_id = _get_field_value_from_messages_for_logging(MessageIdField.SUBTASK_ID, message)
    logger.info(
        f"Response from views. The message has been accepted for further processing -- MESSAGE_TYPE: {_get_message_type(message)} -- "
        f"TASK_ID: {task_id} -- "
        f"SUBTASK_ID: {subtask_id} -- "
        f"CLIENT PUBLIC KEY: {client_public_key}"
    )


@replace_element_to_unavailable_instead_of_none
def log_message_added_to_queue(
    logger: Logger,
    message: Message,
    client_public_key: bytes
):
    task_id = _get_field_value_from_messages_for_logging(MessageIdField.TASK_ID, message)
    subtask_id = _get_field_value_from_messages_for_logging(MessageIdField.SUBTASK_ID, message)
    logger.info(
        f"A new message has been added to queue -- MESSAGE_TYPE: {_get_message_type(message)} -- "
        f"TASK_ID: {task_id} -- "
        f"SUBTASK_ID: {subtask_id} -- "
        f"CLIENT PUBLIC KEY: {client_public_key}"
    )


@replace_element_to_unavailable_instead_of_none
def log_timeout(
    logger: Logger,
    message: Message,
    client_public_key: bytes,
    deadline: int
):
    task_id = _get_field_value_from_messages_for_logging(MessageIdField.TASK_ID, message)
    subtask_id = _get_field_value_from_messages_for_logging(MessageIdField.SUBTASK_ID, message)
    logger.info(
        f"A deadline has been exceeded -- MESSAGE_TYPE: {_get_message_type(message)} -- "
        f"TASK_ID: {task_id} -- "
        f"SUBTASK_ID: {subtask_id} -- "
        f"CLIENT PUBLIC KEY: {client_public_key} -- "
        f"TIMEOUT: {deadline}"
    )


@replace_element_to_unavailable_instead_of_none
def log_empty_queue(
    logger: Logger,
    endpoint: str,
    client_public_key: bytes
):
    logger.info(f"A message queue is empty in `{endpoint}()` -- CLIENT PUBLIC KEY: {client_public_key}")


@replace_element_to_unavailable_instead_of_none
def log_400_error(
    logger: Logger,
    endpoint: str,
    client_public_key: bytes,
    message: Message,
    error_code: str,
    error_message: str
):
    task_id = _get_field_value_from_messages_for_logging(MessageIdField.TASK_ID, message)
    subtask_id = _get_field_value_from_messages_for_logging(MessageIdField.SUBTASK_ID, message)
    logger.info(
        f"Error 400 has been returned from `{endpoint}()` -- "
        f"MESSAGE_TYPE: {_get_message_type(message)} -- "
        f"ERROR CODE: {error_code} -- "
        f"ERROR MESSAGE: {error_message} -- "
        f"TASK_ID: '{task_id}' -- "
        f"SUBTASK_ID: '{subtask_id}' -- "
        f"CLIENT PUBLIC KEY: {client_public_key}"
    )


@replace_element_to_unavailable_instead_of_none
def log_message_not_allowed(
    logger: Logger,
    endpoint: str,
    client_public_key: bytes,
    method: str
):
    logger.info(f"Endpoint {endpoint} does not allow HTTP method {method} -- CLIENT PUBLIC KEY: {client_public_key}")


@replace_element_to_unavailable_instead_of_none
def log_subtask_stored(
    logger: Logger,
    task_id: str,
    subtask_id: str,
    state: str,
    provider_public_key: bytes,
    requestor_public_key: bytes,
    next_deadline: Optional[int] = None,
):
    logger.info(
        f"A subtask has been stored -- STATE: {state} -- "
        f"NEXT_DEADLINE: {next_deadline} -- "
        f"TASK_ID: {task_id} -- "
        f"SUBTASK_ID: {subtask_id} -- "
        f"PROVIDER PUBLIC KEY: {provider_public_key} -- "
        f"REQUESTOR PUBLIC KEY: {requestor_public_key}"
    )


@replace_element_to_unavailable_instead_of_none
def log_subtask_updated(
    logger: Logger,
    task_id: str,
    subtask_id: str,
    state: str,
    provider_public_key: bytes,
    requestor_public_key: bytes,
    next_deadline:  Optional[int] = None,
):
    logger.info(
        f"A subtask has been updated -- STATE: {state} -- "
        f"NEXT_DEADLINE: {next_deadline} -- "
        f"TASK_ID: {task_id} -- "
        f"SUBTASK_ID: {subtask_id} -- "
        f"PROVIDER PUBLIC KEY: {provider_public_key} -- "
        f"REQUESTOR PUBLIC KEY: {requestor_public_key}"
    )


@replace_element_to_unavailable_instead_of_none
def log_stored_message_added_to_subtask(
    logger: Logger,
    task_id: str,
    subtask_id: str,
    state: str,
    stored_message:  Message,
    provider_public_key: bytes,
    requestor_public_key: bytes
):
    logger.info(
        f"A stored message has beed added to subtask -- STATE: {state} "
        f"TASK_ID: {task_id} "
        f"SUBTASK_ID: {subtask_id} "
        f"STORED_MESSAGE_TYPE: {_get_message_type(stored_message)} "
        f"TYPE: { stored_message.TYPE} PROVIDER PUBLIC KEY: {provider_public_key} "
        f"REQUESTOR PUBLIC KEY: {requestor_public_key}"
    )


def log_changes_in_subtask_states(
    logger: Logger,
    client_public_key: bytes,
    count: int
):
    assert isinstance(count, int)
    logger.info(
        f'{count} {"subtask changed its" if count == 1 else "subtasks changed their"} state -- '
        f'CLIENT PUBLIC KEY: {client_public_key}'
    )


def log_change_subtask_state_name(
    logger: Logger,
    old_state: str,
    new_state: str
):
    logger.info(f'Subtask changed its state from {old_state} to {new_state}')


def log_new_pending_response(
    logger: Logger,
    response_type: str,
    queue_name: str,
    subtask: Subtask
):
    task_id = subtask.task_id if subtask is not None else '-not available-'
    subtask_id = subtask.subtask_id if subtask is not None else '-not available-'
    provider_key = subtask.provider.public_key_bytes if subtask is not None else '-not available-'
    requestor_key = subtask.requestor.public_key_bytes if subtask is not None else '-not available-'
    logger.info(
        f'New pending response in {queue_name} endpoint RESPONSE_TYPE: {response_type} '
        f'TASK_ID: {task_id} '
        f'SUBTASK_ID: {subtask_id} '
        f'PROVIDER PUBLIC KEY: {provider_key} '
        f'REQUESTOR PUBLIC KEY {requestor_key}'
    )


@replace_element_to_unavailable_instead_of_none
def log_receive_message_from_database(
    logger: Logger,
    message: Message,
    client_public_key: bytes,
    response_type: str,
    queue_name: str
):
    task_id = _get_field_value_from_messages_for_logging(MessageIdField.TASK_ID, message)
    subtask_id = _get_field_value_from_messages_for_logging(MessageIdField.SUBTASK_ID, message)
    logger.info(
        f'Message {_get_message_type(message)}, TYPE: {message.TYPE} has been received by {queue_name} endpoint.'
        f' RESPONSE_TYPE: {response_type} '
        f'TASK_ID: {task_id} '
        f'SUBTASK_ID: {subtask_id} '
        f'CLIENT PUBLIC KEY: {client_public_key}'
    )


@replace_element_to_unavailable_instead_of_none
def log_file_status(
    logger: Logger,
    task_id: str,
    subtask_id: str,
    requestor_public_key: bytes,
    provider_public_key: bytes
):
    logger.info(
        f'File assigned to TASK_ID: {task_id} '
        f'SUBTASK_ID: {subtask_id} is already uploaded. -- '
        f'REQUESTOR PUBLIC KEY: {requestor_public_key} -- '
        f'PROVIDER PUBLIC KEY {provider_public_key}'
    )


def log_request_received(
    logger: Logger,
    path_to_file: str,
    operation: FileTransferToken.Operation
):
    logger.info(f"{operation.capitalize()} request received. Path to file: '{path_to_file}'")


@replace_element_to_unavailable_instead_of_none
def log_message_under_validation(
    logger: Logger,
    operation: FileTransferToken.Operation,
    message_type: str,
    file_path: str,
    subtask_id: bytes,
    public_key: bytes
):
    logger.info(
        f"{operation.capitalize()} request will be validated. Message type: '{message_type}'. "
        f"File: '{file_path}', with subtask_id '{subtask_id}'. Client public key: '{public_key}'"
    )


@replace_element_to_unavailable_instead_of_none
def log_message_successfully_validated(
    logger: Logger,
    operation: FileTransferToken.Operation,
    message_type: str,
    file_path: str,
    subtask_id: bytes,
    public_key: bytes
):
    logger.info(
        f"{operation.capitalize()} request passed all validations. Message type: '{message_type}'. "
        f"File: '{file_path}', with subtask_id '{subtask_id}'. Client public key: '{public_key}'"
    )


@replace_element_to_unavailable_instead_of_none
def log_operation_validation_failed(
    logger: Logger,
    operation: FileTransferToken.Operation,
    message: str,
    error_code: str,
    path: str,
    subtask_id: str,
    client_key: str
):
    logger.info(
        f"{operation.capitalize()} validation failed. Message: {message} Error code: '{error_code}'. "
        f"File '{path}', with subtask_id '{subtask_id}'. Client public key: '{client_key}'"
    )


@replace_element_to_unavailable_instead_of_none
def log_message_received_in_endpoint(
    logger,
    application_and_endpoint: str,
    message_type: str,
    client_public_key: bytes,
    content_type: str,
    task_id: str,
    subtask_id: str

):

    logger.info(
        f'A message has been received in `{application_and_endpoint}/`. '
        f'Message type: {message_type}. '
        f'TASK_ID: {task_id}. '
        f'SUBTASK_ID:{subtask_id}. '
        f'CLIENT_PUBLIC_KEY: {client_public_key}. '
        f'Content type: {content_type}. '
    )


def log_json_message(
    logger,
    message: json
):
    logger.info(message)


def log_string_message(
    logger,
    message: str
):
    logger.info(message)


def _get_field_value_from_messages_for_logging(
    field_name: MessageIdField,
    message: Message
) -> str:
    value = get_field_from_message(message, field_name.value) if isinstance(message, Message) else '-not available- '
    return value if value is not None else '-not available- '


def _get_message_type(
    message: Message
) -> str:
    return type(message).__name__ if isinstance(message, Message) else '-not available- '


def is_redundant_callable_or_golem_messages_field(golem_message, field_name):
    return False if isinstance(getattr(golem_message, field_name), Message) else callable(getattr(golem_message, field_name))


def get_json_from_message_without_redundant_fields_for_logging(
    golem_message: Message,
) -> json:

    dictionary_to_serialize = serialize_message_to_dictionary(golem_message)

    for field in dir(golem_message):
        if isinstance(getattr(golem_message, field), TaskToCompute):
            task_to_compute_dictionary = serialize_message_to_dictionary(getattr(golem_message, field))
            dictionary_to_serialize.update({field: task_to_compute_dictionary})

    return json.dumps(dictionary_to_serialize, indent=4)


def serialize_message_to_dictionary(
    golem_message: Message,
)->dict:

    fields_to_serialize = [f for f in dir(golem_message) if not f.startswith('_') and not f.isupper() and not is_redundant_callable_or_golem_messages_field(golem_message, f)]

    golem_messages_instances = []

    for field_name in fields_to_serialize:
        if isinstance(getattr(golem_message, field_name), TaskToCompute):
            fields_to_serialize.remove(field_name)

        elif isinstance(getattr(golem_message, field_name), Message):
            golem_messages_instances.append(getattr(golem_message, field_name))
            fields_to_serialize.remove(field_name)

    dict_to_serialize = {field_name: _get_field_value_and_encode_if_bytes_from_message(field_name, golem_message)
                         for field_name in fields_to_serialize}

    for attached_message in golem_messages_instances:
        new_dict = serialize_message_to_dictionary(attached_message)
        dict_to_serialize.update({attached_message.__class__.__name__: new_dict})

    return dict_to_serialize


def _get_field_value_and_encode_if_bytes_from_message(
    field_name: str,
    golem_message: Message
)->str:
    value = get_field_from_message(golem_message, field_name)

    if isinstance(value, bytes):
        value = b64encode(value)

    return str(value)
