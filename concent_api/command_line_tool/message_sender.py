
from base64 import b64encode
import requests
import os
import sys
from golem_messages.shortcuts import dump
from golem_messages.shortcuts import load
# from concent_request import print_message

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.testing_helpers import generate_ecc_key_pair

# from utils.helpers import get_current_utc_timestamp
from concent_api.settings import CONCENT_PUBLIC_KEY

from api_testing_helpers import print_golem_message

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "concent_api.settings")

(PROVIDER_PRIVATE_KEY, PROVIDER_PUBLIC_KEY) = generate_ecc_key_pair()
(REQUESTOR_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY) = generate_ecc_key_pair()


def print_message(message, private_key, public_key, cluster_url, *argv):
    if str(*argv) != 'response':
        message_info = ('Message: ' + str((type(message).__name__)) + ' SENT on: ' + str(cluster_url))
    else:
        message_info = ('Response: ' + str((type(message).__name__)))
    message_info_length = len(message_info)
    print('\n' + '-' * message_info_length + '\n' + str(message_info) + '\n' + '-' * message_info_length + '\n')
    print_golem_message(message, private_key, public_key, indent=4)


def send_message(cluster_url, message):
    private_key = REQUESTOR_PRIVATE_KEY
    public_key = REQUESTOR_PUBLIC_KEY
    # json_data = get_json_data(args)
    storage_cluster_address = cluster_url

    serialized_message = dump(message, REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY)
    headers = {
        'Content-Type': 'application/octet-stream',
        'Concent-Client-Public-Key': b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
        'Concent-Other-Party-Public-Key': b64encode(CONCENT_PUBLIC_KEY).decode('ascii'),

    }

    file_content = serialized_message
    response = requests.post(storage_cluster_address, headers=headers, data=file_content)

    deserialized_response = load(response.content, REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY, check_time=False)

    print_message(message, private_key, public_key, storage_cluster_address)
    print_message(deserialized_response, private_key, public_key, storage_cluster_address, 'response')
