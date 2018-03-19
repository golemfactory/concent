from golem_messages.shortcuts import dump
from golem_messages.shortcuts import load
from utils.testing_helpers import generate_ecc_key_pair
from api_testing_helpers import print_golem_message
from concent_api.settings import CONCENT_PUBLIC_KEY
from .message_extractor import MessageExtractor
from utils.helpers import get_current_utc_timestamp
from jsonschema import Draft4Validator
from base64 import b64encode
import requests
import argparse
import json
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "concent_api.settings")

(PROVIDER_PRIVATE_KEY, PROVIDER_PUBLIC_KEY) = generate_ecc_key_pair()
(REQUESTOR_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY) = generate_ecc_key_pair()


def verify_schema(json_data):
    schema = {
        "type": "object",
        "properties": {
            "timestamp": {"type": "string"},
            "inner_golem_message": {
                "type": "object",
                "properties": {
                    "timestamp": {"type": "string"},
                    "deadline": {"type": "string"}
                }
            }
        },
    }
    v = Draft4Validator(schema)
    errors = sorted(v.iter_errors(json_data), key=lambda e: e.path)

    if errors:
        error_number = 0
        print('\nUploaded schema has following errors:\n')
        for error in errors:
            error_number += 1
            print(str(error_number) + '->', list(error.path), ':', error.message)
        print('\nEND')
        exit()


def get_json_data(args):
    if args.message_file:
        json_data = json.load(open(args.message_file))
    elif args.message:
        json_data = json.loads(args.message)
    # verify_schema(json_data)
    return json_data


def print_message(message, private_key, public_key, cluster_url, *argv):
    if str(*argv) != 'response':
        message_info = ('Message: ' + str((type(message).__name__)) + ' SENT on: ' + str(cluster_url))
    else:
        message_info = ('Response: ' + str((type(message).__name__)))
    message_info_length = len(message_info)
    print('\n' + '-' * message_info_length + '\n' + str(message_info) + '\n' + '-' * message_info_length + '\n')
    print_golem_message(message, private_key, public_key, indent=4)


def send_message(args):
    private_key = REQUESTOR_PRIVATE_KEY
    public_key = REQUESTOR_PUBLIC_KEY
    json_data = get_json_data(args)
    STORAGE_CLUSTER_ADDRESS = args.cluster_url
    message = MessageExtractor().extract_message(json_data)
    serialized_message = dump(message, REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY)
    headers = {
        'Content-Type': 'application/octet-stream',
        'Concent-Client-Public-Key': b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
        'Concent-Other-Party-Public-Key': b64encode(CONCENT_PUBLIC_KEY).decode('ascii'),

    }

    file_content = serialized_message
    response = requests.post(STORAGE_CLUSTER_ADDRESS, headers=headers, data=file_content)

    deserialized_response = load(response.content, REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY, check_time=False)
    print_message(message, private_key, public_key, STORAGE_CLUSTER_ADDRESS)
    print_message(deserialized_response, private_key, public_key, STORAGE_CLUSTER_ADDRESS, 'response')


def receive_message(args):
    print('------------------------\n    Message recieved\n------------------------')
    print('cluster_url:', args.cluster_url)
    print('subtask_id:', args.subtask_id)


def receive_out_of_band_message(args):
    print('------------------------------\n Message out-of-band recieved\n------------------------------')
    print('cluster_url:', args.cluster_url)
    print('subtask_id:', args.subtask_id)


def parse_arguments():
    # create the top-level parser
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()

    # ENDPOINT
    # send
    parser_send_message = subparsers.add_parser('send')
    parser_send_message.add_argument("cluster_url")
    parser_send_message.set_defaults(func=send_message)
    json_format = parser_send_message.add_mutually_exclusive_group(required=True)
    json_format.add_argument('-s', '--message', action="store")
    json_format.add_argument('-f', '--message-file', metavar='--message_file', action="store")

    # ENDPOINT
    # receive
    parser_receive_message = subparsers.add_parser('receive')
    parser_receive_message.set_defaults(func=receive_message)
    parser_receive_message.add_argument("cluster_url", )
    parser_receive_message.add_argument('--subtask_id', action="store")

    # ENDPOINT
    # receive-out-of-band
    parser_receive_out_of_band_message = subparsers.add_parser('receive-out-of-band')
    parser_receive_out_of_band_message.set_defaults(func=receive_out_of_band_message)
    parser_receive_out_of_band_message.add_argument("cluster_url", )

    parser_receive_out_of_band_message.add_argument('--subtask_id', action="store")
    args = parser.parse_args()

    args.func(args)


if __name__ == '__main__':
    parse_arguments()
