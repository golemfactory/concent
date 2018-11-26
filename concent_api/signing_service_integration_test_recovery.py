#!/usr/bin/env python3

from configparser import ConfigParser
from time import sleep
from typing import Any
import os
import socket
import subprocess
import sys

from api_testing_common import assert_condition
from api_testing_common import count_fails
from common.helpers import get_current_utc_timestamp
from middleman_protocol.message import GolemMessageFrame
from middleman_protocol.concent_golem_messages.message import SignedTransaction
from middleman_protocol.stream import send_over_stream
from middleman_protocol.stream import unescape_stream
from signing_service_testing_common import Components
from signing_service_testing_common import create_golem_message_frame_with_correct_transaction_signing_request
from signing_service_testing_common import run_tests
from signing_service_testing_common import send_message_to_middleman_and_receive_response
from signing_service_testing_common import send_message_to_middleman_without_response


REQUIRED_COMPONENTS = []  # type: ignore

SLEEP_TIME_AFTER_SPAWNING_PROCESS = 10
SLEEP_TIME_AFTER_KILLING_PROCESS = 10

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "concent_api.settings")


def run_middleman() -> subprocess.Popen:
    return subprocess.Popen(
        [
            'python',
            'manage.py',
            'middleman'
        ]
    )


def run_signing_service() -> subprocess.Popen:
    return subprocess.Popen(
        [
            'python',
            '-m',
            'signing_service.signing_service',
            '--concent-cluster-host',
            '127.0.0.1',
            '--concent-public-key',
            '"85cZzVjahnRpUBwm0zlNnqTdYom1LF1P1WNShLg17cmhN2UssnPrCjHKTi5susO3wrr/q07eswumbL82b4HgOw=="',
            '--signing-service-private-key',
            '"GfkWzCRGL/Me2wk41mS0NRSch2XMpgIXYLRaasmcozw="',
            '--ethereum-private-key',
            '"M2ExMDc2YmY0NWFiODc3MTJhZDY0Y2NiM2IxMDIxNzczN2Y3ZmFhY2JmMjg3MmU4OGZkZDlhNTM3ZDhmZTI2Ng=="'
        ],
        cwd='../signing_service/'
    )


@count_fails
def test_case_0_prove_of_concept(config: ConfigParser, **kwargs: Any) -> None:
    """
    1. Spawn MiddleMan and SigningService processes.
    2. Client sends GolemMessageFrame with correct TransactionSigningRequest to MiddleMan
       and receives response to prove that connection works.
    """

    try:
        middleman_process = run_middleman()
        signing_service_process = run_signing_service()

        # Waiting for MiddleMan and SigningService to start.
        sleep(SLEEP_TIME_AFTER_SPAWNING_PROCESS)

        # Create GolemMessageFrame with correct TransactionSigningRequest.
        golem_message_frame = create_golem_message_frame_with_correct_transaction_signing_request(
            request_id=get_current_utc_timestamp(),
        )

        # Send message through wrapper and receive deserialized response.
        response = send_message_to_middleman_and_receive_response(
            message=golem_message_frame,
            config=config,
            concent_private_key=CONCENT_PRIVATE_KEY,
            concent_public_key=CONCENT_PUBLIC_KEY,
        )

        # Check response.
        assert_condition(
            type(response),
            GolemMessageFrame,
            f'Deserialized response type is {type(response)} instead of GolemMessageFrame.'
        )
        assert_condition(
            type(response.payload),
            SignedTransaction,
            f'Deserialized response payload type is {type(response.payload)} instead of SignedTransaction.'
        )
        assert_condition(
            response.request_id,
            golem_message_frame.request_id,
            f'Deserialized response request_id is {response.request_id} instead of {golem_message_frame.request_id}.'
        )

    finally:
        middleman_process.kill()
        signing_service_process.kill()


