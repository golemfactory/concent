from typing import Any
from typing import Callable
from typing import Iterable
from typing import Optional
from typing import Sequence
from typing import Tuple
from typing import Union

import argparse
import datetime
import http.client
import json
import requests
import sys
import uuid

from freezegun import freeze_time

from golem_messages.exceptions import MessageError
from golem_messages.factories.tasks import ComputeTaskDefFactory
from golem_messages.factories.tasks import TaskToComputeFactory
from golem_messages.message import Message
from golem_messages.message.concents import ClientAuthorization
from golem_messages.message.tasks import TaskToCompute
from golem_messages.shortcuts import dump
from golem_messages.shortcuts import load
from golem_messages.utils import encode_hex

from common.helpers import sign_message
from common.testing_helpers import generate_ecc_key_pair
from core.exceptions import UnexpectedResponse
from protocol_constants import get_protocol_constants
from protocol_constants import print_protocol_constants

(PROVIDER_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY) = generate_ecc_key_pair()
(REQUESTOR_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY) = generate_ecc_key_pair()

REQUESTOR_ETHEREUM_PRIVATE_KEY = b'}\xf3\xfc\x16ZUoM{h\xa9\xee\xfe_8\xbd\x02\x95\xc3\x8am\xd7\xff\x91R"\x1d\xb71\xed\x08\t'
REQUESTOR_ETHEREUM_PUBLIC_KEY = b'F\xdei\xa1\xc0\x10\xc8M\xce\xaf\xc0p\r\x8e\x8f\xb1` \x8d\xf7=\xa6\xb6\xbazL\xbbY\xd6:\xd5\x06\x8dP\xe7#\xb9\xbb\xf8T\xc73\xebH\x7f2\xcav\xb1\xd8w\xde\xdb\x89\xf0\xddD\xa5\xbf\x030\xf3\x96;'
PROVIDER_ETHEREUM_PRIVATE_KEY = b'\x1dJ\xaf_h\xe0Y#;p\xd7s>\xb4fOH\x19\xbc\x9e\xd1\xf4\t\xdf]!\x9c\xfe\x9f\x888x'
PROVIDER_ETHEREUM_PUBLIC_KEY = b'\x05\xa7w\xc6\x9b\x89<\xf8Rz\xef\xc4AwN}\xa0\x0e{p\xc8\xa7AF\xfc\xd26\xc1)\xdbgp\x8b]9\xfd\xaa]\xd5H@?F\x14\xdbU\x8b\x93\x8d\xf1\xfc/{s3\x8c\xc7\x80-,\x9d\x194u\x8d'


class TestAssertionException(Exception):
    pass


class count_fails(object):
    """
    Decorator that wraps a test functions for intercepting assertions and counting them.
    """
    instances = []  # type: ignore
    number_of_run_tests = 0

    def __init__(self, function: Callable) -> None:
        self._function = function
        self.__name__ = function.__name__
        self.failed = False
        count_fails.instances.append(self)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        try:
            print("Running TC: " + self.__name__)
            count_fails.number_of_run_tests += 1
            return self._function(*args, **kwargs)
        except TestAssertionException as exception:
            print("{}: FAILED".format(self.__name__))
            print(exception)
            self.failed = True

    @classmethod
    def get_fails(cls) -> int:
        return sum([instance.failed for instance in cls.instances])

    @classmethod
    def print_fails(cls) -> None:
        print(f'Total failed tests : {cls.get_fails()} out of {cls.number_of_run_tests}')


def assert_condition(actual: Any, expected: Any, error_message: str=None) -> None:
    message = error_message or f"Actual: {actual} != expected: {expected}"
    if actual != expected:
        raise TestAssertionException(message)


def assert_content_equal(actual: Iterable[str], expected: Iterable[str]) -> None:
    if sorted(actual) != sorted(expected):
        raise TestAssertionException(f'Content of iterables is not equal. "Actual: {actual}". "Expected: {expected}"')


def print_golem_message(message: Message, indent: int=4) -> None:
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


