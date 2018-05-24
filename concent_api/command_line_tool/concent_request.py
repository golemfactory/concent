import argparse
import json
from message_handler import MessageHandler  # pylint: disable=import-error
from message_extractor import MessageExtractor  # pylint: disable=import-error
from key_manager import KeyManager  # pylint: disable=import-error


def get_json_data(message_file, message_str):
    if message_file:
        return json.load(open(message_file))
    else:
        return json.loads(message_str)


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
    parser_receive_out_of_band = subparsers.add_parser('receive-out-of-band')
    parser_receive_out_of_band.set_defaults(endpoint="receive-out-of-band")
    parser_receive_out_of_band.add_argument("cluster_url")
    parser_receive_out_of_band.add_argument("--print_keys", action="store_true")
    parser_receive_out_of_band.add_argument(
        '--party',
        action="store",
        choices=('provider', 'requestor'),
        required=True)

    return parser.parse_args()


def print_keys(req_pub_key, req_priv_key, prov_pub_key, prov_priv_key, conc_pub_key):
    print('REQUESTOR_PRIVATE_KEY = ', req_priv_key)
    print('REQUESTOR_PUBLIC_KEY = ', req_pub_key)
    print('')
    print('PROVIDER_PRIVATE_KEY = ', prov_priv_key)
    print('PROVIDER_PUBLIC_KEY = ', prov_pub_key)
    print('')
    print('CONCENT_PUBLIC_KEY = ', conc_pub_key)


if __name__ == '__main__':
    args = parse_arguments()
    cluster_url = "{}/api/v1/{}/".format(args.cluster_url, args.endpoint)
    key_manager = KeyManager()
    requestor_public_key, requestor_private_key = key_manager.get_requestor_keys()
    provider_public_key, provider_private_key = key_manager.get_provider_keys()
    concent_public_key = key_manager.get_concent_public_key()

    if args.print_keys:
        print_keys(
            requestor_public_key,
            requestor_private_key,
            provider_public_key,
            provider_private_key,
            concent_public_key,
        )

    message_handler = MessageHandler(
        requestor_private_key,
        requestor_public_key,
        provider_public_key,
        provider_private_key,
        concent_public_key,
    )

    if args.endpoint == 'send':
        json_data = get_json_data(args.message_file, args.message)
        message = MessageExtractor(
            requestor_public_key,
            provider_public_key
        ).extract_message(json_data)

        message_handler.send(cluster_url, message)

    elif args.endpoint == 'receive' or 'receive-out-of-band':
        message_handler.receive(cluster_url, args.party, args.endpoint)
