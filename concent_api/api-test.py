#!/usr/bin/env python3

import sys
import datetime
import random

import http.client
from base64                         import b64encode

from golem_messages.message         import AckReportComputedTask
from golem_messages.message         import CannotComputeTask
from golem_messages.message         import ComputeTaskDef
from golem_messages.message         import ForceReportComputedTask
from golem_messages.message         import Message
from golem_messages.message         import TaskToCompute
from golem_messages.message         import RejectReportComputedTask
from golem_messages.shortcuts       import dump
from golem_messages.shortcuts       import load

from utils.testing_helpers          import generate_ecc_key_pair

import requests

(PROVIDER_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY)  = generate_ecc_key_pair()
(REQUESTOR_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY) = generate_ecc_key_pair()

CONCENT_PUBLIC_KEY  = b'\xf3\x97\x19\xcdX\xda\x86tiP\x1c&\xd39M\x9e\xa4\xddb\x89\xb5,]O\xd5cR\x84\xb85\xed\xc9\xa17e,\xb2s\xeb\n1\xcaN.l\xba\xc3\xb7\xc2\xba\xff\xabN\xde\xb3\x0b\xa6l\xbf6o\x81\xe0;'
CONCENT_PRIVATE_KEY = b'l\xcdh\x19\xeb$>\xbcG\xa1\xc7v\xe8\xd7o\x0c\xbf\x0e\x0fM\x89lw\x1e\xd7K\xd6Hnv$\xa2'


def create_data(message_type, task_id):
    assert task_id >= 0
    assert isinstance(task_id, int)

    current_time = int(datetime.datetime.now().timestamp())

    compute_task_def = ComputeTaskDef()
    compute_task_def['task_id']     = task_id
    compute_task_def['deadline']    = current_time + 6000
    task_to_compute = TaskToCompute(
        timestamp = current_time,
        compute_task_def = compute_task_def
    )

    # sign task_to_compute message with PROVIDER sig

    serialized_task_to_compute      = dump(task_to_compute,             REQUESTOR_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY)
    deserialized_task_to_compute    = load(serialized_task_to_compute,  PROVIDER_PRIVATE_KEY,   REQUESTOR_PUBLIC_KEY, check_time = False)

    if message_type == 'ForceReportComputedTask':
        force_report_computed_task = ForceReportComputedTask(
            timestamp = current_time
        )
        force_report_computed_task.task_to_compute = deserialized_task_to_compute

        return force_report_computed_task

    elif message_type == 'AckReportComputedTask':
        ack_report_computed_task = AckReportComputedTask(
            timestamp = current_time
        )
        ack_report_computed_task.task_to_compute = deserialized_task_to_compute

        return ack_report_computed_task

    else:
        assert False, 'Invalid message type'

    return None


def create_reject_data(task_id):
    assert task_id >= 0
    assert isinstance(task_id, int)

    cannot_compute_task = CannotComputeTask()
    cannot_compute_task.task_to_compute = TaskToCompute()
    cannot_compute_task.task_to_compute.compute_task_def = ComputeTaskDef()
    cannot_compute_task.task_to_compute.compute_task_def['task_id'] = task_id
    cannot_compute_task.reason = CannotComputeTask.REASON.WrongKey

    serialized_cannot_compute_task      = dump(cannot_compute_task,             PROVIDER_PRIVATE_KEY,   REQUESTOR_PUBLIC_KEY)
    deserialized_cannot_compute_task    = load(serialized_cannot_compute_task,  REQUESTOR_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY, check_time=False)

    reject_report_computed_task = RejectReportComputedTask()
    reject_report_computed_task.cannot_compute_task = deserialized_cannot_compute_task
    reject_report_computed_task.reason              = RejectReportComputedTask.Reason.TASK_TIME_LIMIT_EXCEEDED
    reject_report_computed_task.task_to_compute     = None
    reject_report_computed_task.task_failure        = None

    return reject_report_computed_task


