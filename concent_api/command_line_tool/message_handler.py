import os
import requests
from golem_messages.shortcuts import dump
from golem_messages.shortcuts import load
from golem_messages.message.concents import ForceGetTaskResult
from golem_messages.message.concents import ForceReportComputedTask
from golem_messages.message.concents import ForceSubtaskResults
from golem_messages.message import AckReportComputedTask

from api_testing_common import print_golem_message
from api_testing_common import create_client_auth_message
from utils.testing_helpers import generate_ecc_key_pair
from utils.helpers import sign_message
from utils.helpers import get_field_from_message

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "concent_api.settings")
(PROVIDER_PRIVATE_KEY, PROVIDER_PUBLIC_KEY) = generate_ecc_key_pair()
(REQUESTOR_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY) = generate_ecc_key_pair()

key_map = {
    'requestor': [ForceGetTaskResult, AckReportComputedTask],
    'provider': [ForceReportComputedTask, ForceSubtaskResults],
}


class MessageHandler():
    def __init__(self, requestor_private_key, requestor_public_key, provider_public_key, provider_private_key,
                 concent_pub_key):
        self.requestor_private_key = requestor_private_key
        self.requestor_public_key = requestor_public_key
        self.provider_private_key = provider_private_key
        self.provider_public_key = provider_public_key
        self.concent_pub_key = concent_pub_key

    def print_message(self, message, cluster_url, *argv):
        if 'send' in argv:
            message_info = ('Message: ' + str((type(message).__name__)) + ' SENT on: ' + str(cluster_url))
        elif 'response' in argv:
            message_info = ('Response: ' + str((type(message).__name__)))

        print('\n' + '-' * len(message_info) + '\n' + str(message_info) + '\n' + '-' * len(message_info) + '\n')
        print_golem_message(message, indent=4)

    def handle_message(self, priv_key, cluster_url, data):
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
        elif response.status_code == 400:
            print('')
            print('STATUS: 400')
        else:
            deserialized_response = load(response.content, priv_key, self.concent_pub_key, check_time=False)
            self.print_message(deserialized_response, cluster_url, 'response')

    def select_keys(self, party):
        priv_key = getattr(self, f'{party}_private_key')
        pub_key = getattr(self, f'{party}_public_key')
        return priv_key, pub_key

    def prepare_to_send_message(self, cluster_url, message):
        for party, message_types in key_map.items():
            if type(message) in message_types:
                priv_key, pub_key = self.select_keys(party)
                break
        else:
            raise Exception(f'Unsupported Message Type: {type(message)}')
        self.print_message(message, cluster_url, 'send')
        sign_message(get_field_from_message(message, 'task_to_compute'), self.requestor_private_key)
        serialized_message = dump(message, priv_key, self.concent_pub_key)
        self.handle_message(priv_key, cluster_url, serialized_message)

    def prepare_to_receive_message(self, cluster_url, party):
        print("""\n-----------------
Endpoint: RECEIVE
-----------------""")
        priv_key, pub_key = self.select_keys(party)
        auth_data = create_client_auth_message(priv_key, pub_key, self.concent_pub_key)
        self.handle_message(priv_key, cluster_url, auth_data)
