from golem_messages.exceptions      import MessageError
from golem_messages.message         import Message
from golem_messages.shortcuts       import dump
from golem_messages.shortcuts       import load

import datetime
import json
import requests
import http.client


class TestAssertionException(Exception):
    pass


def assert_condition(actual, expected, error_message = None):
    message = error_message or f"Actual: {actual} != expected: {expected}"
    if actual != expected:
        raise TestAssertionException(message)


def print_golem_message(message, indent = 4):
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
            print_golem_message(value, indent = indent + 4)
        else:
            print('{}{:30} = {}'.format(' ' * indent, field, value))


def validate_response_status(actual_status_code, expected_status):
    if expected_status is not None:
        assert_condition(
            actual_status_code,
            expected_status,
            f"Expected:HTTP{expected_status}, actual:HTTP{actual_status_code}"
        )


def validate_response_message(encoded_message, expected_message_type, private_key, public_key):
    if expected_message_type is not None:
        decoded_message = try_to_decode_golem_message(private_key, public_key, encoded_message)
        assert_condition(
            decoded_message.TYPE,
            expected_message_type,
            f"Expected:{expected_message_type}, actual:{decoded_message.TYPE}",
        )


def validate_content_type(actual_content_type, expected_content_type):
    if expected_content_type is not None:
        assert_condition(
            actual_content_type,
            expected_content_type,
            f"Wrong content type for Golem Message: {actual_content_type}"
        )


def api_request(
    host,
    endpoint,
    private_key,
    public_key,
    data=None,
    headers=None,
    expected_status=None,
    expected_message_type=None,
    expected_content_type=None
):
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
            print_golem_message(data)

    assert all(value not in ['', None] for value in [endpoint, host, headers])
    url         = "{}/api/v1/{}/".format(host, endpoint)

    _print_data(data, url)

    response = requests.post("{}".format(url), headers=headers, data=_prepare_data(data), verify=False)
    _print_response(private_key, public_key, response)
    validate_response_status(response.status_code, expected_status)
    validate_content_type(response.headers['Content-Type'], expected_content_type)
    validate_response_message(response.content, expected_message_type, private_key, public_key)
    print()


def _print_response(private_key, public_key, response):
    if response.content is None:
        print('RAW RESPONSE: Reponse content is None')
    elif len(response.content) != 0:
        _print_message_from_response(private_key, public_key, response)
    else:
        print('STATUS: {} {}'.format(response.status_code, http.client.responses[response.status_code]))
        if response.text not in ['', None]:
            print('RAW RESPONSE: {}'.format(response.text))


def _print_message_from_response(private_key, public_key, response):
    print('STATUS: {} {}'.format(response.status_code, http.client.responses[response.status_code]))
    print('MESSAGE:')
    print('Concent-Golem-Messages-Version = {}'.format(response.headers['concent-golem-messages-version']))
    if response.headers['Content-Type'] == 'application/octet-stream':
        _print_message_from_stream(private_key, public_key, response.content)
    elif response.headers['Content-Type'] == 'application/json':
        _print_message_from_json(response)
    else:
        print('RAW RESPONSE: Unexpected content-type of response message')


def _print_message_from_json(response):
    try:
        print(response.json())
    except json.decoder.JSONDecodeError:
        print('RAW RESPONSE: Failed to decode response content')


def _print_message_from_stream(private_key, public_key, content):
    decoded_response = try_to_decode_golem_message(private_key, public_key, content)
    print_golem_message(decoded_response)


def try_to_decode_golem_message(private_key, public_key, content):
    try:
        decoded_response = load(
            content,
            private_key,
            public_key,
            check_time = False
        )
    except MessageError:
        print("Failed to decode a Golem Message.")
        raise
    return decoded_response


def timestamp_to_isoformat(timestamp):
    return datetime.datetime.fromtimestamp(timestamp).isoformat(' ')


if __name__ == '__main__':
    pass
