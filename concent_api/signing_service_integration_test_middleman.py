#!/usr/bin/env python3

from configparser import ConfigParser
from typing import Any
import os
import sys

from api_testing_common import assert_condition
from api_testing_common import call_function_in_threads
from api_testing_common import count_fails
from common.helpers import get_current_utc_timestamp
from common.helpers import RequestIDGenerator
from middleman_protocol.message import GolemMessageFrame
from middleman_protocol.concent_golem_messages.message import SignedTransaction
from signing_service_testing_common import Components
from signing_service_testing_common import create_golem_message_frame_with_correct_transaction_signing_request
from signing_service_testing_common import create_golem_message_frame_with_incorrect_transaction_signing_request
from signing_service_testing_common import run_tests
from signing_service_testing_common import send_message_to_middleman_and_receive_response
from signing_service_testing_common import send_message_to_middleman_without_response


REQUIRED_COMPONENTS = [Components.MIDDLEMAN]

NUMBER_OF_CONCENTS_FOR_SEVERAL_CONCENTS_TEST_CASE = 4
NUMBER_OF_CONCENTS_FOR_MAYHEM_TEST_CASE = 20
NUMBER_OF_REQUEST_PER_CONCENT_FOR_MAYHEM_TEST_CASE = 40


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "concent_api.settings")


def send_golem_message_frame_with_correct_transaction_signing_request(config: ConfigParser) -> None:
    request_id = RequestIDGenerator.generate_request_id()

    # Create GolemMessageFrame with correct TransactionSigningRequest.
    golem_message_frame = create_golem_message_frame_with_correct_transaction_signing_request(
        request_id=request_id,
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
        request_id,
        f'Deserialized response request_id is {response.request_id} instead of {request_id}.'
    )


def send_golem_message_frame_with_incorrect_transaction_signing_request(config: ConfigParser) -> None:
    # Create GolemMessageFrame with incorrect TransactionSigningRequest.
    golem_message_frame = create_golem_message_frame_with_incorrect_transaction_signing_request(
        request_id=get_current_utc_timestamp(),
    )

    # Send message through wrapper and do not wait for response.
    send_message_to_middleman_without_response(
        message=golem_message_frame,
        config=config,
        concent_private_key=CONCENT_PRIVATE_KEY,
    )


@count_fails
def test_case_1_send_golem_message_frame_with_correct_transaction_signing_request(config: ConfigParser, **kwargs: Any) -> None:
    """
    1. Client sends GolemMessageFrame with correct TransactionSigningRequest to MiddleMan.
    2. MiddleMan responds with GolemMessageFrame with SignedTransaction.
    """

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


@count_fails
def test_case_2_send_golem_message_frame_with_incorrect_then_correct_transaction_signing_request(config: ConfigParser, **kwargs: Any) -> None:
    """
    1. Client sends GolemMessageFrame with incorrect TransactionSigningRequest to MiddleMan.
    2  Client sends GolemMessageFrame with correct TransactionSigningRequest to MiddleMan.
    3. MiddleMan responds with GolemMessageFrame with SignedTransaction.
    """

    # Create GolemMessageFrame with incorrect TransactionSigningRequest.
    golem_message_frame = create_golem_message_frame_with_incorrect_transaction_signing_request(
        request_id=get_current_utc_timestamp(),
    )

    # Send message through wrapper and do not wait for response.
    send_message_to_middleman_without_response(
        message=golem_message_frame,
        config=config,
        concent_private_key=CONCENT_PRIVATE_KEY,
    )

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


@count_fails
def test_case_3_send_golem_message_frame_with_correct_transaction_signing_request_by_several_concents(config: ConfigParser, **kwargs: Any) -> None:
    """
    1. Several clients sends GolemMessageFrame with correct TransactionSigningRequest to MiddleMan.
    2. MiddleMan responds with GolemMessageFrame with SignedTransaction to each client.
    """

    call_function_in_threads(
        send_golem_message_frame_with_correct_transaction_signing_request,
        NUMBER_OF_CONCENTS_FOR_SEVERAL_CONCENTS_TEST_CASE,
        config,
    )


@count_fails
def test_case_4_mayhem(config: ConfigParser, **kwargs: Any) -> None:
    """
    In this test case a defined number of Concents
    will send a defined number of requests
    of which half will be correct.
    """

    def send_golem_message_frames(config: ConfigParser) -> None:
        for i in range(NUMBER_OF_REQUEST_PER_CONCENT_FOR_MAYHEM_TEST_CASE):
            if bool(i % 2):
                send_golem_message_frame_with_correct_transaction_signing_request(config)
            else:
                send_golem_message_frame_with_incorrect_transaction_signing_request(config)

    call_function_in_threads(
        send_golem_message_frames,
        NUMBER_OF_CONCENTS_FOR_MAYHEM_TEST_CASE,
        config,
    )


if __name__ == '__main__':
    try:
        from concent_api.settings import CONCENT_PRIVATE_KEY
        from concent_api.settings import CONCENT_PUBLIC_KEY
        run_tests(globals())
    except Exception as exception:
        print("\nERROR: Tests failed with exception:\n", file=sys.stderr)
        sys.exit(str(exception))
