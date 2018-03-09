import datetime
import http.client
import json
import requests
import sys

from collections                    import namedtuple

from golem_messages.exceptions      import MessageError
from golem_messages.message         import Message, ComputeTaskDef, TaskToCompute
from golem_messages.shortcuts       import dump
from golem_messages.shortcuts       import load


ProtocolConstants = namedtuple("ProtocolConstants",
                               ["concent_messaging_time",
                                "subtask_verification_time",
                                "force_acceptance_time",
                                "token_expiration_time"])


def get_protocol_constants(cluster_url):
    url = f"{cluster_url}/api/v1/protocol-constants/"
    resp = requests.get(url)
    json = resp.json()
    concent_messaging_time = json['concent_messaging_time']
    subtask_verification_time = json['subtask_verification_time']
    force_acceptance_time = json['force_acceptance_time']
    token_expiration_time = json['token_expiration_time']
    constants = ProtocolConstants(concent_messaging_time, subtask_verification_time, force_acceptance_time,
                                  token_expiration_time)
    return constants


def print_protocol_constants(constants):
    print("PROTOCOL_CONSTANTS: ")
    print(f"concent_messaging_time = {constants.concent_messaging_time}")
    print(f"subtask_verification_time = {constants.subtask_verification_time}")
    print(f"force_acceptance_time = {constants.force_acceptance_time}")
    print(f"token_expiration_time = {constants.token_expiration_time}\n")


def print_golem_message(message, indent=4):
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
            print_golem_message(value, indent=indent + 4)
        elif field == 'timestamp':
            print('{}{:30} = {}  # UTC: {}'.format(' ' * indent, field, value, timestamp_to_isoformat(value)))
        else:
            print('{}{:30} = {}'.format(' ' * indent, field, value))


def validate_response_status(actual_status_code, expected_status):
    if expected_status is not None:
        assert expected_status == actual_status_code, f"Expected:HTTP{expected_status}, actual:HTTP{actual_status_code}"


def validate_response_message(encoded_message, expected_message, private_key, public_key,):
    if expected_message is not None:
        decoded_message = try_to_decode_golem_message(private_key, public_key, encoded_message)
        assert isinstance(decoded_message, expected_message), f"Expected:{expected_message}, actual:{decoded_message}"


def api_request(host, endpoint, private_key, public_key, data=None, headers=None, expected_status=None, expected_message=None):
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
    url = "{}/api/v1/{}/".format(host, endpoint)

    _print_data(data, url)

    response = requests.post("{}".format(url), headers = headers, data = _prepare_data(data))

    _print_response(private_key, public_key, response)
    validate_response_status(response.status_code, expected_status)
    validate_response_message(response.content, expected_message, private_key, public_key,)
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
            check_time=False
        )
    except MessageError:
        print("Failed to decode a Golem Message.")
        raise
    return decoded_response


def timestamp_to_isoformat(timestamp):
    return datetime.datetime.fromtimestamp(timestamp).isoformat(' ')


def parse_command_line(command_line):
    if len(command_line) <= 1:
        sys.exit('Not enough arguments')

    if len(command_line) >= 3:
        sys.exit('Too many arguments')

    cluster_url = command_line[1]
    return cluster_url


def create_task_to_compute(current_time, task_id, deadline_offset=60):
    compute_task_def = ComputeTaskDef()
    compute_task_def['task_id'] = task_id
    compute_task_def['deadline'] = current_time + deadline_offset
    task_to_compute = TaskToCompute(
        compute_task_def=compute_task_def)
    return task_to_compute
