from logging                        import getLogger

from golem_messages.message.base    import Message

from utils.helpers                  import get_task_id_from_message


logger = getLogger(__name__)


def log_message_received(message: Message, client_public_key: str):
    task_id = get_task_id_for_logging(message)
    logger.info('A message has been received in `send/` -- MESSAGE_TYPE: {} -- TASK_ID: {} -- CLIENT PUBLIC KEY: {}'.format(
        message.TYPE,
        task_id,
        client_public_key,
    ))
    logger.debug('A message has been received in `send/` -- MESSAGE: {}'.format(
        message,
    ))


def log_message_returned(message: Message, client_public_key: str):
    task_id = get_task_id_for_logging(message)
    logger.info('A message has been returned from `send/` -- MESSAGE_TYPE: {} -- TASK_ID: {} -- CLIENT PUBLIC KEY: {}'.format(
        message.TYPE,
        task_id,
        client_public_key,
    ))
    logger.debug('A message has been received in `send/` -- MESSAGE: {}'.format(
        message,
    ))


def log_message_accepted(message: Message, client_public_key: str):
    task_id = get_task_id_for_logging(message)
    logger.info('The message has been accepted for further processing -- MESSAGE_TYPE: {} -- TASK_ID: {} -- CLIENT PUBLIC KEY: {}'.format(
        message.TYPE,
        task_id,
        client_public_key,
    ))


def log_message_added_to_queue(message: Message, client_public_key: str):
    task_id = get_task_id_for_logging(message)
    logger.info('A new message has been added to queue -- MESSAGE_TYPE: {} -- TASK_ID: {} -- CLIENT PUBLIC KEY: {}'.format(
        message.TYPE,
        task_id,
        client_public_key,
    ))


def log_message_delivered(message: Message, client_public_key: str):
    task_id = get_task_id_for_logging(message)
    logger.info('A message in queue has been marked as delivered -- MESSAGE_TYPE: {} -- TASK_ID: {} -- CLIENT PUBLIC KEY: {}'.format(
        message.TYPE,
        task_id,
        client_public_key,
    ))


def log_timeout(message: Message, client_public_key: str, deadline: int):
    task_id = get_task_id_for_logging(message)
    logger.info('A deadline has been exceeded -- MESSAGE_TYPE: {} -- TASK_ID: {} -- CLIENT PUBLIC KEY: {} -- TIMEOUT: {}'.format(
        message.TYPE,
        task_id,
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
    logger.info('Error 4xx has been returned from `{}()` -- MESSAGE_TYPE: {} -- TASK_ID: {} -- CLIENT PUBLIC KEY: {}'.format(
        endpoint,
        message.TYPE,
        task_id,
        client_public_key,
    ))


def get_task_id_for_logging(message):
    task_id = get_task_id_from_message(message)
    if not isinstance(task_id, str):
        task_id = ''
    return task_id
