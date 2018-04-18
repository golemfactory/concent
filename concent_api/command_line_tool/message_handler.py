import os
from base64 import b64encode
import requests
from golem_messages.shortcuts import dump
from golem_messages.shortcuts import load
from golem_messages.message.concents import ForceGetTaskResult
from golem_messages.message.concents import ForceReportComputedTask
from golem_messages.message.concents import ForceSubtaskResults
from golem_messages.message import AckReportComputedTask

from api_testing_common import print_golem_message
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
        if 'response' not in argv:
            message_info = ('Message: ' + str((type(message).__name__)) + ' SENT on: ' + str(cluster_url))
        else:
            message_info = ('Response: ' + str((type(message).__name__)))
        message_info_length = len(message_info)
        print('\n' + '-' * message_info_length + '\n' + str(message_info) + '\n' + '-' * message_info_length + '\n')
        print_golem_message(message, indent=4)

    def exchange_message(self, cluster_url, message):

        for party, message_types in key_map.items():
            if type(message) in message_types:
                priv_key = getattr(self, f'{party}_private_key')
                pub_key = getattr(self, f'{party}_public_key')
                break
        else:
            raise Exception(f'Unsupported Message Type: {type(message)}')

        storage_cluster_address = cluster_url
        sign_message(get_field_from_message(message, 'task_to_compute'), self.requestor_private_key)
        serialized_message = dump(message, priv_key, self.concent_pub_key)
        headers = {
            'Content-Type': 'application/octet-stream',
            # 'Concent-Client-Public-Key': b64encode(requestor_public_key).decode('ascii'),
            # 'Concent-Other-Party-Public-Key': b64encode(concent_public_key).decode('ascii'),
        }

        response = requests.post(storage_cluster_address, headers=headers, data=serialized_message)
        self.print_message(message, storage_cluster_address, priv_key, pub_key)
        if response.status_code == 202:
            print('')
            print('STATUS: 202 Message Accepted')
        elif response.status_code == 400:
            print('')
            print('STATUS: 400')
        else:
            deserialized_response = load(response.content, priv_key, self.concent_pub_key, check_time=False)
            self.print_message(deserialized_response, storage_cluster_address, priv_key, pub_key, 'response')

    def receive_message(self, cluster_url, priv_key, pub_key, concent_pub_key):

        storage_cluster_address = cluster_url

        headers = {
            'Content-Type': 'application/octet-stream',
            'concent-client-public-key': b64encode(pub_key).decode('ascii'),
        }

        response = requests.post(storage_cluster_address, headers=headers, data='')
        if response.status_code == 204:
            print('')
            print('STATUS: 204 No Content')
        elif response.status_code == 400:
            print('')
            print('STATUS: 400')
        else:
            deserialized_response = load(response.content, pub_key, concent_pub_key, check_time=False)
            self.print_message(deserialized_response, storage_cluster_address, priv_key, pub_key, 'response')
