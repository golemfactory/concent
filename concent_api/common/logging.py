import json
from base64 import b64decode
from enum import Enum
from logging import Logger
from typing import Any
from typing import Callable
from typing import Dict
from typing import List
from typing import Optional
from typing import Union

from django.http import JsonResponse
from golem_messages.message.base import AbstractReasonMessage
from golem_messages.message.base import Message
from golem_messages.message.concents import FileTransferToken
from golem_messages.message.concents import ForcePayment
from golem_messages.message.tasks import SubtaskResultsAccepted
from golem_messages.utils import encode_hex

from common.constants import MessageIdField
from common.helpers import get_field_from_message
from common.helpers import join_messages

MessageAsDict = Dict[str, Union[str, Dict[str, Any]]]


class LoggingLevel(Enum):
    INFO = 'info'
    EXCEPTION = 'exception'
    WARNING = 'warning'
    ERROR = 'error'


def replace_element_to_unavailable_instead_of_none(log_function: Callable) -> Callable:
    def wrap(*args: Any, **kwargs: Any) -> None:
        args_list = [arg if arg is not None else '-not available-' for arg in args]
        kwargs = {key: value if value is not None else '-not available-' for (key, value) in kwargs.items()}
        log_function(*args_list, **kwargs)
    return wrap


@replace_element_to_unavailable_instead_of_none
def log_message_received(logger: Logger, message: Message, client_public_key: bytes) -> None:
    task_id = _get_field_value_from_messages_for_logging(MessageIdField.TASK_ID, message)
    subtask_id: str = _get_field_value_from_messages_for_logging(MessageIdField.SUBTASK_ID, message)
    log(
        logger,
        f'A message has been received in `send/` -- MESSAGE_TYPE: {_get_message_type(message)} -- TASK_ID: {task_id} -- ',
        subtask_id=subtask_id,
        client_public_key=client_public_key
    )


@replace_element_to_unavailable_instead_of_none
def log_message_returned(
    logger: Logger,
    response_message: Message,
    client_public_key: bytes,
    endpoint: str
) -> None:
    task_id = _get_field_value_from_messages_for_logging(MessageIdField.TASK_ID, response_message)
    subtask_id = _get_field_value_from_messages_for_logging(MessageIdField.SUBTASK_ID, response_message)
    reason = ""
    if isinstance(response_message, AbstractReasonMessage):
        reason = f"(with reason: {response_message.reason}) "
    message_to_log = f'A message has been returned from `{endpoint}` ' \
        f'-- MESSAGE_TYPE: {_get_message_type(response_message)} {reason}' \
        f'-- TASK_ID: {task_id} -- '

    log(
        logger,
        message_to_log,
        subtask_id=subtask_id,
        client_public_key=client_public_key
    )


@replace_element_to_unavailable_instead_of_none
def log_message_accepted(logger: Logger, message: Message, client_public_key: bytes) -> None:
    task_id = _get_field_value_from_messages_for_logging(MessageIdField.TASK_ID, message)
    subtask_id = _get_field_value_from_messages_for_logging(MessageIdField.SUBTASK_ID, message)
    log(
        logger,
        f'Response from views. The message has been accepted for further processing -- MESSAGE_TYPE: {_get_message_type(message)} -- TASK_ID: {task_id} -- ',
        subtask_id=subtask_id,
        client_public_key=client_public_key
    )


@replace_element_to_unavailable_instead_of_none
def log_message_added_to_queue(logger: Logger, message: Message, client_public_key: bytes) -> None:
    task_id = _get_field_value_from_messages_for_logging(MessageIdField.TASK_ID, message)
    subtask_id = _get_field_value_from_messages_for_logging(MessageIdField.SUBTASK_ID, message)
    log(
        logger,
        f'A new message has been added to queue -- MESSAGE_TYPE: {_get_message_type(message)} -- TASK_ID: {task_id} -- ',
        subtask_id=subtask_id,
        client_public_key=client_public_key
    )


@replace_element_to_unavailable_instead_of_none
def log_timeout(
    logger: Logger,
    message: Message,
    client_public_key: bytes,
    deadline: int
) -> None:
    task_id = _get_field_value_from_messages_for_logging(MessageIdField.TASK_ID, message)
    subtask_id = _get_field_value_from_messages_for_logging(MessageIdField.SUBTASK_ID, message)

    log(
        logger,
        f'A deadline has been exceeded -- MESSAGE_TYPE: {_get_message_type(message)} --TASK_ID: {task_id} -- TIMEOUT: {deadline}',
        subtask_id=subtask_id,
        client_public_key=client_public_key
    )


@replace_element_to_unavailable_instead_of_none
def log_400_error(
    logger: Logger,
    endpoint: str,
    client_public_key: bytes,
    message: Message,
    error_code: str,
    error_message: str
) -> None:
    task_id = _get_field_value_from_messages_for_logging(MessageIdField.TASK_ID, message)
    subtask_id = _get_field_value_from_messages_for_logging(MessageIdField.SUBTASK_ID, message)
    log(
        logger,
        f"Error 400 has been returned from `{endpoint}()` -- MESSAGE_TYPE: {_get_message_type(message)} -- "
        f"ERROR CODE: {error_code} -- ERROR MESSAGE: {error_message} -- TASK_ID: '{task_id}' --",
        subtask_id=subtask_id,
        client_public_key=client_public_key
    )


