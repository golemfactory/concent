import argparse
import random
import sys

from freezegun import freeze_time

from golem_messages.exceptions      import MessageError
from golem_messages.factories.tasks import ComputeTaskDefFactory
from golem_messages.factories.tasks import TaskToComputeFactory
from golem_messages.message import Message
from golem_messages.message.concents import ClientAuthorization
from golem_messages.shortcuts       import dump
from golem_messages.shortcuts       import load
from golem_messages.utils import encode_hex

import datetime
import json
import requests
import http.client

from protocol_constants import get_protocol_constants
from protocol_constants import print_protocol_constants
from utils.helpers import sign_message
from utils.testing_helpers import generate_ecc_key_pair

(PROVIDER_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY)  = generate_ecc_key_pair()
(REQUESTOR_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY) = generate_ecc_key_pair()

REQUESTOR_ETHEREUM_PUBLIC_KEY = '46de69a1c010c84dceafc0700d8e8fb160208df73da6b6ba7a4cbb59d63ad5068d50e723b9bbf854c733eb487f32ca76b1d877dedb89f0dd44a5bf0330f3963b'
PROVIDER_ETHEREUM_PUBLIC_KEY = '05a777c69b893cf8527aefc441774e7da00e7b70c8a74146fcd236c129db67708b5d39fdaa5dd548403f4614db558b938df1fc2f7b73338cc7802d2c9d1934758d'


class TestAssertionException(Exception):
    pass


class count_fails(object):
    """
    Decorator that wraps a test functions for intercepting assertions and counting them.
    """
    instances = []  # type: ignore
    number_of_run_tests = 0

    def __init__(self, function):
        self._function     = function
        self.__name__ = function.__name__
        self.failed  = False
        count_fails.instances.append(self)

    def __call__(self, *args, **kwargs):
        try:
            print("Running TC: " + self.__name__)
            count_fails.number_of_run_tests += 1
            return self._function(*args, **kwargs)
        except TestAssertionException as exception:
            print("{}: FAILED".format(self.__name__))
            print(exception)
            self.failed = True

    @classmethod
    def get_fails(cls):
        return sum([instance.failed for instance in cls.instances])

    @classmethod
    def print_fails(cls):
        print(f'Total failed tests : {cls.get_fails()} out of {cls.number_of_run_tests}')


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
        if isinstance(data, bytes):
            return data
        return dump(
            data,
            private_key,
            public_key,
        )

    def _print_data(data, url):
        if data is None:
            print('RECEIVE ({})'.format(url))

        elif isinstance(data, bytes):
            print('RECEIVE ({})'.format(url))

        else:
            print('SEND ({})'.format(url))
            print('MESSAGE:')
            print_golem_message(data)

    assert all(value not in ['', None] for value in [endpoint, host, headers])
    url = "{}/api/v1/{}/".format(host, endpoint)

    _print_data(data, url)
    response = requests.post("{}".format(url), headers=headers, data=_prepare_data(data), verify=False)
    _print_response(private_key, public_key, response)
    validate_response_status(response.status_code, expected_status)
    validate_content_type(response.headers['Content-Type'], expected_content_type)
    validate_response_message(response.content, expected_message_type, private_key, public_key)
    print()
    if response.status_code in [202, 204]:
        return None
    else:
        return try_to_decode_golem_message(private_key, public_key, response.content)


def _print_response(private_key, public_key, response):
    if response.content is None:
        print('RESPONSE: <empty>')
    elif len(response.content) != 0:
        _print_message_from_response(private_key, public_key, response)
    else:
        print('STATUS: {} {}'.format(response.status_code, http.client.responses[response.status_code]))
        if response.text not in ['', None]:
            print('RAW RESPONSE (text): {}'.format(response.text))


def _print_message_from_response(private_key, public_key, response):
    print('STATUS: {} {}'.format(response.status_code, http.client.responses[response.status_code]))
    print('MESSAGE:')
    print('Concent-Golem-Messages-Version = {}'.format(response.headers['concent-golem-messages-version']))
    if response.headers['Content-Type'] == 'application/octet-stream':
        _print_message_from_stream(private_key, public_key, response.content)
    elif response.headers['Content-Type'] == 'application/json':
        _print_message_from_json(response)
    else:
        print('ERROR: Unexpected content-type of response message')