def validate_response_status(actual_status_code: int, expected_status: Optional[int]=None) -> None:
    if expected_status is not None:
        assert_condition(
            actual_status_code,
            expected_status,
            f"Expected:HTTP{expected_status}, actual:HTTP{actual_status_code}"
        )


def validate_response_message(
    encoded_message: bytes,
    expected_message_type: Message,
    private_key: bytes,
    public_key: bytes,
) -> None:
    if expected_message_type is not None:
        decoded_message = try_to_decode_golem_message(private_key, public_key, encoded_message)
        assert_condition(
            type(decoded_message),
            expected_message_type,
            f"Expected:{expected_message_type}, actual:{type(decoded_message)}",
        )


def validate_content_type(actual_content_type: str, expected_content_type: Optional[str]=None) -> None:
    if expected_content_type is not None:
        assert_condition(
            actual_content_type,
            expected_content_type,
            f"Wrong content type for Golem Message: {actual_content_type}"
        )


def api_request(
    host: str,
    endpoint: str,
    private_key: bytes,
    public_key: bytes,
    data: Optional[Message]=None,
    headers: Optional[dict]=None,
    expected_status: Optional[int]=None,
    expected_message_type: Optional[Message]=None,
    expected_content_type: Optional[str]=None
) -> Union[None, Message]:
    def _prepare_data(data: Optional[Union[bytes, str]]=None) -> Union[str, bytes]:
        if data is None:
            return ''
        if isinstance(data, bytes):
            return data
        return dump(
            data,
            private_key,
            public_key,
        )

    def _print_data(data: Optional[Union[bytes, str]], url: str) -> None:
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
    content_type = response.headers['Content-Type']
    if 'text/html' in content_type:
        return None
    elif content_type == 'json':
        return json.loads(response.content)
    elif content_type == 'application/octet-stream':
        return try_to_decode_golem_message(private_key, public_key, response.content)
    else:
        raise UnexpectedResponse(f'Unexpected response content_type. Response content type is {content_type}.')


def _print_response(private_key: bytes, public_key: bytes, response: requests.Response) -> None:
    if response.content is None:
        print('RESPONSE: <empty>')
    else:
        print(f'STATUS: {response.status_code} {http.client.responses[response.status_code]}')
        print('MESSAGE:')
        print(f'Concent-Golem-Messages-Version = {response.headers["concent-golem-messages-version"]}')
        if response.headers['Content-Type'] == 'application/octet-stream':
            _print_message_from_stream(private_key, public_key, response.content)
        elif response.headers['Content-Type'] == 'application/json':
            _print_message_from_json(response)
        elif response.headers['Content-Type'] == 'text/html; charset=utf-8':
            pass
        else:
            print('Unexpected content-type of response message')


def _print_message_from_json(response: requests.Response) -> None:
    try:
        print(response.json())
    except json.decoder.JSONDecodeError:
        print('RAW RESPONSE: Failed to decode response content')


def _print_message_from_stream(private_key: bytes, public_key: bytes, content: bytes) -> None:
    decoded_response = try_to_decode_golem_message(private_key, public_key, content)
    if decoded_response is None:
        print("ERROR: Decoded Golem Message is 'None'")
    else:
        print_golem_message(decoded_response)


def try_to_decode_golem_message(private_key: bytes, public_key: bytes, content: bytes) -> Message:
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


def timestamp_to_isoformat(timestamp: int) -> str:
    return datetime.datetime.fromtimestamp(timestamp).isoformat(' ')


def create_client_auth_message(client_priv_key: bytes, client_public_key: bytes, concent_public_key: bytes) -> bytes:
    client_auth = ClientAuthorization()
    client_auth.client_public_key = client_public_key
    return dump(client_auth, client_priv_key, concent_public_key)


def parse_command_line(command_line: list) -> str:
    if len(command_line) <= 1:
        sys.exit('Not enough arguments')

    if len(command_line) >= 3:
        sys.exit('Too many arguments')

    cluster_url = command_line[1]
    return cluster_url


def parse_arguments() -> Tuple:
    parser = argparse.ArgumentParser()
    parser.add_argument("cluster_url")
    parser.add_argument("tc_patterns", nargs='*')
    args = parser.parse_args()
    return (args.cluster_url, args.tc_patterns)


