from golem_messages.exceptions      import InvalidSignature
from golem_messages.message         import Message
from golem_messages.shortcuts       import dump
from golem_messages.shortcuts       import load

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
        if isinstance(value, bytes):
            try:
                nested_message = load(
                    value,
                    private_key,
                    public_key,
                    check_time=False,
                )
            except InvalidSignature as exception:
                print("Failed to decode a Golem Message.")
            if nested_message is None:
                print('{}{:30} = <BINARY DATA>'.format(' ' * indent, field))
            else:
                print('{}{:30} ='.format(' ' * indent, field))
                print_golem_message(nested_message, private_key, public_key, indent = indent + 4)
        else:
            if isinstance(value, Message):
                print_golem_message(value, private_key, public_key, indent = indent + 4)
            else:
                print('{}{:30} = {}'.format(' ' * indent, field, value))


def api_request(host, endpoint, private_key, public_key, data = None, headers = None):
    assert all(value not in ['', None] for value in [endpoint, host, headers])
    url = "{}/api/v1/{}/".format(host, endpoint)

    if data is None:
        print('RECEIVE ({})'.format(url))
    else:
        print('SEND ({})'.format(url))
        print('MESSAGE:')
        print_golem_message(data, private_key, public_key)

        data = dump(
            data,
            private_key,
            public_key,
        )

    if data is None:
        response = requests.post("{}".format(url), headers = headers)
    else:
        response = requests.post("{}".format(url), headers = headers, data = data)

    if response.content is None:
        print('RAW RESPONSE: Reponse content is None')
    elif len(response.content) != 0:
        print('STATUS: {} {}'.format(response.status_code, http.client.responses[response.status_code]))
        print('MESSAGE:')
        if response.headers['Content-Type'] == 'application/octet-stream':
            try:
                decoded_response = load(
                    response.content,
                    private_key,
                    public_key,
                    check_time = False
                )
            except InvalidSignature as exception:
                print("Failed to decode a Golem Message.")

            print_golem_message(decoded_response, private_key, public_key)
        elif response.headers['Content-Type'] == 'application/json':
            try:
                print(response.json())
            except json.decoder.JSONDecodeError:
                print('RAW RESPONSE: Failed to decode response content')
        else:
            print('RAW RESPONSE: Unexpected content-type of response message')
    else:
        print('STATUS: {} {}'.format(response.status_code, http.client.responses[response.status_code]))
        if response.text not in ['', None]:
            print('RAW RESPONSE: {}'.format(response.text))
    print()


if __name__ == '__main__':
    pass
