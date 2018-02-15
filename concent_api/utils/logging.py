from logging                        import getLogger

from golem_messages.message.base    import Message

from utils.helpers                  import get_task_id_from_message


logger = getLogger(__name__)


def log_message_received(message: Message, client_public_key: str):
    logger.info('A message has been received in `send/` -- MESSAGE_TYPE: {} -- TASK_ID: {} -- CLIENT PUBLIC KEY: {}'.format(
        message.TYPE,
        get_task_id_from_message(message) or '',
        client_public_key,
    ))
    logger.debug('A message has been received in `send/` -- MESSAGE: {}'.format(
        message,
    ))


def log_message_returned(message: Message, client_public_key: str):
    logger.info('A message has been returned from `send/` -- MESSAGE_TYPE: {} -- TASK_ID: {} -- CLIENT PUBLIC KEY: {}'.format(
        message.TYPE,
        get_task_id_from_message(message) or '',
        client_public_key,
    ))
    logger.debug('A message has been received in `send/` -- MESSAGE: {}'.format(
        message,
    ))


def log_message_accepted(message: Message, client_public_key: str):
    logger.info('The message has been accepted for further processing -- MESSAGE_TYPE: {} -- TASK_ID: {} -- CLIENT PUBLIC KEY: {}'.format(
        message.TYPE,
        get_task_id_from_message(message) or '',
        client_public_key,
    ))


def log_message_added_to_queue():
    logger.info('A new message has been added to queue.')


def log_message_delivered():
    logger.info('A message in queue has been marked as delivered.')


def log_deadline_exceeded(message: Message, client_public_key: str, deadline: int):
    logger.info('A deadline has been exceeded -- MESSAGE_TYPE: {} -- TASK_ID: {} -- CLIENT PUBLIC KEY: {} -- DEADLINE: {}'.format(
        message.TYPE,
        get_task_id_from_message(message) or '',
        client_public_key,
        deadline,
    ))


def log_empty_queue(endpoint: str, client_public_key: str):
    logger.info('A message queue is empty in `{}/` -- CLIENT PUBLIC KEY: {}'.format(
        endpoint,
        client_public_key,
    ))


def log_400_error(endpoint: str, message: Message, client_public_key: str):
    logger.info('Error 4xx has been returned from `{}/` -- MESSAGE_TYPE: {} -- TASK_ID: {} -- CLIENT PUBLIC KEY: {}'.format(
        endpoint,
        message.TYPE,
        get_task_id_from_message(message) or '',
        client_public_key,
    ))
