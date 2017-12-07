#!/usr/bin/env python3

import sys
import json
import datetime
import random

import requests


DEFAULT_HEADERS = {
    'Content-Type':              'application/json',
    'concent-client-public-key': '85cZzVjahnRpUBwm0zlNnqTdYom1LF1P1WNShLg17cmhN2UssnPrCjHKTi5susO3wrr/q07eswumbL82b4HgOw==',
}


def create_data(message_type, task_id):
    current_time = int(datetime.datetime.now().timestamp())
    data = {
        "type":         message_type,
        "timestamp":    current_time,
        "message_task_to_compute": {
            "type":         "MessageTaskToCompute",
            "timestamp":    current_time,
            "task_id":      task_id,
            "deadline":     current_time + 6000
        }
    }
    return data


def create_reject_data(message_type, task_id):
    current_time = int(datetime.datetime.now().timestamp())
    data = {
        "type":         "MessageRejectReportComputedTask",
        "timestamp":    current_time,
        "reason":       "cannot-compute-task",
        "message_cannot_commpute_task": {
            "type":         "MessageCannotComputeTask",
            "timestamp":    current_time,
            "reason":       "provider-quit",
            "task_id":      task_id
        }
    }
    return data


def api_request(host, endpoint, data = None, headers = None):
    if headers is None:
        headers = DEFAULT_HEADERS

    if data is None:
        print('Receive message:')
    else:
        print('Send message {}:'.format(data['type']))
    print("{}/api/v1/{}/".format(host, endpoint))

    if data is None:
        response = requests.post("{}/api/v1/{}/".format(host, endpoint), headers = headers)
    else:
        response = requests.post("{}/api/v1/{}/".format(host, endpoint), headers = headers, data = json.dumps(data))

    try:
        decoded_response = response.json()
    except json.JSONDecodeError:
        decoded_response = response.text
        print(response, decoded_response)
    else:
        print(response, json.dumps(decoded_response, indent = 4))
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
    task_id     = random.randrange(1, 1000)

    api_request(cluster_url, 'send',    create_data('MessageForceReportComputedTask', task_id))
    api_request(cluster_url, 'receive')
    api_request(cluster_url, 'send',    create_data('MessageAckReportComputedTask', task_id))
    api_request(cluster_url, 'receive')

    api_request(cluster_url, 'send',    create_data('MessageForceReportComputedTask', task_id + 1))
    api_request(cluster_url, 'receive')
    api_request(cluster_url, 'send',    create_reject_data('MessageRejectReportComputedTask', task_id + 1))
    api_request(cluster_url, 'receive')


if __name__ == '__main__':
    try:
        main()
    except requests.exceptions.ConnectionError as exception:
        print("\nERROR: Failed connect to the server.\n", file = sys.stderr)
        sys.exit(str(exception))
