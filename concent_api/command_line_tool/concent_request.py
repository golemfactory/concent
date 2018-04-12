import os
import sys
import argparse
import json
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from message_sender import send_message
from message_extractor import MessageExtractor



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
    args = parser.parse_args()

    return args.endpoint, args.message_file, args.message, args.cluster_url


if __name__ == '__main__':
    endpoint, msg_file, msg_str, cluster_url = parse_arguments()
    json_data = get_json_data(msg_file, msg_str)
    message = MessageExtractor().extract_message(json_data)
    send_message(cluster_url, message)
