from typing import Any
from typing import Dict
from typing import Callable
from typing import Iterable
from typing import MutableMapping
from typing import Optional
from typing import Sequence
from typing import Tuple
from typing import Type
from typing import Union

from threading import Thread
import argparse
import datetime
import http.client
import json
import requests

from freezegun import freeze_time

from django.conf import settings

from golem_messages import message
from golem_messages.datastructures.tasks import TaskHeader
from golem_messages.exceptions import MessageError
from golem_messages.factories.datastructures.tasks import TaskHeaderFactory
from golem_messages.factories.tasks import ComputeTaskDefFactory
from golem_messages.factories.tasks import TaskToComputeFactory
from golem_messages.factories.tasks import WantToComputeTaskFactory
from golem_messages.message import Message
from golem_messages.message.concents import ClientAuthorization
from golem_messages.message.tasks import TaskToCompute
from golem_messages.shortcuts import dump
from golem_messages.shortcuts import load
from golem_messages.utils import encode_hex

from common.helpers import parse_timestamp_to_utc_datetime
from common.helpers import sign_message
from common.testing_helpers import generate_ecc_key_pair
from concent_api.settings import GOLEM_MESSAGES_VERSION
from core.exceptions import UnexpectedResponse
from core.utils import calculate_maximum_download_time
from protocol_constants import get_protocol_constants
from protocol_constants import print_protocol_constants
from sci_testing_common import SCIBaseTest

(PROVIDER_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY) = generate_ecc_key_pair()
(REQUESTOR_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY) = generate_ecc_key_pair()

REQUEST_HEADERS = {
    'Content-Type': 'application/octet-stream',
    'X-Golem-Messages': GOLEM_MESSAGES_VERSION
}

REPORT_COMPUTED_TASK_SIZE = 10


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
    expected_message_type: Optional[Type[Message]],
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


def validate_golem_version(actual_golem_version: str, expected_golem_version: str) -> None:
    assert_condition(
        '.'.join(actual_golem_version.split('.')[:-1]),
        '.'.join(expected_golem_version.split('.')[:-1]),
        f"Expected Golem Message version: {'.'.join(expected_golem_version.split('.')[:-1])}.X, "
        f"actual version: {actual_golem_version}"
    )


def validate_error_code(actual_error_code: str, expected_error_code: str) -> None:
    assert_condition(
        actual_error_code,
        expected_error_code,
        f"Expected error code: {expected_error_code}, actual error: {actual_error_code}"
    )


def api_request(
    host: str,
    endpoint: str,
    private_key: bytes,
    public_key: bytes,
    data: Union[Message, bytes],
    headers: Optional[dict]=None,
    expected_status: Optional[int]=None,
    expected_message_type: Optional[Type[Message]]=None,
    expected_content_type: Optional[str]=None,
    expected_golem_version: Optional[str]=None,
    expected_error_code: Optional[str]=None,
) -> Union[None, Message]:
    def _prepare_data(data: Union[Message, bytes]) -> bytes:
        if isinstance(data, bytes):
            return data
        return dump(
            data,
            private_key,
            public_key,
        )

    def _print_data(data: Union[Message, bytes], url: str) -> None:
        if isinstance(data, bytes):
            print('RECEIVE ({})'.format(url))

        else:
            print('SEND ({})'.format(url))
            print('MESSAGE:')
            print_golem_message(data)
    if headers is None:
        headers = REQUEST_HEADERS
        if expected_golem_version is not None:
            headers['X-Golem-Messages'] = expected_golem_version
    assert all(value not in ['', None] for value in [endpoint, host, REQUEST_HEADERS])
    url = "{}/api/v1/{}/".format(host, endpoint)
    _print_data(data, url)
    response = requests.post("{}".format(url), headers=headers, data=_prepare_data(data), verify=False)
    _print_response(private_key, public_key, response)
    validate_response_status(response.status_code, expected_status)
    validate_content_type(response.headers['Content-Type'], expected_content_type)
    validate_response_message(response.content, expected_message_type, private_key, public_key)
    if expected_golem_version is not None and 'Concent-Golem-Messages-Version' in response.headers:
        validate_golem_version(response.headers['Concent-Golem-Messages-Version'], expected_golem_version)
    print()
    content_type = response.headers['Content-Type']
    if 'text/html' in content_type:
        return None
    elif content_type == 'application/json' and expected_error_code is not None:
        validate_error_code((json.loads(response.content))['error_code'], expected_error_code)
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
        if response.headers['Content-Type'] == 'application/octet-stream':
            _print_message_from_stream(private_key, public_key, response.content, response.headers)
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


