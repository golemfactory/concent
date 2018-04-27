import os
import sys
import argparse
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from message_handler import MessageHandler
from message_extractor import MessageExtractor
from key_manager import KeyManager


def get_json_data(message_file, message_str):
    if message_file:
        return json.load(open(message_file))
    else:
        return json.loads(message_str)


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
    parser_send_message.add_argument("--print_keys", action="store_true")
    json_format = parser_send_message.add_mutually_exclusive_group(required=True)
    json_format.add_argument('-s', '--message', action="store")
    json_format.add_argument('-f', '--message-file', action="store")

    # ENDPOINT
    # receive
    parser_receive_message = subparsers.add_parser('receive')
    parser_receive_message.set_defaults(endpoint="receive")
    parser_receive_message.add_argument("cluster_url")
    parser_receive_message.add_argument("--print_keys", action="store_true")
    parser_receive_message.add_argument("--party", action="store", choices=('provider', 'requestor'), required=True)

    # ENDPOINT
    # receive-out-of-band
    parser_receive_out_of_band_message = subparsers.add_parser('receive-out-of-band')
    parser_receive_out_of_band_message.set_defaults(endpoint="receive_out_of_band_message")
    parser_receive_out_of_band_message.add_argument("cluster_url")
    parser_receive_out_of_band_message.add_argument("--print_keys", action="store_true")
    parser_receive_out_of_band_message.add_argument(
        '--party',
        action="store",
        choices=('provider', 'requestor'),
        required=True)

    return parser.parse_args()


def print_keys(requestor_public_key, requestor_private_key, provider_public_key, provider_private_key,
               concent_public_key):
    print('REQUESTOR_PRIVATE_KEY', '\n', requestor_private_key, '\n')
    print('REQUESTOR_PUBLIC_KEY', '\n', requestor_public_key, '\n')
    print('PROVIDER_PRIVATE_KEY', '\n', provider_private_key, '\n')
    print('PROVIDER_PUBLIC_KEY', '\n', provider_public_key, '\n')
    print('CONCENT_PUBLIC_KEY', '\n', concent_public_key, '\n')


if __name__ == '__main__':
    args = parse_arguments()

    key_manager = KeyManager()
    requestor_public_key, requestor_private_key = key_manager.get_requestor_keys()
    provider_public_key, provider_private_key = key_manager.get_provider_keys()
    concent_public_key = key_manager.get_concent_public_key()

    if args.print_keys:
        print_keys(requestor_public_key, requestor_private_key, provider_public_key, provider_private_key,
                   concent_public_key)

    message_handler = MessageHandler(
        requestor_private_key,
        requestor_public_key,
        provider_public_key,
        provider_private_key,
        concent_public_key)

    if args.endpoint == 'send':
        json_data = get_json_data(args.message_file, args.message)
        message = MessageExtractor(
            requestor_public_key,
            provider_public_key).extract_message(json_data)

        message_handler.prepare_to_send_message(args.cluster_url, message)


    elif args.endpoint == 'receive':
        message_handler.prepare_to_receive_message(args.cluster_url, args.party)
