import os
import sys
import argparse
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.testing_helpers import generate_ecc_key_pair
from concent_api.settings import CONCENT_PUBLIC_KEY
from message_handler import MessageHandler
from message_extractor import MessageExtractor
from key_manager import KeyManager

(PROVIDER_PRIVATE_KEY, PROVIDER_PUBLIC_KEY) = generate_ecc_key_pair()
(REQUESTOR_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY) = generate_ecc_key_pair()

concent_public_key = CONCENT_PUBLIC_KEY


def get_json_data(message_file, message_str):
    if message_file:
        return json.load(open(message_file))
    else:
        return json.loads(message_str)
    # verify_schema(json_data)


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
    parser_send_message.set_defaults(endpoint="send")
    json_format = parser_send_message.add_mutually_exclusive_group(required=True)
    json_format.add_argument('-s', '--message', action="store")
    json_format.add_argument('-f', '--message-file', action="store")

    # ENDPOINT
    # receive
    parser_receive_message = subparsers.add_parser('receive')
    parser_receive_message.set_defaults(endpoint="receive")
    parser_receive_message.add_argument("cluster_url", )
    parser_receive_message.add_argument('--subtask_id', action="store")

    # ENDPOINT
    # receive-out-of-band
    parser_receive_out_of_band_message = subparsers.add_parser('receive-out-of-band')
    parser_receive_out_of_band_message.set_defaults(endpoint="receive_out_of_band_message")
    parser_receive_out_of_band_message.add_argument("cluster_url", )

    parser_receive_out_of_band_message.add_argument('--subtask_id', action="store")
    return parser.parse_args()


if __name__ == '__main__':
    args = parse_arguments()

    key_manager = KeyManager()
    requestor_public_key, requestor_private_key = key_manager.get_requestor_keys()
    provider_public_key, provider_private_key = key_manager.get_provider_keys()

    if args.endpoint == 'send':
        json_data = get_json_data(args.message_file, args.message)
        message = MessageExtractor(
            requestor_public_key,
            provider_public_key).extract_message(json_data)
        MessageHandler(
            requestor_private_key,
            requestor_public_key,
            provider_public_key,
            provider_private_key,
            concent_public_key).exchange_message(args.cluster_url, message)

    elif args.endpoint == 'receive':
        MessageHandler(requestor_private_key,
                       requestor_public_key,
                       provider_public_key,
                       provider_private_key,
                       concent_public_key).receive_message(args.cluster_url)
