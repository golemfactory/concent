#!/usr/bin/env python3

import hashlib
import os
import sys
import time
from datetime import datetime
from threading import Thread

import requests
from golem_messages.shortcuts import dump

from api_testing_common import api_request
from api_testing_common import assert_condition
from api_testing_common import count_fails
from api_testing_common import get_force_get_task_result
from api_testing_common import REQUESTOR_PRIVATE_KEY
from api_testing_common import run_tests
from common.helpers import get_current_utc_timestamp

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "concent_api.settings")

now = datetime.now()
testing_subtask_id = str(now.year) + str(now.month) + str(now.day) + str(now.hour) + str(now.minute) + str(now.second) + str(now.microsecond)

responses = []  # type: list

NUMBER_OF_TESTING_THREADS = 3
MAXIMUM_WAITING_TIME_FOR_ALL_RESPONSES = 5     # seconds


def multi_threads(number_of_threads: int):
    def call_function_in_threads(func):
        def wrapper(*args, **kwargs):
            for i in range(number_of_threads):
                t = Thread(target=func, args=(*args,), kwargs={**kwargs})
                t.start()

        return wrapper
    return call_function_in_threads


@count_fails
def test_case_that_multiple_requests_by_one_subtask_will_not_be_cause_of_server_error(cluster_consts, cluster_url, test_id):

    send_correct_request(cluster_consts=cluster_consts, cluster_url=cluster_url)

    end_time = time.time() + MAXIMUM_WAITING_TIME_FOR_ALL_RESPONSES
    while len(responses) != NUMBER_OF_TESTING_THREADS:
        time.sleep(0.1)
        if time.time() >= end_time:
            break

    print('Responses = ' + str(responses))

    assert_condition(
        actual=responses,
        expected=['AckForceGetTaskResult', 'ServiceRefused', 'ServiceRefused'],
        error_message="Responses should be: 'AckForceGetTaskResult', 'ServiceRefused', 'ServiceRefused'"
    )
    print('Test passed successfully')


@multi_threads(NUMBER_OF_TESTING_THREADS)
def send_correct_request(cluster_consts, cluster_url):
    current_time = get_current_utc_timestamp()
    (subtask_id, task_id) = (testing_subtask_id, '130')

    file_content = task_id
    file_size = len(file_content)
    file_check_sum = 'sha1:' + hashlib.sha1(file_content.encode()).hexdigest()

    data = dump(
        get_force_get_task_result(
            task_id,
            subtask_id,
            current_time,
            cluster_consts,
            size=file_size,
            package_hash=file_check_sum,
        ),
        REQUESTOR_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
    )

    response = api_request(
        cluster_url,
        'send',
        REQUESTOR_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        data,
        headers={
            'Content-Type': 'application/octet-stream',
        },
        expected_status=200,
        expected_content_type='application/octet-stream',
    )
    responses.append(response.__class__.__name__)


if __name__ == '__main__':
    try:
        from concent_api.settings import CONCENT_PUBLIC_KEY
        run_tests(globals())
    except requests.exceptions.ConnectionError as exception:
        print("\nERROR: Failed connect to the server.\n", file=sys.stderr)
        sys.exit(str(exception))
