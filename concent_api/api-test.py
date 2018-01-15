#!/usr/bin/env python3

import sys
import datetime
import random

import http.client
from base64                         import b64encode

from golem_messages.message         import Message
from golem_messages.message         import MessageAckReportComputedTask
from golem_messages.message         import MessageCannotComputeTask
from golem_messages.message         import MessageForceReportComputedTask
from golem_messages.message         import MessageRejectReportComputedTask
from golem_messages.message         import MessageTaskToCompute
from golem_messages.shortcuts       import dump
from golem_messages.shortcuts       import load

from utils.testing_helpers          import generate_ecc_key_pair

import requests

(CONCENT_PRIVATE_KEY,   CONCENT_PUBLIC_KEY)   = generate_ecc_key_pair()

DEFAULT_HEADERS = {
    'Content-Type':              'application/octet-stream',
    'concent-client-public-key': b64encode(CONCENT_PUBLIC_KEY).decode('ascii'),
}


def create_data(message_type, task_id):
    assert task_id >= 0
    assert isinstance(task_id, int)

    current_time = int(datetime.datetime.now().timestamp())
    message_task_to_compute = MessageTaskToCompute(
        timestamp = current_time,
        task_id = task_id,
        deadline = current_time + 6000,
    )

    message_task_to_compute_dumped = dump(
        message_task_to_compute,
        CONCENT_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
    )

    if message_type == 'MessageForceReportComputedTask':
        return MessageForceReportComputedTask(
            timestamp = current_time,
            message_task_to_compute = message_task_to_compute_dumped
        )

    elif message_type == 'MessageAckReportComputedTask':
        return MessageAckReportComputedTask(
            timestamp = current_time,
            message_task_to_compute = message_task_to_compute_dumped,
        )
    else:
        assert False, 'Invalid message type'

    return None


def create_reject_data(task_id):
    assert task_id >= 0
    assert isinstance(task_id, int)

    current_time = int(datetime.datetime.now().timestamp())
    message_cannot_compute_task = MessageCannotComputeTask(
        timestamp = current_time,
        reason = 'provider-quit',
        task_id = task_id,
    )

    message_cannot_compute_task_dumped = dump(
        message_cannot_compute_task,
        CONCENT_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
    )

    return MessageRejectReportComputedTask(
        timestamp = current_time,
        reason = 'cannot-compute-task',
        message_cannot_compute_task = message_cannot_compute_task_dumped,
    )


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
        if isinstance(value, bytes):
            try:
                nested_message = load(
                    value,
                    CONCENT_PRIVATE_KEY,
                    CONCENT_PUBLIC_KEY,
                    check_time=False,
                )
            except InvalidSignature as exception:
                print("Failed to decode a Golem Message.")
            if nested_message is None:
                print('{}{:30} = <BINARY DATA>'.format(' ' * indent, field))
            else:
                print('{}{:30} ='.format(' ' * indent, field))
                print_golem_message(nested_message, indent = indent + 4)
        else:
            print('{}{:30} = {}'.format(' ' * indent, field, value))


def api_request(host, endpoint, data = None, headers = None):
    assert all(value not in ['', None] for value in [endpoint, host, headers])

    url = "{}/api/v1/{}/".format(host, endpoint)

    if data is None:
        print('RECEIVE ({})'.format(url))
    else:
        print('SEND ({})'.format(url))
        print('MESSAGE:')
        print_golem_message(data)

        data = dump(
            data,
            CONCENT_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY,
        )

    if data is None:
        response = requests.post("{}".format(url), headers = headers)
    else:
        response = requests.post("{}".format(url), headers = headers, data = data)

    if len(response.content) != 0:
        decoded_response = load(
            response.content,
            CONCENT_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY,
        )
        print('STATUS: {} {}'.format(response.status_code, http.client.responses[response.status_code]))
        print('MESSAGE:')
        print_golem_message(decoded_response)
    else:
        print('STATUS: {} {}'.format(response.status_code, http.client.responses[response.status_code]))
        if response.text not in ['', None]:
            print('RAW RESPONSE: {}'.format(response.text))
    print()


def parse_command_line(command_line):
    if len(command_line) <= 1:
        sys.exit('Not enough arguments')

    if len(command_line) >= 3:
        sys.exit('Too many arguments')

    cluster_url = command_line[1]
    return cluster_url


def main():
    cluster_url = parse_command_line(sys.argv)
    task_id     = random.randrange(1, 100000)

    api_request(cluster_url, 'send',    create_data('MessageForceReportComputedTask', task_id), DEFAULT_HEADERS)
    api_request(cluster_url, 'receive', headers = DEFAULT_HEADERS)
    api_request(cluster_url, 'send',    create_data('MessageAckReportComputedTask', task_id), DEFAULT_HEADERS)
    api_request(cluster_url, 'receive', headers = DEFAULT_HEADERS)

    api_request(cluster_url, 'send',    create_data('MessageForceReportComputedTask', task_id + 1), DEFAULT_HEADERS)
    api_request(cluster_url, 'receive', headers = DEFAULT_HEADERS)
    api_request(cluster_url, 'send',    create_reject_data(task_id + 1), DEFAULT_HEADERS)
    api_request(cluster_url, 'receive', headers = DEFAULT_HEADERS)


if __name__ == '__main__':
    try:
        main()
    except requests.exceptions.ConnectionError as exception:
        print("\nERROR: Failed connect to the server.\n", file = sys.stderr)
        sys.exit(str(exception))
