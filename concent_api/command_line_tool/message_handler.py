import os
import requests
from golem_messages.shortcuts import dump
from golem_messages.shortcuts import load
from golem_messages.message import Message
from golem_messages.message.tasks import AckReportComputedTask
from golem_messages.message.concents import ForceGetTaskResult
from golem_messages.message.concents import ForceReportComputedTask
from golem_messages.message.concents import ForceSubtaskResults
# TODO: Remove when setup.py will be created
import pathmagic  # noqa: F401  # pylint: disable=unused-import
from api_testing_common import create_client_auth_message
from api_testing_common import print_golem_message
from common.helpers import get_field_from_message
from common.helpers import sign_message

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "concent_api.settings")

KEY_MAP = {
    'requestor': (ForceGetTaskResult, AckReportComputedTask),
    'provider': (ForceReportComputedTask, ForceSubtaskResults),
}


def print_message(message: Message, cluster_url: str, endpoint: str) -> None:
    if endpoint == 'send':
        message_info = 'Endpoint: SEND'
        _print_message_info(message_info)
        message_info = ('Message: ' + str((type(message).__name__)) + ' SENT on: ' + str(cluster_url))
        _print_message_info(message_info)
    elif endpoint in ('receive', 'receive-out-of-band'):
        message_info = f'Endpoint: {str.upper(endpoint)}'
        _print_message_info(message_info)
    elif message is not None:
        message_info = ('Response: ' + str((type(message).__name__)))
        _print_message_info(message_info)
    else:
        print('Unsupported Message')
    if message is not None:
        print_golem_message(message, indent=4)


def _print_message_info(message_info: str) -> None:
    print('-' * len(message_info) + '\n' + str(message_info) + '\n' + '-' * len(message_info))


class MessageHandler():
    def __init__(
        self,
        requestor_private_key: bytes,
        requestor_public_key: bytes,
        provider_public_key: bytes,
        provider_private_key: bytes,
        concent_pub_key: bytes,
    ) -> None:

        self.requestor_private_key = requestor_private_key
        self.requestor_public_key = requestor_public_key
        self.provider_private_key = provider_private_key
        self.provider_public_key = provider_public_key
        self.concent_pub_key = concent_pub_key

    def _exchange_message(self, priv_key: bytes, cluster_url: str, data: bytes) -> None:
        headers = {
            'Content-Type': 'application/octet-stream',
        }
        response = requests.post(cluster_url, headers=headers, data=data)
        if response.status_code == 202:
            print('')
            print('STATUS: 202 Message Accepted')
        elif response.status_code == 204:
            print('')
            print('STATUS: 204 No Content')
        elif response.status_code in [400, 404, 500, 503]:
            print('')
            print('STATUS: {}'.format(response.status_code))
            print('Response Content:', response.content)
        else:
            deserialized_response = load(response.content, priv_key, self.concent_pub_key, check_time=False)
            print_message(deserialized_response, cluster_url, '')

    def select_keys(self, party: str) -> tuple:
        priv_key = getattr(self, f'{party}_private_key')
        pub_key = getattr(self, f'{party}_public_key')
        return priv_key, pub_key

    def send(self, cluster_url: str, message: Message) -> None:
        for party, message_types in KEY_MAP.items():
            if isinstance(message, message_types):
                priv_key, _ = self.select_keys(party)
                break
        else:
            raise Exception(f'Unsupported Message Type: {type(message)}')
        print_message(message, cluster_url, 'send')
        sign_message(get_field_from_message(message, 'task_to_compute'), self.requestor_private_key)
        serialized_message = dump(message, priv_key, self.concent_pub_key)
        self._exchange_message(priv_key, cluster_url, serialized_message)

    def receive(self, cluster_url: str, party: str, endpoint: str) -> None:
        print_message(None, cluster_url, endpoint)
        priv_key, pub_key = self.select_keys(party)
        auth_data = create_client_auth_message(priv_key, pub_key, self.concent_pub_key)
        self._exchange_message(priv_key, cluster_url, auth_data)
