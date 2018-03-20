import importlib
import types
import re
from typing import Dict, Text, Any, List
from golem_messages.message import Message
from inspect import getmembers, ismodule, isclass

JsonType = Dict[Text, Any]

FIELD_NAMES = ['task_to_compute', 'compute_task_def', 'report_computed_task', 'force_get_task_result']


def find_modules():
    package = importlib.import_module("golem_messages.message.tasks")
    package2 = importlib.import_module("golem_messages.message.concents")
    package3 = importlib.import_module("golem_messages.message")

    return list(dict([(name, cls) for name, cls in package.__dict__.items() if isinstance(cls, type)]).keys())


# print(find_modules())
# package = importlib.import_module("golem_messages.message.tasks")

def validate_message_list(message_list: List[Message]) -> None:
    if len(message_list) > 1:
        raise ValueError("Malformed message definition")


def create_message(message_name: str, message_params: JsonType) -> Message:
    module = importlib.import_module("golem_messages.message")
    module = module if hasattr(module, convert_message_name(message_name)) else importlib.import_module(
        "golem_messages.message.concents")
    message = getattr(module, convert_message_name(message_name))(**message_params)
    return message

    # module = importlib.import_module("golem_messages.message")
    #
    # if hasattr(module, convert_message_name(message_name)):
    #     msg_class = getattr(module, convert_message_name(message_name))
    # else:
    #     module = importlib.import_module("golem_messages.message.concents")
    #     msg_class = getattr(module, convert_message_name(message_name))
    #
    # message = msg_class(**message_params)


def substitue_message(json: JsonType, message_name: str, message: Message) -> JsonType:
    params = {k: v for k, v in json.items()}
    params[message_name] = message
    return params


def convert_message_name(message):
    return ''.join([(word[:1].capitalize() + word[1:]) for word in message.split('_')])


def split_uppercase(message):
    return (''.join([(word[:1].lower() + word[1:]) for word in re.sub(r'([A-Z])', r'_\1', message)]))[1:]


class MessageExtractor(object):
    def __init__(self):
        self.messages = []  # type: List[Message]

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
        message_list = [key for key in json.keys() if key in FIELD_NAMES]

        if self._contains_valid_message(message_list):
            message_name = message_list[0]
            message = self._process_body(json[message_name], message_name)
            params = substitue_message(json, message_name, message)
            return create_message(name, params)
        else:
            return create_message(name, json)

    def _contains_valid_message(self, FIELD_NAMES: List[Text]) -> bool:
        return len(FIELD_NAMES) == 1
