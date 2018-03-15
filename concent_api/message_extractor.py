import importlib

from typing import Dict, Text, Any, List

from golem_messages.message import Message

JsonType = Dict[Text, Any]

MESSAGE_NAMES = ['ForceReportComputedTask']


def validate_message_list(message_list: List[Message]) -> None:
    if len(message_list) > 1:
        raise ValueError("Malformed message definition")


def create_message(message_name: str, message_params: JsonType) -> Message:
    module = importlib.import_module("concents", "golem_messages.message")
    msg_class = getattr(module, message_name)
    message = msg_class(**message_params)
    return message


def substitue_message(json: JsonType, message_name: str, message: Message) -> JsonType:
    params = {k: v for k, v in json.items()}
    params[message_name] = message
    return params


def convert_message_name(message):
    return ''.join([(word[:1].capitalize() + word[1:]) for word in message.split('_')])

class MessageExtractor(object):
    def __init__(self):
        self.messages = []  # type: List[Message]

    def extract_message(self, json: JsonType, name: str = None) -> Message:
        if name is None:
            self._process_top_level(json)
        else:
            self._processs_body(json, name)

    def _process_top_level(self, json):
        try:
            name = json['type']
            body = json['body']
        except KeyError:
            # TODO: throw an appropriate exception, maybe log sth
            raise
        message = self.extract_message(body, name)

    def _processs_body(self, json: JsonType, name: str) -> Message:
        message_list = [key for key in json.keys() if key in MESSAGE_NAMES]
        if self._contains_valid_message(message_list):
            message_name = message_list[0]
            message = self._processs_body(json['message_name'], message_name)
            params = substitue_message(json, message_name,  message)
            return create_message(name, params)
        else:
            return create_message(name, json)

    def _contains_valid_message(self, message_names: List[Text]) -> bool:
        return len(message_names) == 1