def _print_message_from_stream(
    private_key: bytes,
    public_key: bytes,
    content: bytes,
    headers: MutableMapping[str, str]
) -> None:
    decoded_response = try_to_decode_golem_message(private_key, public_key, content)
    if decoded_response is None:
        print("ERROR: Decoded Golem Message is 'None'")
    else:
        print('MESSAGE:')
        print(f'Concent-Golem-Messages-Version = {headers["concent-golem-messages-version"]}')
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
    return parse_timestamp_to_utc_datetime(timestamp).isoformat(' ')


def create_client_auth_message(client_priv_key: bytes, client_public_key: bytes, concent_public_key: bytes) -> bytes:
    client_auth = ClientAuthorization()
    client_auth.client_public_key = client_public_key
    return dump(client_auth, client_priv_key, concent_public_key)


def parse_arguments() -> Tuple:
    parser = argparse.ArgumentParser()
    parser.add_argument("cluster_url")
    parser.add_argument("tc_patterns", nargs='*')
    parser.add_argument(
        '-v1',
        '--concent-1-golem-messages-version',
        type=str,
        help=f'First version of golem messages to check.',
    )
    parser.add_argument(
        '-v2',
        '--concent-2-golem-messages-version',
        type=str,
        help=f'Second version of golem messages to check.',
    )
    parser.add_argument(
        '--full_sci',
        action='store_true',
        help='To initiate full SCIBase to test add --full_sci flag')
    args = parser.parse_args()
    return (
        args.cluster_url,
        args.tc_patterns,
        args.concent_1_golem_messages_version,
        args.concent_2_golem_messages_version,
        args.full_sci
    )


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
        test(**kwargs)
        print("-" * 80)


def run_tests(objects: dict, additional_arguments: Optional[dict]=None) -> int:
    if additional_arguments is None:
        additional_arguments = {}
    (cluster_url, patterns, concent_1_golem_messages_version, concent_2_golem_messages_version, init_new_users_accounts) = parse_arguments()
    if concent_1_golem_messages_version is not None and concent_2_golem_messages_version is not None:
        if concent_1_golem_messages_version == concent_2_golem_messages_version:
            raise TestAssertionException("Use different versions of golem messages to check supportability")
        additional_arguments['concent_1_golem_messages_version'] = concent_1_golem_messages_version
        additional_arguments['concent_2_golem_messages_version'] = concent_1_golem_messages_version
    cluster_consts = get_protocol_constants(cluster_url)
    print_protocol_constants(cluster_consts)
    tests_to_execute = get_tests_list(patterns, list(objects.keys()))
    objects['sci_base'] = SCIBaseTest(cluster_url, init_new_users_accounts)
    print("Tests to be executed: \n * " + "\n * ".join(tests_to_execute))
    print()
    execute_tests(
        tests_to_execute=tests_to_execute,
        objects=objects,
        cluster_url=cluster_url,
        cluster_consts=cluster_consts,
        **additional_arguments
    )
    number_of_failed_tests = count_fails.get_fails()
    if number_of_failed_tests > 0:
        count_fails.print_fails()
    objects['sci_base'].requestor_sci.stop()
    objects['sci_base'].provider_sci.stop()
    print("END")
    status_code = int(number_of_failed_tests > 0)
    return status_code


def _get_provider_hex_public_key() -> str:
    """ Returns provider hex public key """
    return encode_hex(PROVIDER_PUBLIC_KEY)


