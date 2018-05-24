from enum import Enum
from typing import Optional

from golem_messages.message import FileTransferToken
from golem_messages.message.base    import Message

from core.models import Subtask
from utils.helpers import get_field_from_message


class MessageFields(Enum):
    TASK_ID = 'task_id'
    SUBTASK_ID = 'subtask_id'


def replace_element_to_unavailable_instead_of_none(log_function):
    def wrap(*args, **kwargs):
        args_list = [arg if arg is not None else 'UNAVAILABLE' for arg in args]
        kwargs = {key: value if value is not None else 'UNAVAILABLE' for (key, value) in kwargs.items()}
        log_function(*args_list, **kwargs)
    return wrap


def log_message_returned(
    logger,
    response_message: Message,
    client_public_key: bytes
):
    task_id = _get_field_value_from_messages_for_logging(MessageFields.TASK_ID, response_message)
    subtask_id = _get_field_value_from_messages_for_logging(MessageFields.SUBTASK_ID, response_message)

    logger.info('A message has been returned from `send/` -- MESSAGE_TYPE: {} -- TASK_ID: {} -- SUBTASK_ID: {} -- CLIENT PUBLIC KEY: {}'.format(
        type(response_message).__name__,
        task_id,
        subtask_id,
        client_public_key if isinstance(client_public_key, bytes) else 'UNAVAILABLE',
    ))


def log_message_accepted(
    logger,
    message: Message,
    client_public_key: bytes
):
    task_id = _get_field_value_from_messages_for_logging(MessageFields.TASK_ID, message)
    subtask_id = _get_field_value_from_messages_for_logging(MessageFields.SUBTASK_ID, message)
    logger.info('The message has been accepted for further processing -- MESSAGE_TYPE: {} -- TASK_ID: {} -- SUBTASK_ID: {} -- CLIENT PUBLIC KEY: {}'.format(
        type(message).__name__,
        task_id,
        subtask_id,
        client_public_key,
    ))


def log_message_added_to_queue(
    logger,
    message: Message,
    client_public_key: bytes
):
    task_id = _get_field_value_from_messages_for_logging(MessageFields.TASK_ID, message)
    subtask_id = _get_field_value_from_messages_for_logging(MessageFields.SUBTASK_ID, message)
    logger.info('A new message has been added to queue -- MESSAGE_TYPE: {} -- TASK_ID: {} -- SUBTASK_ID: {} -- CLIENT PUBLIC KEY: {}'.format(
        type(message).__name__,
        task_id,
        subtask_id,
        client_public_key,
    ))


def log_timeout(
    logger,
    message: Message,
    client_public_key: bytes,
    deadline: int
):
    task_id = _get_field_value_from_messages_for_logging(MessageFields.TASK_ID, message)
    subtask_id = _get_field_value_from_messages_for_logging(MessageFields.SUBTASK_ID, message)
    logger.info('A deadline has been exceeded -- MESSAGE_TYPE: {} -- TASK_ID: {} -- SUBTASK_ID: {} -- CLIENT PUBLIC KEY: {} -- TIMEOUT: {}'.format(
        type(message).__name__,
        task_id,
        subtask_id,
        client_public_key,
        deadline,
    ))


@replace_element_to_unavailable_instead_of_none
def log_empty_queue(
    logger,
    endpoint: str,
    client_public_key: bytes
):
    logger.info('A message queue is empty in `{}()` -- CLIENT PUBLIC KEY: {}'.format(
        endpoint,
        client_public_key,
    ))


@replace_element_to_unavailable_instead_of_none
def log_400_error(
    logger,
    endpoint: str,
    client_public_key: bytes,
    message: Message
):
    task_id = _get_field_value_from_messages_for_logging(MessageFields.TASK_ID, message)
    subtask_id = _get_field_value_from_messages_for_logging(MessageFields.SUBTASK_ID, message)
    message_type = type(message).__name__
    logger.info("Error 400 has been returned from `{}()` -- MESSAGE_TYPE: {} -- TASK_ID: '{}' -- SUBTASK_ID: '{}' -- CLIENT PUBLIC KEY: {}".format(
        endpoint,
        message_type,
        task_id,
        subtask_id,
        client_public_key,
    ))


@replace_element_to_unavailable_instead_of_none
def log_message_not_allowed(
    logger,
    endpoint: str,
    client_public_key: bytes,
    method: str
):
    logger.info('Endpoint {} does not allow HTTP method {} -- CLIENT PUBLIC KEY: {}'.format(
        endpoint,
        method,
        client_public_key,
    ))


def log_subtask_stored(
    logger,
    task_id: str,
    subtask_id: str,
    state: str,
    provider_public_key: bytes,
    requestor_public_key: bytes,
    next_deadline:  Optional[int] = None,
):
    logger.info('A subtask has been stored -- STATE: {} -- NEXT_DEADLINE: {} -- TASK_ID: {} -- SUBTASK_ID: {} -- PROVIDER PUBLIC KEY: {} -- REQUESTOR PUBLIC KEY: {}'.format(
        state,
        next_deadline or '',
        task_id,
        subtask_id,
        provider_public_key,
        requestor_public_key,
    ))


