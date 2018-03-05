from logging                        import getLogger

from golem_messages.message.base    import Message

from utils.helpers                  import get_field_from_message


logger = getLogger(__name__)


def log_message_received(message: Message, client_public_key: str):
    task_id = get_task_id_for_logging(message)
    subtask_id = get_subtask_id_for_logging(message)
    logger.info('A message has been received in `send/` -- MESSAGE_TYPE: {} -- TASK_ID: {} -- SUBTASK_ID: {} -- CLIENT PUBLIC KEY: {}'.format(
        message.TYPE,
        task_id,
        subtask_id,
        client_public_key,
    ))
    logger.debug('A message has been received in `send/` -- MESSAGE: {}'.format(
        message,
    ))


def log_message_returned(message: Message, client_public_key: str):
    task_id = get_task_id_for_logging(message)
    subtask_id = get_subtask_id_for_logging(message)
    logger.info('A message has been returned from `send/` -- MESSAGE_TYPE: {} -- TASK_ID: {} -- SUBTASK_ID: {} -- CLIENT PUBLIC KEY: {}'.format(
        message.TYPE,
        task_id,
        subtask_id,
        client_public_key,
    ))
    logger.debug('A message has been received in `send/` -- MESSAGE: {}'.format(
        message,
    ))


def log_message_accepted(message: Message, client_public_key: str):
    task_id = get_task_id_for_logging(message)
    subtask_id = get_subtask_id_for_logging(message)
    logger.info('The message has been accepted for further processing -- MESSAGE_TYPE: {} -- TASK_ID: {} -- SUBTASK_ID: {} -- CLIENT PUBLIC KEY: {}'.format(
        message.TYPE,
        task_id,
        subtask_id,
        client_public_key,
    ))


def log_message_added_to_queue(message: Message, client_public_key: str):
    task_id = get_task_id_for_logging(message)
    subtask_id = get_subtask_id_for_logging(message)
    logger.info('A new message has been added to queue -- MESSAGE_TYPE: {} -- TASK_ID: {} -- SUBTASK_ID: {} -- CLIENT PUBLIC KEY: {}'.format(
        message.TYPE,
        task_id,
        subtask_id,
        client_public_key,
    ))


def log_message_delivered(message: Message, client_public_key: str):
    task_id = get_task_id_for_logging(message)
    subtask_id = get_subtask_id_for_logging(message)
    logger.info('A message in queue has been marked as delivered -- MESSAGE_TYPE: {} -- TASK_ID: {} -- SUBTASK_ID: {} -- CLIENT PUBLIC KEY: {}'.format(
        message.TYPE,
        task_id,
        subtask_id,
        client_public_key,
    ))


def log_timeout(message: Message, client_public_key: str, deadline: int):
    task_id = get_task_id_for_logging(message)
    subtask_id = get_subtask_id_for_logging(message)
    logger.info('A deadline has been exceeded -- MESSAGE_TYPE: {} -- TASK_ID: {} -- SUBTASK_ID: {} -- CLIENT PUBLIC KEY: {} -- TIMEOUT: {}'.format(
        message.TYPE,
        task_id,
        subtask_id,
        client_public_key,
        deadline,
    ))


def log_empty_queue(endpoint: str, client_public_key: str):
    logger.info('A message queue is empty in `{}()` -- CLIENT PUBLIC KEY: {}'.format(
        endpoint,
        client_public_key,
    ))


def log_400_error(endpoint: str, message: Message, client_public_key: str):
    task_id = get_task_id_for_logging(message)
    subtask_id = get_subtask_id_for_logging(message)
    logger.info('Error 4xx has been returned from `{}()` -- MESSAGE_TYPE: {} -- TASK_ID: {} -- SUBTASK_ID: {} -- CLIENT PUBLIC KEY: {}'.format(
        endpoint,
        message.TYPE,
        task_id,
        subtask_id,
        client_public_key,
    ))


def log_subtask_stored(
    task_id:              str,
    subtask_id:           str,
    state:                str,
    provider_public_key:  str,
    requestor_public_key: str,
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
    provider_public_key:  str,
    requestor_public_key: str,
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
    subtask_id:           str,
    state:                str,
    stored_message_type:  int,
):
    logger.info('A stored message has beed added to subtask -- STATE: {} SUBTASK_ID: {} STORED_MESSAGE_TYPE: {}'.format(
        state,
        subtask_id,
        stored_message_type,
    ))


def log_no_changes_in_subtask_states(client_public_key: bytes):
    logger.info('None of subtask changed state -- CLIENT PUBLIC KEY: {}'.format(
        client_public_key,
    ))


def log_changes_in_subtask_states(client_public_key: bytes, count: int):
    assert count >= 1
    logger.info('{} {} state -- CLIENT PUBLIC KEY: {}'.format(
        count,
        "subtasks changed their" if count >= 2 else "subtask changed its",
        client_public_key,
    ))


def log_change_subtask_state_name(old_state, new_state):
    logger.info('Subtask changed its state from {} to {}'.format(
        old_state,
        new_state,
    ))


def log_new_pending_response(response_type: str, queue_name: str, subtask_id: str, client_public_key: str):
    logger.info('New pending response in {} endpoint -- RESPONSE_TYPE: {} -- SUBTASK_ID: {} -- CLIENT PUBLIC KEY: {}'.format(
        queue_name,
        response_type,
        subtask_id,
        client_public_key,
    ))


def log_receive_message_from_database(message: Message, client_public_key: str, response_type: str, queue_name: str):
    logger.info('Message {}, TYPE: {} has been received by {} endpoint -- RESPONSE_TYPE: {} -- CLIENT PUBLIC KEY: {}'.format(
        message.__class__.__name__,
        message.TYPE,
        queue_name,
        response_type,
        client_public_key,
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