@count_fails
def test_case_1_middleman_recovery(config: ConfigParser, **kwargs: Any) -> None:
    """
    1. Spawn MiddleMan and SigningService processes.
    2. Client sends GolemMessageFrame with correct TransactionSigningRequest to MiddleMan.
    3. Middleman is restarted. The connection and latest message is lost.
    4. Client sends GolemMessageFrame with correct TransactionSigningRequest to MiddleMan.
    5. Client receives response for latest message.
    """

    try:
        middleman_process = run_middleman()
        signing_service_process = run_signing_service()

        # Waiting for MiddleMan and SigningService to start.
        sleep(SLEEP_TIME_AFTER_SPAWNING_PROCESS)

        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)

        # Create GolemMessageFrame with correct TransactionSigningRequest.
        golem_message_frame = create_golem_message_frame_with_correct_transaction_signing_request(
            request_id=get_current_utc_timestamp(),
        )

        client_socket.connect(
            (
                config.get(Components.MIDDLEMAN.value, 'host'),
                int(config.get(Components.MIDDLEMAN.value, 'port')),
            )
        )
        send_over_stream(
            connection=client_socket,
            raw_message=golem_message_frame,
            private_key=CONCENT_PRIVATE_KEY,
        )

        middleman_process.kill()

        # Waiting for MiddleMan to finish.
        sleep(SLEEP_TIME_AFTER_KILLING_PROCESS)

        middleman_process = run_middleman()

        # Waiting for MiddleMan to start.
        sleep(SLEEP_TIME_AFTER_SPAWNING_PROCESS)

        receive_frame_generator = unescape_stream(connection=client_socket)
        try:
            next(receive_frame_generator)
        except socket.error as exception:
            assert_condition(exception.args[0], socket.errno.ECONNRESET, f'Connection should be reset by peer.')  # type: ignore

        # Create GolemMessageFrame with correct TransactionSigningRequest.
        golem_message_frame = create_golem_message_frame_with_correct_transaction_signing_request(
            request_id=get_current_utc_timestamp(),
        )

        # Send message through wrapper and receive deserialized response.
        response = send_message_to_middleman_and_receive_response(
            message=golem_message_frame,
            config=config,
            concent_private_key=CONCENT_PRIVATE_KEY,
            concent_public_key=CONCENT_PUBLIC_KEY,
        )

        # Check response.
        assert_condition(
            type(response),
            GolemMessageFrame,
            f'Deserialized response type is {type(response)} instead of GolemMessageFrame.'
        )
        assert_condition(
            type(response.payload),
            SignedTransaction,
            f'Deserialized response payload type is {type(response.payload)} instead of SignedTransaction.'
        )
        assert_condition(
            response.request_id,
            golem_message_frame.request_id,
            f'Deserialized response request_id is {response.request_id} instead of {golem_message_frame.request_id}.'
        )

    finally:
        middleman_process.kill()
        signing_service_process.kill()


@count_fails
def test_case_2_signing_service_recovery(config: ConfigParser, **kwargs: Any) -> None:
    """
    1. Spawn MiddleMan and SigningService processes.
    2. Client sends GolemMessageFrame with correct TransactionSigningRequest to MiddleMan.
    3. SigningService is restarted. The latest message is lost.
    4. Client sends GolemMessageFrame with correct TransactionSigningRequest to MiddleMan.
    5. Client receives response for latest message.
    """

    try:
        middleman_process = run_middleman()
        signing_service_process = run_signing_service()

        # Waiting for MiddleMan and SigningService to start.
        sleep(SLEEP_TIME_AFTER_SPAWNING_PROCESS)

        # Create GolemMessageFrame with correct TransactionSigningRequest.
        golem_message_frame = create_golem_message_frame_with_correct_transaction_signing_request(
            request_id=get_current_utc_timestamp(),
        )

        # Send message through wrapper and do not wait for response.
        send_message_to_middleman_without_response(
            message=golem_message_frame,
            config=config,
            concent_private_key=CONCENT_PRIVATE_KEY,
        )

        signing_service_process.kill()

        # Waiting for SigningService to finish.
        sleep(SLEEP_TIME_AFTER_KILLING_PROCESS)

        signing_service_process = run_signing_service()

        # Waiting for SigningService to start.
        sleep(SLEEP_TIME_AFTER_SPAWNING_PROCESS)

        # Create GolemMessageFrame with correct TransactionSigningRequest.
        golem_message_frame = create_golem_message_frame_with_correct_transaction_signing_request(
            request_id=get_current_utc_timestamp(),
        )

        # Send message through wrapper and receive deserialized response.
        response = send_message_to_middleman_and_receive_response(
            message=golem_message_frame,
            config=config,
            concent_private_key=CONCENT_PRIVATE_KEY,
            concent_public_key=CONCENT_PUBLIC_KEY,
        )

        # Check response.
        assert_condition(
            type(response),
            GolemMessageFrame,
            f'Deserialized response type is {type(response)} instead of GolemMessageFrame.'
        )
        assert_condition(
            type(response.payload),
            SignedTransaction,
            f'Deserialized response payload type is {type(response.payload)} instead of SignedTransaction.'
        )
        assert_condition(
            response.request_id,
            golem_message_frame.request_id,
            f'Deserialized response request_id is {response.request_id} instead of {golem_message_frame.request_id}.'
        )

    finally:
        middleman_process.kill()
        signing_service_process.kill()


if __name__ == '__main__':
    try:
        from concent_api.settings import CONCENT_PRIVATE_KEY
        from concent_api.settings import CONCENT_PUBLIC_KEY
        run_tests(globals())
    except Exception as exception:
        print("\nERROR: Tests failed with exception:\n", file=sys.stderr)
        sys.exit(str(exception))
