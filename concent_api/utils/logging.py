from logging                        import getLogger

from golem_messages.message import FileTransferToken
from golem_messages.message.base    import Message

from utils.helpers                  import get_field_from_message

logger = getLogger(__name__)


def replace_element_to_unavailable_instead_of_none(log_function):
    def wrap(*args, **kwargs):
        args_list = [arg if arg is not None else 'UNAVAILABLE' for arg in args]
        kwargs = {key: value if value is not None else 'UNAVAILABLE' for (key, value) in kwargs.items()}
        log_function(*args_list, **kwargs)
    return wrap


@replace_element_to_unavailable_instead_of_none
def log_message_received(message: Message, client_public_key: bytes):
    task_id = get_task_id_for_logging(message)
    subtask_id = get_subtask_id_for_logging(message)
    logger.info('A message has been received in `send/` -- MESSAGE_TYPE: {} -- TASK_ID: {} -- SUBTASK_ID: {} -- CLIENT PUBLIC KEY: {}'.format(
        type(message).__name__,
        task_id,
        subtask_id,
        client_public_key,
    ))
    logger.debug('A message has been received in `send/` -- MESSAGE: {}'.format(
        message,
    ))


@replace_element_to_unavailable_instead_of_none
def log_message_returned(message: Message, client_public_key: bytes):
    task_id = get_task_id_for_logging(message)
    subtask_id = get_subtask_id_for_logging(message)
    logger.info('A message has been returned from `send/` -- MESSAGE_TYPE: {} -- TASK_ID: {} -- SUBTASK_ID: {} -- CLIENT PUBLIC KEY: {}'.format(
        type(message).__name__,
        task_id,
        subtask_id,
        client_public_key,
    ))
    logger.debug('A message has been received in `send/` -- MESSAGE: {}'.format(
        message,
    ))


def log_message_accepted(message: Message, client_public_key: bytes):
    task_id = get_task_id_for_logging(message)
    subtask_id = get_subtask_id_for_logging(message)
    logger.info('The message has been accepted for further processing -- MESSAGE_TYPE: {} -- TASK_ID: {} -- SUBTASK_ID: {} -- CLIENT PUBLIC KEY: {}'.format(
        type(message).__name__,
        task_id,
        subtask_id,
        client_public_key,
    ))


def log_message_added_to_queue(message: Message, client_public_key: bytes):
    task_id = get_task_id_for_logging(message)
    subtask_id = get_subtask_id_for_logging(message)
    logger.info('A new message has been added to queue -- MESSAGE_TYPE: {} -- TASK_ID: {} -- SUBTASK_ID: {} -- CLIENT PUBLIC KEY: {}'.format(
        type(message).__name__,
        task_id,
        subtask_id,
        client_public_key,
    ))


def log_timeout(message: Message, client_public_key: bytes, deadline: int):
    task_id = get_task_id_for_logging(message)
    subtask_id = get_subtask_id_for_logging(message)
    logger.info('A deadline has been exceeded -- MESSAGE_TYPE: {} -- TASK_ID: {} -- SUBTASK_ID: {} -- CLIENT PUBLIC KEY: {} -- TIMEOUT: {}'.format(
        type(message).__name__,
        task_id,
        subtask_id,
        client_public_key,
        deadline,
    ))


@replace_element_to_unavailable_instead_of_none
def log_empty_queue(endpoint: str, client_public_key: bytes):
    logger.info('A message queue is empty in `{}()` -- CLIENT PUBLIC KEY: {}'.format(
        endpoint,
        client_public_key,
    ))


@replace_element_to_unavailable_instead_of_none
def log_400_error(endpoint: str, client_public_key: bytes, message: Message):
    if message is not None:
        task_id      = get_task_id_for_logging(message)
        subtask_id   = get_subtask_id_for_logging(message)
        message_type = type(message).__name__
    else:
        task_id      = 'not available'
        subtask_id   = 'not available'
        message_type = 'not available'
    logger.info("Error 400 has been returned from `{}()` -- MESSAGE_TYPE: {} -- TASK_ID: '{}' -- SUBTASK_ID: '{}' -- CLIENT PUBLIC KEY: {}".format(
        endpoint,
        message_type,
        task_id,
        subtask_id,
        client_public_key,
    ))


@replace_element_to_unavailable_instead_of_none
def log_message_not_allowed(endpoint: str, client_public_key: bytes, method: str):
    logger.info('Endpoint {} does not allow HTTP method {} -- CLIENT PUBLIC KEY: {}'.format(
        endpoint,
        method,
        client_public_key,
    ))


def log_subtask_stored(
    task_id:              str,
    subtask_id:           str,
    state:                str,
    provider_public_key:  bytes,
    requestor_public_key: bytes,
    next_deadline:        int          = None,
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
    task_id:              str,
    subtask_id:           str,
    state:                str,
    provider_public_key:  bytes,
    requestor_public_key: bytes,
    next_deadline:        int          = None,
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
    task_id:              str,
    subtask_id:           str,
    state:                str,
    stored_message:  Message,
):
    logger.info('A stored message has beed added to subtask -- STATE: {} TASK_ID: {} SUBTASK_ID: {} STORED_MESSAGE_TYPE: {} TYPE: {}'.format(
        state,
        task_id,
        subtask_id,
        stored_message.__name__,
        stored_message.TYPE,
    ))


def log_changes_in_subtask_states(client_public_key: bytes, count: int):
    assert isinstance(count, int)
    logger.info('{} {} state -- CLIENT PUBLIC KEY: {}'.format(
        count,
        "subtask changed its" if count == 1 else "subtasks changed their",
        client_public_key,
    ))


def log_change_subtask_state_name(old_state, new_state):
    logger.info('Subtask changed its state from {} to {}'.format(
        old_state,
        new_state,
    ))


def log_new_pending_response(response_type: str, queue_name: str, task_id: str, subtask_id: str, client_public_key: bytes):
    logger.info('New pending response in {} endpoint -- RESPONSE_TYPE: {} -- TASK_ID: {} -- SUBTASK_ID: {} -- CLIENT PUBLIC KEY: {}'.format(
        queue_name,
        response_type,
        task_id,
        subtask_id,
        client_public_key,
    ))


def log_receive_message_from_database(message: Message, client_public_key: bytes, response_type: str, queue_name: str):
    logger.info('Message {}, TYPE: {} has been received by {} endpoint -- RESPONSE_TYPE: {} -- CLIENT PUBLIC KEY: {}'.format(
        type(message).__name__,
        message.TYPE,
        queue_name,
        response_type,
        client_public_key,
    ))


def log_file_status(task_id: str, subtask_id: str, requestor_public_key: bytes, provider_public_key: bytes):
    logger.info('File assigned to TASK_ID: {} SUBTASK_ID: {} is already uploaded. -- REQUESTOR PUBLIC KEY: {} -- PROVIDER PUBLIC KEY {}'.format(
        task_id,
        subtask_id,
        requestor_public_key,
        provider_public_key,
    ))


def get_task_id_for_logging(message):
    task_id = get_field_from_message(message, 'task_id')
    if not isinstance(task_id, str):
        task_id = ''
    return task_id


def get_subtask_id_for_logging(message):
    subtask_id = get_field_from_message(message, 'subtask_id')
    if not isinstance(subtask_id, str):
        subtask_id = ''
    return subtask_id


def log_request_received(path_to_file, operation: FileTransferToken.Operation):
    logger.debug("{} request received. Path to file: '{}'".format(
        operation.capitalize(),
        path_to_file
    ))


@replace_element_to_unavailable_instead_of_none
def log_message_under_validation(
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
