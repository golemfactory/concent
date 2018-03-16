from jsonschema import Draft4Validator
import argparse
import json


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
    print(json_data)
    verify_schema(json_data)
    return json_data


def send_message(args):
    cluster_url = args.cluster_url
    json_data = get_json_data(args)
    print('------------------------\n      Message sent\n------------------------')

    print(json_data, cluster_url)


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