def _get_requestor_hex_public_key() -> str:
    return encode_hex(REQUESTOR_PUBLIC_KEY)


def create_signed_task_to_compute(
    deadline: int,
    timestamp: Optional[Union[datetime.datetime, str]]=None,
    provider_public_key: Optional[bytes]=None,
    provider_private_key: Optional[bytes]=None,
    requestor_public_key: Optional[bytes]=None,
    requestor_private_key: Optional[bytes]=None,
    price: int=1,
    size: int=1,
    package_hash: str='sha1:57786d92d1a6f7eaaba1c984db5e108c68b03f0d',
    render_parameters: Optional[Dict[str, Any]]=None,
) -> TaskToCompute:
    # Temporary workaround for requestor's and provider's keys until all Concent use cases will have payments
    # When we will have payments then all keys will be taken from SCIBaseTest class
    if provider_public_key is None and provider_private_key is None:
        provider_public_key = PROVIDER_PUBLIC_KEY
        provider_private_key = PROVIDER_PRIVATE_KEY
    if requestor_public_key is None and requestor_private_key is None:
        requestor_public_key = REQUESTOR_PUBLIC_KEY
        requestor_private_key = REQUESTOR_PRIVATE_KEY

    with freeze_time(timestamp):
        compute_task_def = ComputeTaskDefFactory(
            deadline=deadline,
            extra_data={
                'output_format': 'png',
                'scene_file': '/golem/resources/golem-header-light.blend',
                'frames': [1],
                'resolution': render_parameters.get('resolution') if render_parameters is not None else [400, 400],
                'use_compositing': render_parameters.get('use_compositing') if render_parameters is not None else False,
                'samples': render_parameters.get('samples') if render_parameters is not None else 0,
                'crops': [
                    {
                        'borders_x': render_parameters['borders_x'] if render_parameters is not None else [0.0, 1.0],
                        'borders_y': render_parameters['borders_y'] if render_parameters is not None else [0.0, 1.0],
                    }
                ]
            }
        )

        task_header: TaskHeader = TaskHeaderFactory(
            task_id=compute_task_def['task_id'],
            sign__privkey=requestor_private_key,
        )

        want_to_compute_task = WantToComputeTaskFactory(
            provider_public_key=encode_hex(provider_public_key),
            task_header=task_header,
            sign__privkey=provider_private_key
        )

        task_to_compute = TaskToComputeFactory(
            requestor_public_key=encode_hex(requestor_public_key),
            compute_task_def=compute_task_def,
            want_to_compute_task=want_to_compute_task,
            requestor_ethereum_public_key=encode_hex(requestor_public_key),
            price=price,
            size=size,
            package_hash=package_hash,
        )
        task_to_compute.generate_ethsig(requestor_private_key)
        task_to_compute.sign_all_promissory_notes(
            deposit_contract_address=settings.GNT_DEPOSIT_CONTRACT_ADDRESS,
            private_key=requestor_private_key,
        )
        signed_task_to_compute: TaskToCompute = sign_message(task_to_compute, requestor_private_key)  # type: ignore
        return signed_task_to_compute


def call_function_in_threads(
    func: Callable,
    number_of_threads: int,
    *args: Any,
    **kwargs: Any,
) -> None:
    for _ in range(number_of_threads):
        thread = Thread(target=func, args=args, kwargs=kwargs)
        thread.start()


def create_signed_subtask_results_accepted(
    requestor_private_key: bytes,
    payment_ts: int,
    report_computed_task: message.tasks.ReportComputedTask,
    timestamp: Optional[str] = None,
) -> message.tasks.SubtaskResultsAccepted:
    with freeze_time(timestamp):
        signed_message: message.tasks.SubtaskResultsAccepted = sign_message(
            message.tasks.SubtaskResultsAccepted(
                payment_ts=payment_ts,
                report_computed_task=report_computed_task,
            ),
            requestor_private_key,
        )
        return signed_message


