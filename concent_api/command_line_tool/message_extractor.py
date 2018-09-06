from base64 import b64decode
import re
import random
import string
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import Sequence
from typing import Text
from typing import Union
import golem_messages.message as message_messages
import golem_messages.message.concents as message_concents
import golem_messages.message.tasks as message_tasks
from golem_messages.datastructures import FrozenDict as Task
from golem_messages.message import Message

DEFAULT_ID_STRING_LENGTH = 36
GENERATE_ID_CHARS = (string.ascii_letters + string.digits)

JsonType = Dict[Text, Any]


def make_random_string(length: Optional[int]=None, chars: Optional[Sequence[str]]=None) -> str:
    length = length if length is not None else DEFAULT_ID_STRING_LENGTH
    chars = chars if chars is not None else GENERATE_ID_CHARS
    return ''.join(random.choice(chars) for _ in range(length))


def split_uppercase(message: str) -> str:
    """change first letter of each word to lowercase and add underscore
    e.g. Input -> ForceComputedTask, Output -> force_computed_task
    """
    return (''.join([(word[:1].lower() + word[1:]) for word in re.sub(r'([A-Z])', r'_\1', message)]))[1:]


def find_modules() -> list:
    message_modules = [message_tasks, message_concents]
    message_list = []
    for module in message_modules:
        (message_list.extend([name for name, cls in module.__dict__.items() if isinstance(cls, type)]))
    return message_list


def get_field_names() -> list:
    """Makes a list of available messages from golem messages with name converted to snake case.
    """
    field_names = []
    for message in find_modules():
        field_names.append(split_uppercase(message))
    return field_names


FIELD_NAMES = get_field_names()


def create_message(message_name: str, message_params: JsonType) -> Union[Message, Task]:
    module = message_messages
    module = module if hasattr(module, convert_message_name(message_name)) else message_concents
    message = getattr(module, convert_message_name(message_name))(**message_params)
    return message


def substitute_message(json: JsonType, message_name: str, message: Message) -> JsonType:
    params = {k: v for k, v in json.items()}
    params[message_name] = message
    return params


def convert_message_name(message: str) -> str:
    """Remove underscore and change first letter of each word to uppercase
    e.g. Input -> force_computed_task, Output -> ForceComputedTask
    """
    return ''.join([(word[:1].capitalize() + word[1:]) for word in message.split('_')])


def _get_valid_message_name(messages: List[Text], json: JsonType) -> Optional[Text]:
    if len(messages) == 0:
        return None
    elif len(messages) == 1:
        return messages[0]
    else:
        names = []
        for message in messages:
            if json[message] is not None:
                names.append(message)
        if len(names) != 1:
            raise Exception("Invalid message definition")
        return names[0]


def generate_subtask_id(base_name: str) -> str:
    subtask_id = f'{base_name}_{random.randrange(1, 1000)}'
    return subtask_id


class MessageExtractor(object):
    def __init__(self, requestor_public_key: str, provider_public_key: str) -> None:
        self.messages = []  # type: List[Message]
        task_id = make_random_string(8)
        subtask_id = generate_subtask_id(task_id)
        requestor_id = make_random_string()
        self.data_replacement = {
            'provider_public_key': provider_public_key,
            'requestor_public_key': requestor_public_key,
            'task_id': task_id,
            'subtask_id': subtask_id,
            'requestor_id': requestor_id,
        }
        self.keys_list = [
            'requestor_public_key',
            'provider_public_key',
            'requestor_ethereum_public_key',
            'provider_ethereum_public_key',
        ]

    def extract_message(self, json: JsonType, name: str = None) -> Message:
        if name is None:
            return self._process_top_level(json)
        else:
            return self._process_body(json, name)

    def _process_top_level(self, json: JsonType) -> Union[Message, Task]:
        try:
            name = json['name']
            body = json['body']
        except KeyError:
            # TODO: throw an appropriate exception, maybe log sth
            raise
        return self.extract_message(body, name)

    def _process_body(self, json: JsonType, name: str) -> Message:
        def supplement_data(params: dict, supplement: dict, keys: list) -> dict:
            for k, v in params.items():
                if isinstance(v, dict):
                    supplement_data(v, supplement, keys)
                elif v == '' and k in supplement:
                    params[k] = supplement[k]
                elif k in keys:
                    params[k] = b64decode(params[k])
            return params

        message_list = [key for key in json.keys() if key in FIELD_NAMES]

        message_name = _get_valid_message_name(message_list, json)
        if message_name is not None:
            message = self._process_body(json[message_name], message_name)
            parameters = substitute_message(json, message_name, message)
            parameters = supplement_data(parameters, self.data_replacement, self.keys_list)
            return create_message(name, parameters)
        else:
            return create_message(name, json)