def print_golem_message(message, PRIVATE_KEY, PUBLIC_KEY, indent = 4):
    assert isinstance(message, Message)
    HEADER_FIELDS  = ['timestamp', 'encrypted', 'sig']
    PRIVATE_FIELDS = {'subtask_id', 'result_hash', '_payload', '_raw'}

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
                    PRIVATE_KEY,
                    PUBLIC_KEY,
                    check_time=False,
                )
            except AttributeError:
                # FIXME: golem-messages provides no reliable way to discern invalid messages from other AttributeErrors.
                print('{}{:30} = <BINARY DATA>'.format(' ' * indent, field))
            else:
                print('{}{:30} ='.format(' ' * indent, field))
                print_golem_message(nested_message, PRIVATE_KEY, PUBLIC_KEY, indent = indent + 4)
        else:
            if isinstance(value, Message):
                if message.task_to_compute is not None:
                    print_golem_message(message.task_to_compute, PRIVATE_KEY, PUBLIC_KEY, indent = indent + 4)
                else:
                    print_golem_message(message.cannot_compute_task, PRIVATE_KEY, PUBLIC_KEY, indent = indent + 4)
            else:
                print('{}{:30} = {}'.format(' ' * indent, field, value))


def api_request(host, endpoint, PRIVATE_KEY, PUBLIC_KEY, data = None, headers = None):
    assert all(value not in ['', None] for value in [endpoint, host, headers])
    url = "{}/api/v1/{}/".format(host, endpoint)

    if data is None:
        print('RECEIVE ({})'.format(url))
    else:
        print('SEND ({})'.format(url))
        print('MESSAGE:')
        print_golem_message(data, PRIVATE_KEY, PUBLIC_KEY)

        data = dump(
            data,
            PRIVATE_KEY,
            PUBLIC_KEY,
        )
    if data is None:
        response = requests.post("{}".format(url), headers = headers)
    else:
        response = requests.post("{}".format(url), headers = headers, data = data)

    if len(response.content) != 0:

        decoded_response = load(
            response.content,
            PRIVATE_KEY,
            PUBLIC_KEY,
            check_time=False,
        )
        print('STATUS: {} {}'.format(response.status_code, http.client.responses[response.status_code]))
        print('MESSAGE:')
        print_golem_message(decoded_response, PRIVATE_KEY, PUBLIC_KEY)
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

    api_request(
        cluster_url,
        'send',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        create_data('ForceReportComputedTask', task_id), {
            'Content-Type': 'application/octet-stream',
            'concent-client-public-key':    b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            'additional-client-public-key': b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii')
        },
    )

    api_request(
        cluster_url,
        'receive',
        CONCENT_PRIVATE_KEY,
        PROVIDER_PUBLIC_KEY,
        headers = {
            'Content-Type': 'application/octet-stream',
            'concent-client-public-key':    b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            'additional-client-public-key': b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii')
        }
    )

    api_request(
        cluster_url,
        'send',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        create_data('AckReportComputedTask', task_id), {
            'Content-Type': 'application/octet-stream',
            'concent-client-public-key':    b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            'additional-client-public-key': b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii')
        }
    )

    api_request(
        cluster_url,
        'receive',
        CONCENT_PRIVATE_KEY,
        PROVIDER_PUBLIC_KEY,
        headers = {
            'Content-Type': 'application/octet-stream',
            'concent-client-public-key':    b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            'additional-client-public-key': b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii')
        }
    )

    api_request(
        cluster_url,
        'send',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        create_data('ForceReportComputedTask', task_id + 1), {
            'Content-Type': 'application/octet-stream',
            'concent-client-public-key':    b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            'additional-client-public-key': b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii')
        }
    )

    api_request(
        cluster_url,
        'receive',
        CONCENT_PRIVATE_KEY,
        PROVIDER_PUBLIC_KEY,
        headers = {
            'Content-Type': 'application/octet-stream',
            'concent-client-public-key':    b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            'additional-client-public-key': b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii')
        }
    )

    api_request(
        cluster_url,
        'send',
        REQUESTOR_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        create_reject_data(task_id + 1), {
            'Content-Type': 'application/octet-stream',
            'concent-client-public-key':    b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            'additional-client-public-key': b64encode(PROVIDER_PUBLIC_KEY).decode('ascii')
        }
    )

    api_request(
        cluster_url,
        'receive',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        headers = {
            'Content-Type': 'application/octet-stream',
            'concent-client-public-key':    b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            'additional-client-public-key': b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
        }
    )


if __name__ == '__main__':
    try:
        main()
    except requests.exceptions.ConnectionError as exception:
        print("\nERROR: Failed connect to the server.\n", file = sys.stderr)
        sys.exit(str(exception))