@replace_element_to_unavailable_instead_of_none
def log_subtask_stored(
    logger: Logger,
    task_id: str,
    subtask_id: str,
    state: str,
    provider_public_key: bytes,
    requestor_public_key: bytes,
    computation_deadline: int,
    result_package_size: int,
    next_deadline: Optional[int] = None,
) -> None:
    log(
        logger,
        f"A subtask has been stored -- STATE: {state} -- "
        f"NEXT_DEADLINE: {next_deadline} -- "
        f"TASK_ID: {task_id} -- "
        f"PROVIDER PUBLIC KEY: {convert_public_key_to_hex(provider_public_key)} "
        f"REQUESTOR PUBLIC KEY: {convert_public_key_to_hex(requestor_public_key)} "
        f"RESULT_PACKAGE_SIZE: {result_package_size} -- "
        f"COMPUTATION_DEADLINE: {computation_deadline} --",
        subtask_id=subtask_id,
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
) -> None:
    log(
        logger,
        f"A subtask has been updated -- STATE: {state} -- "
        f"NEXT_DEADLINE: {next_deadline} -- "
        f"TASK_ID: {task_id} -- "
        f"PROVIDER PUBLIC KEY: {convert_public_key_to_hex(provider_public_key)} "
        f"REQUESTOR PUBLIC KEY: {convert_public_key_to_hex(requestor_public_key)}",
        subtask_id=subtask_id,
    )


@replace_element_to_unavailable_instead_of_none
def log_stored_message_added_to_subtask(
    logger: Logger,
    task_id: str,
    subtask_id: str,
    state: str,
    stored_message:  Message,
    provider_id: str,
    requestor_id: str
) -> None:
    log(
        logger,
        f"A stored message has beed added to subtask -- STATE: {state} "
        f"TASK_ID: {task_id} "
        f"STORED_MESSAGE_TYPE: {_get_message_type(stored_message)} "
        f"PROVIDER PUBLIC KEY: {provider_id} "
        f"REQUESTOR PUBLIC KEY: {requestor_id}",
        subtask_id=subtask_id,
    )


def log_new_pending_response(
    logger: Logger,
    response_type: str,
    queue_name: str,
    subtask: Optional['Subtask']=None,  # type: ignore
) -> None:
    task_id = subtask.task_id if subtask is not None else '-not available-'
    subtask_id = subtask.subtask_id if subtask is not None else '-not available-'
    provider_key = subtask.provider.public_key if subtask is not None else '-not available-'
    requestor_key = subtask.requestor.public_key if subtask is not None else '-not available-'
    log(
        logger,
        f'New pending response in {queue_name} endpoint RESPONSE_TYPE: {response_type} '
        f'TASK_ID: {task_id} '
        f'PROVIDER PUBLIC KEY: {convert_public_key_to_hex(provider_key)} '
        f'REQUESTOR PUBLIC KEY {convert_public_key_to_hex(requestor_key)}',
        subtask_id=subtask_id,
    )


@replace_element_to_unavailable_instead_of_none
def log_receive_message_from_database(
    logger: Logger,
    message: Message,
    client_public_key: bytes,
    response_type: str,
    queue_name: str
) -> None:
    task_id = _get_field_value_from_messages_for_logging(MessageIdField.TASK_ID, message)
    subtask_id = _get_field_value_from_messages_for_logging(MessageIdField.SUBTASK_ID, message)
    log(
        logger,
        f'Message {_get_message_type(message)}, TYPE: {message.header.type_} has been received by {queue_name} endpoint.'
        f' RESPONSE_TYPE: {response_type} '
        f'TASK_ID: {task_id} ',
        subtask_id=subtask_id,
        client_public_key=client_public_key
    )


def log_request_received(logger: Logger, path_to_file: str, operation: FileTransferToken.Operation) -> None:
    log(logger, f"{operation.capitalize()} request received. Path to file: '{path_to_file}'")


def log(
    logger: Logger,
    *messages_to_log: str,
    subtask_id: Optional[str] = None,
    client_public_key: Union[bytes, str, None] = None,
    logging_level: Optional[LoggingLevel] = LoggingLevel.INFO
) -> None:
    client_key_message = f'CLIENT_PUBLIC_KEY: {convert_public_key_to_hex(client_public_key)}. ' if client_public_key is not None else ''
    subtask_id_message = f'SUBTASK_ID: {subtask_id}. ' if subtask_id is not None else ''
    if isinstance(logging_level, LoggingLevel) and logging_level == logging_level.INFO:
        logger.info(f'{subtask_id_message}{client_key_message}{join_messages(*messages_to_log)}')
    elif isinstance(logging_level, LoggingLevel) and logging_level == logging_level.EXCEPTION:
        logger.exception(f'{subtask_id_message}{client_key_message}{join_messages(*messages_to_log)}')
    elif isinstance(logging_level, LoggingLevel) and logging_level == logging_level.WARNING:
        logger.warning(f'{subtask_id_message}{client_key_message}{join_messages(*messages_to_log)}')
    elif isinstance(logging_level, LoggingLevel) and logging_level == logging_level.ERROR:
        logger.error(f'{subtask_id_message}{client_key_message}{join_messages(*messages_to_log)}')
    else:
        raise TypeError('Unexpected logging level')


