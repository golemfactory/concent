from base64 import b64decode
import importlib
import re
import random
import string
from typing import Dict, Text, Any, List, Union
from golem_messages.datastructures import FrozenDict
from golem_messages.message import Message

JsonType = Dict[Text, Any]
Task = FrozenDict


def make_random_string(length=None, chars=None):
    length = length if length is not None else 36
    chars = chars if chars is not None else (string.ascii_letters + string.digits)

    return ''.join(random.choice(chars) for _ in range(length))


def split_uppercase(message):
    return (''.join([(word[:1].lower() + word[1:]) for word in re.sub(r'([A-Z])', r'_\1', message)]))[1:]


def find_modules():
    message_tasks = importlib.import_module("golem_messages.message.tasks")
    message_concents = importlib.import_module("golem_messages.message.concents")
    message_modules = [message_tasks, message_concents]
    message_list = []
    for module in message_modules:
        (message_list.extend([name for name, cls in module.__dict__.items() if isinstance(cls, type)]))
    return message_list


def get_field_names():
    field_names = []
    for message in find_modules():
        field_names.append(split_uppercase(message))
    return field_names


FIELD_NAMES = get_field_names()


def validate_message_list(message_list: List[Message]) -> None:
    if len(message_list) > 1:
        raise ValueError("Malformed message definition")


def create_message(message_name: str, message_params: JsonType) -> Union[Message, Task]:
    module = importlib.import_module("golem_messages.message")
    module = module if hasattr(module, convert_message_name(message_name)) else importlib.import_module(
        "golem_messages.message.concents")
    message = getattr(module, convert_message_name(message_name))(**message_params)
    return message


def substitute_message(json: JsonType, message_name: str, message: Message) -> JsonType:
    params = {k: v for k, v in json.items()}
    params[message_name] = message
    return params


def convert_message_name(message):
    return ''.join([(word[:1].capitalize() + word[1:]) for word in message.split('_')])


def _contains_valid_message(messages: List[Text]) -> bool:
    return len(messages) == 1


class MessageExtractor(object):
    def __init__(self, requestor_public_key, provider_public_key):
        self.messages = []  # type: List[Message]
        task_id = make_random_string(8)
        subtask_id = task_id + '_' + str(random.randrange(1, 100))
        requestor_id = make_random_string()
        self.data_replacement = {'provider_public_key': provider_public_key,
                                 'requestor_public_key': requestor_public_key,
                                 'task_id': task_id,
                                 'subtask_id': subtask_id,
                                 'requestor_id': requestor_id,
                                 }
        self.keys_list = ['requestor_public_key', 'provider_public_key', 'requestor_ethereum_public_key',
                          'provider_ethereum_public_key']

    def extract_message(self, json: JsonType, name: str = None) -> Message:
        if name is None:
            return self._process_top_level(json)
        else:
            return self._process_body(json, name)

    def _process_top_level(self, json):
        try:
            name = json['name']
            body = json['body']
        except KeyError:
            # TODO: throw an appropriate exception, maybe log sth
            raise
        return self.extract_message(body, name)

    def _process_body(self, json: JsonType, name: str) -> Message:
        def supplement_data(params, supplement, keys):
            for k, v in params.items():
                if isinstance(v, dict):
                    supplement_data(v, supplement, keys)
                elif v == '' and k in supplement:
                    params[k] = supplement[k]
                elif k in keys:
                    params[k] = b64decode(params[k])
            return params

        message_list = [key for key in json.keys() if key in FIELD_NAMES]

        if _contains_valid_message(message_list):
            message_name = message_list[0]
            message = self._process_body(json[message_name], message_name)
            parameters = substitute_message(json, message_name, message)
            parameters = supplement_data(parameters, self.data_replacement, self.keys_list)
            return create_message(name, parameters)
        else:
            return create_message(name, json)
