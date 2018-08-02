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
from api_testing_common import get_force_get_task_result
from api_testing_common import REQUESTOR_PRIVATE_KEY
from api_testing_common import run_tests
from common.helpers import get_current_utc_timestamp

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "concent_api.settings")

now = datetime.now()
testing_subtask_id = str(now.year) + str(now.month) + str(now.day) + str(now.hour) + str(now.minute) + str(
    now.second) + str(now.microsecond)

responses = []


def multiprocess(func):
    def wrapper(*args, **kwargs):
        for i in range(3):
            t = Thread(target=func, args=(*args,), kwargs={**kwargs})
            t.start()

    return wrapper


def test_case_that_multiple_requests_by_one_subtask_will_not_be_cause_of_server_error(cluster_consts, cluster_url, test_id):

    send_correct_request(cluster_consts=cluster_consts, cluster_url=cluster_url)

    time.sleep(4)
    print('Responses = ' + str(responses))
    assert 'AckForceGetTaskResult' in responses
    responses.remove('AckForceGetTaskResult')
    assert all(x == 'ServiceRefused' for x in responses)
    print('Test passed successfully')


@multiprocess
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