def log_subtask_updated(
    logger,
    task_id: str,
    subtask_id: str,
    state: str,
    provider_public_key: bytes,
    requestor_public_key: bytes,
    next_deadline:  Optional[int] = None,
):
    logger.info('A subtask has been updated -- STATE: {} -- NEXT_DEADLINE: {} -- TASK_ID: {} -- SUBTASK_ID: {} -- PROVIDER PUBLIC KEY: {} -- REQUESTOR PUBLIC KEY: {}'.format(
        state,
        next_deadline if next_deadline is not None else '',
        task_id,
        subtask_id,
        provider_public_key,
        requestor_public_key,
    ))


def log_stored_message_added_to_subtask(
    logger,
    task_id: str,
    subtask_id: str,
    state: str,
    stored_message:  Message,
    provider_public_key: bytes,
    requestor_public_key: bytes
):
    logger.info('A stored message has beed added to subtask -- STATE: {} TASK_ID: {} SUBTASK_ID: {} STORED_MESSAGE_TYPE: {} TYPE: {} PROVIDER PUBLIC KEY: {} REQUESTOR PUBLIC KEY: {}'.format(
        state,
        task_id,
        subtask_id,
        stored_message.__name__,
        stored_message.TYPE,
        provider_public_key,
        requestor_public_key
    ))


def log_changes_in_subtask_states(
    logger,
    client_public_key: bytes,
    count: int
):
    assert isinstance(count, int)
    logger.info('{} {} state -- CLIENT PUBLIC KEY: {}'.format(
        count,
        "subtask changed its" if count == 1 else "subtasks changed their",
        client_public_key,
    ))


def log_change_subtask_state_name(
    logger,
    old_state,
    new_state
):
    logger.info('Subtask changed its state from {} to {}'.format(
        old_state,
        new_state,
    ))


def log_new_pending_response(
    logger,
    response_type: str,
    queue_name: str,
    subtask: Subtask
):
    logger.info('New pending response in {} endpoint RESPONSE_TYPE: {} TASK_ID: {} SUBTASK_ID: {} PROVIDER PUBLIC KEY: {} REQUESTOR PUBLIC KEY {}'.format(
        queue_name,
        response_type,
        subtask.task_id if subtask is not None else 'UNAVAILABLE',
        subtask.subtask_id if subtask is not None else 'UNAVAILABLE',
        subtask.provider.public_key_bytes if subtask is not None else 'UNAVAILABLE',
        subtask.requestor.public_key_bytes if subtask is not None else 'UNAVAILABLE',
    ))


@replace_element_to_unavailable_instead_of_none
def log_receive_message_from_database(
    logger,
    message: Message,
    client_public_key: bytes,
    response_type: str,
    queue_name: str
):
    logger.info('Message {}, TYPE: {} has been received by {} endpoint. RESPONSE_TYPE: {} TASK_ID: {} SUBTASK_ID: {} CLIENT PUBLIC KEY: {}'.format(
        type(message).__name__,
        message.TYPE,
        queue_name,
        response_type,
        _get_field_value_from_messages_for_logging(MessageFields.TASK_ID, message),
        _get_field_value_from_messages_for_logging(MessageFields.SUBTASK_ID, message),
        client_public_key,
    ))


def log_file_status(
    logger,
    task_id: str,
    subtask_id: str,
    requestor_public_key: bytes,
    provider_public_key: bytes
):

    if (task_id or subtask_id or requestor_public_key or provider_public_key) is None:
        raise Exception
    logger.info('File assigned to TASK_ID: {} SUBTASK_ID: {} is already uploaded. -- REQUESTOR PUBLIC KEY: {} -- PROVIDER PUBLIC KEY {}'.format(
        task_id,
        subtask_id,
        requestor_public_key,
        provider_public_key,
    ))


def log_request_received(
    logger,
    path_to_file,
    operation: FileTransferToken.Operation
):
    logger.debug("{} request received. Path to file: '{}'".format(
        operation.capitalize(),
        path_to_file
    ))


@replace_element_to_unavailable_instead_of_none
def log_message_under_validation(
    logger,
    operation: FileTransferToken.Operation,
    message_type: str,
    file_path: str,
    subtask_id: bytes,
    public_key: bytes
):

    logger.debug("{} request will be validated. Message type: '{}'. File: '{}', with subtask_id '{}'. Client public key: '{}'".format(
        operation.capitalize(),
        message_type,
        file_path,
        subtask_id,
        public_key
    ))


@replace_element_to_unavailable_instead_of_none
def log_message_successfully_validated(
    logger,
    operation: FileTransferToken.Operation,
    message_type: str,
    file_path: str,
    subtask_id: bytes,
    public_key: bytes
):
    logger.info("{} request passed all validations.  Message type: '{}'. File: '{}', with subtask_id '{}'. Client public key: '{}'".format(
        operation.capitalize(),
        message_type,
        file_path,
        subtask_id,
        public_key
    ))


@replace_element_to_unavailable_instead_of_none
def log_operation_validation_failed(
    logger,
    operation: FileTransferToken.Operation,
    message: str,
    error_code: str,
    path: str,
    subtask_id: str,
    client_key: str
):
    logger.info("{} validation failed. Message: {} Error code: '{}'. File '{}', with subtask_id '{}'. Client public key: '{}'".format(
        operation.capitalize(),
        message,
        error_code,
        path,
        subtask_id,
        client_key
    ))


def _get_field_value_from_messages_for_logging(
    field_name: MessageFields,
    message: Message
)->str:
    return get_field_from_message(message, field_name.value) if message is not None else 'UNAVAILABLE'