def _print_message_from_json(response):
    try:
        print(response.json())
    except json.decoder.JSONDecodeError:
        print('RAW RESPONSE: Failed to decode response content')


def _print_message_from_stream(private_key, public_key, content):
    decoded_response = try_to_decode_golem_message(private_key, public_key, content)
    if decoded_response is None:
        print("ERROR: Decoded Golem Message is 'None'")
    else:
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


def create_client_auth_message(client_priv_key, client_public_key, concent_public_key):  # pylint: disable=no-self-use
    client_auth = ClientAuthorization()
    client_auth.client_public_key = client_public_key
    return dump(client_auth, client_priv_key, concent_public_key)


def parse_command_line(command_line):
    if len(command_line) <= 1:
        sys.exit('Not enough arguments')

    if len(command_line) >= 3:
        sys.exit('Too many arguments')

    cluster_url = command_line[1]
    return cluster_url


def get_task_id_and_subtask_id(test_id, case_name):
    task_id = f'task_{case_name}_{test_id}'
    subtask_id = 'sub_' + task_id
    return (subtask_id, task_id)


def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("cluster_url")
    parser.add_argument("tc_patterns", nargs='*')
    args = parser.parse_args()
    return (args.cluster_url, args.tc_patterns)


def get_tests_list(patterns, all_objects):
    def _is_a_test(x):
        return "case_" in x

    tests = list(filter(lambda x: _is_a_test(x), all_objects))
    if len(patterns) > 0:
        safe_patterns = set(pattern for pattern in patterns if _is_a_test(pattern))
        tests = set(test for pattern in safe_patterns for test in tests if pattern in test)
    return sorted(tests)


def execute_tests(tests_to_execute, objects, **kwargs):
    tests = [objects[name] for name in tests_to_execute]
    for test in tests:
        test_id = kwargs['test_id'] + test.__name__
        kw = {k: v for k, v in kwargs.items() if k != 'test_id'}
        test(test_id=test_id, **kw)
        print("-" * 80)


def run_tests(objects, additional_arguments=None):
    if additional_arguments is None:
        additional_arguments = {}
    (cluster_url, patterns) = parse_arguments()
    cluster_consts = get_protocol_constants(cluster_url)
    print_protocol_constants(cluster_consts)
    test_id = str(random.randrange(1, 100000))
    tests_to_execute = get_tests_list(patterns, list(objects.keys()))
    print("Tests to be executed: \n * " + "\n * ".join(tests_to_execute))
    print()
    execute_tests(
        tests_to_execute=tests_to_execute,
        objects=objects,
        cluster_url=cluster_url,
        test_id=test_id,
        cluster_consts=cluster_consts,
        **additional_arguments
    )
    if count_fails.get_fails() > 0:
        count_fails.print_fails()
    print("END")


def _get_provider_hex_public_key():
    """ Returns provider hex public key """
    return encode_hex(PROVIDER_PUBLIC_KEY)


def _get_requestor_hex_public_key():
    return encode_hex(REQUESTOR_PUBLIC_KEY)


def create_signed_task_to_compute(
    task_id,
    subtask_id,
    deadline,
    timestamp=None,
    provider_public_key=None,
    requestor_public_key=None,
    requestor_ethereum_public_key=REQUESTOR_ETHEREUM_PUBLIC_KEY,
    provider_ethereum_public_key=PROVIDER_ETHEREUM_PUBLIC_KEY,
    price=0
):
    with freeze_time(timestamp):
        compute_task_def = ComputeTaskDefFactory(
            task_id=task_id,
            subtask_id=subtask_id,
            deadline= deadline,
        )
        task_to_compute = TaskToComputeFactory(
            provider_public_key=provider_public_key if provider_public_key is not None else _get_provider_hex_public_key(),
            requestor_public_key=requestor_public_key if requestor_public_key is not None else _get_requestor_hex_public_key(),
            compute_task_def=compute_task_def,
            requestor_ethereum_public_key=requestor_ethereum_public_key,
            provider_ethereum_public_key=provider_ethereum_public_key,
            price=price,
            size=1,
        )
        sign_message(task_to_compute, REQUESTOR_PRIVATE_KEY)
        return task_to_compute