def get_tests_list(patterns: Sequence, all_objects: list) -> list:
    def _is_a_test(x: Sequence) -> bool:
        return "case_" in x

    tests = list(filter(lambda x: _is_a_test(x), all_objects))
    if len(patterns) > 0:
        safe_patterns = set(pattern for pattern in patterns if _is_a_test(pattern))
        tests = set(test for pattern in safe_patterns for test in tests if pattern in test)  # type: ignore
    return sorted(tests)


def execute_tests(tests_to_execute: list, objects: dict, **kwargs: Any) -> None:
    tests = [objects[name] for name in tests_to_execute]
    for test in tests:
        test(task_id=str(uuid.uuid4()), subtask_id=str(uuid.uuid4()), **kwargs)
        print("-" * 80)


def run_tests(objects: dict, additional_arguments: Optional[dict]=None) -> None:
    if additional_arguments is None:
        additional_arguments = {}
    (cluster_url, patterns) = parse_arguments()
    cluster_consts = get_protocol_constants(cluster_url)
    print_protocol_constants(cluster_consts)
    tests_to_execute = get_tests_list(patterns, list(objects.keys()))
    print("Tests to be executed: \n * " + "\n * ".join(tests_to_execute))
    print()
    execute_tests(
        tests_to_execute=tests_to_execute,
        objects=objects,
        cluster_url=cluster_url,
        cluster_consts=cluster_consts,
        **additional_arguments
    )
    if count_fails.get_fails() > 0:
        count_fails.print_fails()
    print("END")


def _get_provider_hex_public_key() -> str:
    """ Returns provider hex public key """
    return encode_hex(PROVIDER_PUBLIC_KEY)


def _get_requestor_hex_public_key() -> str:
    return encode_hex(REQUESTOR_PUBLIC_KEY)


def create_signed_task_to_compute(
    task_id: str,
    subtask_id: str,
    deadline: int,
    timestamp: Optional[Union[datetime.datetime, str]]=None,
    provider_public_key: Optional[bytes]=None,
    requestor_public_key: Optional[bytes]=None,
    requestor_ethereum_public_key: Optional[bytes]=None,
    requestor_ethereum_private_key: Optional[bytes]=None,
    provider_ethereum_public_key: Optional[bytes]=None,
    price: int=0,
    size: int=1,
    package_hash: str='sha1:57786d92d1a6f7eaaba1c984db5e108c68b03f0d',
    script_src: Optional[str]=None,
) -> TaskToCompute:
    with freeze_time(timestamp):
        compute_task_def = ComputeTaskDefFactory(
            task_id=task_id,
            subtask_id=subtask_id,
            deadline=deadline,
            extra_data={
                'output_format': 'png',
                'scene_file': '/golem/resources/golem-header-light.blend',
                'frames': [1],
                'script_src': script_src,
            }
        )
        if script_src is not None:
            compute_task_def['extra_data']['script_src'] = script_src
        task_to_compute = TaskToComputeFactory(
            provider_public_key=provider_public_key if provider_public_key is not None else _get_provider_hex_public_key(),
            requestor_public_key=requestor_public_key if requestor_public_key is not None else _get_requestor_hex_public_key(),
            compute_task_def=compute_task_def,
            requestor_ethereum_public_key=encode_hex(requestor_ethereum_public_key) if requestor_ethereum_public_key is not None else encode_hex(REQUESTOR_ETHEREUM_PUBLIC_KEY),
            provider_ethereum_public_key=encode_hex(provider_ethereum_public_key) if provider_ethereum_public_key is not None else encode_hex(PROVIDER_ETHEREUM_PUBLIC_KEY),
            price=price,
            size=size,
            package_hash=package_hash,
        )
        task_to_compute.generate_ethsig(
            requestor_ethereum_private_key if requestor_ethereum_private_key is not None else REQUESTOR_ETHEREUM_PRIVATE_KEY
        )
        task_to_compute = sign_message(task_to_compute, REQUESTOR_PRIVATE_KEY)
        return task_to_compute
