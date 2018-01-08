#!/usr/bin/env python3

import sys
import datetime
import random
import time
import http.client
from base64                 import b64encode

from golem_messages         import dump
from golem_messages         import load
from golem_messages.message import AckReportComputedTask
from golem_messages.message import ComputeTaskDef
from golem_messages.message import ForceReportComputedTask
from golem_messages.message import Message
from golem_messages.message import TaskToCompute

from utils.testing_helpers  import generate_ecc_key_pair

import requests

CONCENT_PUBLIC_KEY  = b'\xf3\x97\x19\xcdX\xda\x86tiP\x1c&\xd39M\x9e\xa4\xddb\x89\xb5,]O\xd5cR\x84\xb85\xed\xc9\xa17e,\xb2s\xeb\n1\xcaN.l\xba\xc3\xb7\xc2\xba\xff\xabN\xde\xb3\x0b\xa6l\xbf6o\x81\xe0;'
CONCENT_PRIVATE_KEY = b'l\xcdh\x19\xeb$>\xbcG\xa1\xc7v\xe8\xd7o\x0c\xbf\x0e\x0fM\x89lw\x1e\xd7K\xd6Hnv$\xa2'

(PROVIDER_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY)  = generate_ecc_key_pair()
(REQUESTOR_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY) = generate_ecc_key_pair()


def print_golem_message(message, indent = 4):
    assert isinstance(message, Message)

    HEADER_FIELDS  = ['timestamp', 'encrypted', 'sig']
    PRIVATE_FIELDS = {'_payload', '_raw', 'result_hash'}
    assert 'type' not in message.__slots__
    fields = ['type'] + HEADER_FIELDS + sorted(set(message.__slots__) - set(HEADER_FIELDS) - PRIVATE_FIELDS)
    values = [
        type(message).__name__ if field == 'type' else
        getattr(message, field)
        for field in fields
    ]

    for field, value in zip(fields, values):
        if isinstance(value, bytes) and field is not 'sig':
            try:
                nested_message = load(
                    value,
                    CONCENT_PRIVATE_KEY,
                    CONCENT_PUBLIC_KEY,
                    check_time = False
                )
            except AttributeError:
                # FIXME: golem-messages provides no reliable way to discern invalid messages from other AttributeErrors.
                print('{}{:30} = <BINARY DATA>'.format(' ' * indent, field))
            else:
                print('{}{:30} ='.format(' ' * indent, field))
                print_golem_message(nested_message, indent = indent + 4)
        else:
            if isinstance(value, Message):
                if message.task_to_compute is not None:
                    print_golem_message(message.task_to_compute, indent = indent + 4)
                else:
                    print_golem_message(message.cannot_compute_task, indent = indent + 4)
            else:
                print('{}{:30} = {}'.format(' ' * indent, field, value))


def api_request(host, endpoint, private_key = None, public_key = None, data = None, headers = None, ):
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
            private_key,
            CONCENT_PUBLIC_KEY,
        )

    if data is None:
        response = requests.post("{}".format(url), headers = headers)
    else:
        response = requests.post("{}".format(url), headers = headers, data = data)

    if len(response.content) != 0:
        decoded_response = load(
            response.content,
            private_key,
            public_key,
            check_time = False
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


def force_report_computed_task(task_id, provider_private_key, provider_public_key, requestor_private_key, requestor_public_key, current_time):

    compute_task_def = ComputeTaskDef()
    compute_task_def['task_id'] = task_id
    compute_task_def['deadline'] = current_time + 60
    task_to_compute = TaskToCompute(
        timestamp = current_time - 3540,
        compute_task_def = compute_task_def)

    serialized_task_to_compute      = dump(task_to_compute,             requestor_private_key,  provider_public_key)
    deserialized_task_to_compute    = load(serialized_task_to_compute,  provider_private_key,   requestor_public_key, check_time = False)

    force_report_computed_task = ForceReportComputedTask(
        timestamp = current_time - 3540
    )
    force_report_computed_task.task_to_compute = deserialized_task_to_compute

    return force_report_computed_task


def ack_report_computed_task(task_id, provider_private_key, provider_public_key, requestor_private_key, requestor_public_key, current_time):

    task_to_compute = TaskToCompute(
        timestamp   = current_time - 3540
    )
    task_to_compute.compute_task_def = ComputeTaskDef()
    task_to_compute.compute_task_def['task_id']     = task_id
    task_to_compute.compute_task_def['deadline']    = current_time + 60

    serialized_task_to_compute      = dump(task_to_compute,             requestor_private_key,  provider_public_key)
    deserialized_task_to_compute    = load(serialized_task_to_compute,  provider_private_key,   requestor_public_key, check_time = False)

    ack_report_computed_task = AckReportComputedTask(
        timestamp               = current_time + 65,
    )
    ack_report_computed_task.task_to_compute = deserialized_task_to_compute
    return ack_report_computed_task


def main():
    cluster_url = parse_command_line(sys.argv)
    task_id     = random.randrange(1, 100000)
    current_time = int(datetime.datetime.now().timestamp())

    api_request(
        cluster_url,
        'send',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        force_report_computed_task(
            task_id,
            PROVIDER_PRIVATE_KEY,
            PROVIDER_PUBLIC_KEY,
            REQUESTOR_PRIVATE_KEY,
            REQUESTOR_PUBLIC_KEY,
            current_time
        ), headers = {
            'Content-Type': 'application/octet-stream',
            'concent-client-public-key': b64encode(PROVIDER_PUBLIC_KEY).decode('ascii')
        }
    )
    time.sleep(65)

    api_request(
        cluster_url,
        'receive',
        CONCENT_PRIVATE_KEY,
        PROVIDER_PUBLIC_KEY,
        headers = {
            'Content-Type': 'application/octet-stream',
            'concent-client-public-key': b64encode(PROVIDER_PUBLIC_KEY).decode('ascii')
        }
    )

    api_request(cluster_url,
        'send',
        REQUESTOR_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        ack_report_computed_task(
            task_id,
            PROVIDER_PRIVATE_KEY,
            PROVIDER_PUBLIC_KEY,
            REQUESTOR_PRIVATE_KEY,
            REQUESTOR_PUBLIC_KEY,
            current_time
        ), headers = {
            'Content-Type': 'application/octet-stream',
            'concent-client-public-key': b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii')
        }
    )
    time.sleep(10)

    api_request(
        cluster_url,
        'receive',
        CONCENT_PRIVATE_KEY,
        REQUESTOR_PUBLIC_KEY,
        headers = {
            'Content-Type': 'application/octet-stream',
            'concent-client-public-key': b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii')
        }
    )


if __name__ == '__main__':
    try:
        main()
    except requests.exceptions.ConnectionError as exception:
        print("\nERROR: Failed connect to the server.\n", file = sys.stderr)
        sys.exit(str(exception))