def create_signed_report_computed_task(
    provider_private_key: bytes,
    task_to_compute: message.tasks.TaskToCompute,
    timestamp: Optional[str] = None
) -> message.tasks.ReportComputedTask:
    with freeze_time(timestamp):
        signed_message: message.tasks.ReportComputedTask = sign_message(
            message.tasks.ReportComputedTask(
                task_to_compute=task_to_compute,
                size=REPORT_COMPUTED_TASK_SIZE,
            ),
            provider_private_key,
        )
        return signed_message


def receive_all_left_pending_responses(
    host: str,
    endpoint: str,
    client_private_key: bytes,
    client_public_key: bytes,
    concent_public_key: bytes,
    client_name: str,
) -> None:
    url = f"{host}/api/v1/{endpoint}/"
    status_code = 200
    received_messages = []
    while status_code == 200:
        response = requests.post(f"{url}", headers=REQUEST_HEADERS, data=create_client_auth_message(client_private_key, client_public_key, concent_public_key), verify=False)
        status_code = response.status_code
        if status_code == 200:
            if isinstance(response.content, bytes) and response.headers['Content-Type'] == 'application/octet-stream':
                received_messages.append(load(response.content, client_private_key, concent_public_key).__class__.__name__)

    if len(received_messages) > 0:
        print(f'Concent had {len(received_messages)} messages which waited for {client_name} to receive. Name of these messages: {received_messages}')
    else:
        print(f'Concent had not any pending messages for {client_name}')


def receive_pending_messages_for_requestor_and_provider(
    cluster_url: str,
    sci_base: SCIBaseTest,
    concent_public_key: bytes,
) -> None:
    receive_all_left_pending_responses(
        cluster_url,
        'receive',
        sci_base.provider_private_key,
        sci_base.provider_public_key,
        concent_public_key,
        'Provider',
    )
    receive_all_left_pending_responses(
        cluster_url,
        'receive',
        sci_base.requestor_private_key,
        sci_base.requestor_public_key,
        concent_public_key,
        'Requestor',
    )


def calculate_timestamp(current_time: int, concent_messaging_time: int, minimum_upload_rate: int) -> str:
    return timestamp_to_isoformat(
        current_time - (2 * concent_messaging_time + _precalculate_subtask_verification_time(minimum_upload_rate, concent_messaging_time))
    )


def calculate_deadline(current_time: int, concent_messaging_time: int, minimum_upload_rate: int) -> int:
    return current_time - (concent_messaging_time + _precalculate_subtask_verification_time(minimum_upload_rate, concent_messaging_time))


def create_force_subtask_results(
    timestamp: Optional[str]=None,
    ack_report_computed_task: Optional[message.tasks.AckReportComputedTask]=None,
) -> message.concents.ForceSubtaskResults:
    with freeze_time(timestamp):
        return message.concents.ForceSubtaskResults(
            ack_report_computed_task=ack_report_computed_task,
        )


def create_ack_report_computed_task(
    requestor_private_key: bytes,
    timestamp: Optional[str]=None,
    report_computed_task: Optional[message.tasks.ReportComputedTask]=None,
) -> message.tasks.AckReportComputedTask:
    with freeze_time(timestamp):
        signed_message: message.tasks.AckReportComputedTask = sign_message(
            message.tasks.AckReportComputedTask(
                report_computed_task=report_computed_task,
            ),
            requestor_private_key,
        )
        return signed_message


def calculate_deadline_too_far_in_the_future(current_time: int, minimum_upload_rate: int, concent_messaging_time: int) -> int:
    return current_time - (1 + (20 * _precalculate_subtask_verification_time(minimum_upload_rate, concent_messaging_time)))


def _precalculate_subtask_verification_time(minimum_upload_rate: int, concent_messaging_time: int) -> int:
    maxiumum_download_time = calculate_maximum_download_time(
        size=REPORT_COMPUTED_TASK_SIZE,
        rate=minimum_upload_rate,
    )
    return (
        (4 * concent_messaging_time) +
        (3 * maxiumum_download_time)
    )