def log_received_force_payment(
    logger: Logger,
    force_payment_message: ForcePayment,
) -> None:
    log(logger, f"ForcePayment received with {len(force_payment_message.subtask_results_accepted_list)} nested SubtaskResultsAccepted messages:")
    for i, subtask_results_accepted in enumerate(force_payment_message.subtask_results_accepted_list):
        log(
            logger,
            f" -> {i}. SubtaskResultsAccepted with SUBTASK_ID: {subtask_results_accepted.subtask_id},"
            f" payment timestamp: {subtask_results_accepted.payment_ts},"
            f" price: {subtask_results_accepted.task_to_compute.price}."
        )


def log_different_keys_addresses_and_wrong_requestor_signature(
    logger: Logger,
    subtask_results_accepted_list: List[SubtaskResultsAccepted],
) -> None:
    for subtask_results_accepted in subtask_results_accepted_list:
        log(
            logger,
            f"Keys and addresses are not unique within subtask_results_accepted_list ",
            f"or SubtaskResultsAccepted messages are not signed by the same requestor",
            subtask_id=subtask_results_accepted.subtask_id)


def log_duplicate_subtask_results_accepted(
    logger: Logger,
    duplicated_subtask_ids: List[str],
) -> None:
    log(logger, f"Subtask_ids in subtask_results_accepted_list are duplicated: {duplicated_subtask_ids}")


def log_lack_of_unsettled_task(
    logger: Logger,
) -> None:
    log(logger, f"Lack of unsettled payments.")


def _get_field_value_from_messages_for_logging(field_name: MessageIdField, message: Message) -> str:
    value: str = get_field_from_message(message, field_name.value) if isinstance(message, Message) else '-not available-'  # type: ignore
    return value if value is not None else '-not available-'


def _get_message_type(message: Message) -> str:
    return type(message).__name__ if isinstance(message, Message) else '-not available-'


def get_json_from_message_without_redundant_fields_for_logging(golem_message: Message) -> JsonResponse:
    dictionary_to_serialize = serialize_message_to_dictionary(golem_message)
    return json.dumps(dictionary_to_serialize, indent=4)


def serialize_message_to_dictionary(golem_message: Message) -> MessageAsDict:
    fields_to_serialize = [f for f in golem_message.__slots__]

    golem_messages_instances = []

    for field_name in fields_to_serialize:
        if isinstance(getattr(golem_message, field_name), Message):
            golem_messages_instances.append(getattr(golem_message, field_name))
            fields_to_serialize.remove(field_name)

    dict_to_serialize: MessageAsDict = {field_name: _get_field_value_and_encode_if_bytes_from_message(field_name, golem_message)
                         for field_name in fields_to_serialize}

    for attached_message in golem_messages_instances:
        new_dict = serialize_message_to_dictionary(attached_message)
        dict_to_serialize.update({attached_message.__class__.__name__: new_dict})

    return dict_to_serialize


def _get_field_value_and_encode_if_bytes_from_message(field_name: str, golem_message: Message) -> str:
    value = get_field_from_message(golem_message, field_name)
    if isinstance(value, bytes):
        value = encode_hex(value)
    return str(value)


def convert_public_key_to_hex(client_key: Union[bytes, str, None]) -> str:
    if client_key is None:
        decoded_key = '-not available-'
    elif isinstance(client_key, bytes):
        decoded_key = encode_hex(client_key)
    elif isinstance(client_key, str):
        if client_key == '-not available-':
            decoded_key = client_key
        elif len(client_key) == 88:
            decoded_key = encode_hex(b64decode(client_key))
        elif len(client_key) == 128:
            decoded_key = client_key
        else:
            raise TypeError(f'Cannot convert client key given as string to hex. Client key: {client_key}')
    else:
        raise TypeError(f'Unsupported type of client public key.  Client key: {client_key}.  Type of client key: {type(client_key)}')

    assert len(decoded_key) == 128 or decoded_key == '-not available-'
    return decoded_key


def log_payment_time_exceeded(
    logger: Logger,
    subtask_results_accepted_list: List[SubtaskResultsAccepted],
) -> None:
    for subtask_results_accepted in subtask_results_accepted_list:
        log(
            logger,
            f"SubtaskResultsAccepted with SUBTASK_ID: {subtask_results_accepted.subtask_id} time exceeded.",
            f" payment timestamp: {subtask_results_accepted.payment_ts}",
            f" price: {subtask_results_accepted.task_to_compute.price}",
        )
