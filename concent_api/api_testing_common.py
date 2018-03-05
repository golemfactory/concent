import sys

from golem_messages.exceptions      import MessageError
from golem_messages.message         import Message
from golem_messages.shortcuts       import dump
from golem_messages.shortcuts       import load

import datetime
import json
import requests
import http.client


def print_golem_message(message, private_key, public_key, indent = 4):
    assert isinstance(message, Message)
    HEADER_FIELDS  = ['timestamp', 'encrypted', 'sig']
    PRIVATE_FIELDS = {'_payload', '_raw'}
    assert 'type' not in message.__slots__
    fields = ['type'] + HEADER_FIELDS + sorted(set(message.__slots__) - set(HEADER_FIELDS) - PRIVATE_FIELDS)
    values = [
        type(message).__name__ if field == 'type' else
        getattr(message, field)
        for field in fields
    ]

    for field, value in zip(fields, values):
        if isinstance(value, Message):
            print_golem_message(value, private_key, public_key, indent = indent + 4)
        else:
            print('{}{:30} = {}'.format(' ' * indent, field, value))


def api_request(host, endpoint, private_key, public_key, data = None, headers = None):
    def _prepare_data(data):
        if data is None:
            return ''
        return dump(
            data,
            private_key,
            public_key,
        )

    def _print_data(data, url):
        if data is None:
            print('RECEIVE ({})'.format(url))
        else:
            print('SEND ({})'.format(url))
            print('MESSAGE:')
            print_golem_message(data, private_key, public_key)

    assert all(value not in ['', None] for value in [endpoint, host, headers])
    url = "{}/api/v1/{}/".format(host, endpoint)

    _print_data(data, url)

    response = requests.post("{}".format(url), headers = headers, data = _prepare_data(data))

    _print_response(private_key, public_key, response)

    print()


def _print_response(private_key, public_key, response):
    if response.content is None:
        print('RAW RESPONSE: Reponse content is None')
    elif len(response.content) != 0:
        _print_messge_from_response(private_key, public_key, response)
    else:
        print('STATUS: {} {}'.format(response.status_code, http.client.responses[response.status_code]))
        if response.text not in ['', None]:
            print('RAW RESPONSE: {}'.format(response.text))


def _print_messge_from_response(private_key, public_key, response):
    print('STATUS: {} {}'.format(response.status_code, http.client.responses[response.status_code]))
    print('MESSAGE:')
    if response.headers['Content-Type'] == 'application/octet-stream':
        _print_message_from_stream(private_key, public_key, response)
    elif response.headers['Content-Type'] == 'application/json':
        _print_message_from_json(response)
    else:
        print('RAW RESPONSE: Unexpected content-type of response message')


def _print_message_from_json(response):
    try:
        print(response.json())
    except json.decoder.JSONDecodeError:
        print('RAW RESPONSE: Failed to decode response content')


def _print_message_from_stream(private_key, public_key, response):
    try:
        decoded_response = load(
            response.content,
            private_key,
            public_key,
            check_time=False
        )
    except MessageError:
        print("Failed to decode a Golem Message.")
    print_golem_message(decoded_response, private_key, public_key)


def timestamp_to_isoformat(timestamp):
    return datetime.datetime.fromtimestamp(timestamp).isoformat(' ')


def parse_command_line(command_line):
    if len(command_line) <= 1:
        sys.exit('Not enough arguments')

    if len(command_line) >= 3:
        sys.exit('Too many arguments')

    cluster_url = command_line[1]
    return cluster_url


if __name__ == '__main__':
    pass
