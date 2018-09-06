#!/usr/bin/env python3

from configparser import ConfigParser
import os
import sys

from golem_messages.message import Message
from middleman_protocol.message import GolemMessageFrame
from middleman_protocol.concent_golem_messages.message import SignedTransaction
from middleman_protocol.concent_golem_messages.message import TransactionSigningRequest

from api_testing_common import assert_condition
from api_testing_common import count_fails
from common.helpers import get_current_utc_timestamp
from signing_service_testing_common import Components
from signing_service_testing_common import run_tests
from signing_service_testing_common import send_message_to_middleman_and_receive_response


REQUIRED_COMPONENTS = [Components.MIDDLEMAN]

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "concent_api.settings")


def create_golem_message_frame(payload: Message, request_id: int) -> GolemMessageFrame:
    return GolemMessageFrame(
        payload=payload,
        request_id=request_id,
    )


def correct_transaction_signing_request(request_id: int) -> TransactionSigningRequest:
    transaction_siging_request = TransactionSigningRequest(
        nonce=request_id,
        gasprice=10 ** 6,
        startgas=80000,
        value=10,
        to='7917bc33eea648809c28',
        data=b'3078666333323333396130303030303030303030303030303030303030303030303032393662363963383738613734393865663463343531363436353231336564663834666334623330303030303030303030303030303030303030303030303030333431336437363161356332633362656130373531373064333239363566636161386261303533633030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303237313030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303562343336643666',
    )
    setattr(transaction_siging_request, 'from', '7917bc33eea648809c29')
    return transaction_siging_request


def create_golem_message_frame_with_correct_transaction_signing_request(request_id: int) -> GolemMessageFrame:
    return create_golem_message_frame(
        payload=correct_transaction_signing_request(request_id),
        request_id=request_id,
    )


@count_fails
def test_case_send_golem_message_frame_with_correct_transaction_signing_request(test_id: str, config: ConfigParser) -> None:
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
        signing_service_public_key=SIGNING_SERVICE_PUBLIC_KEY,
        concent_private_key=CONCENT_PRIVATE_KEY,
    )

    # Check response.
    assert_condition(type(response), GolemMessageFrame, f'Deserialized response type is {type(response)} instead of GolemMessageFrame.')
    assert_condition(type(response.payload), SignedTransaction, f'Deserialized response payload type is {type(response.payload)} instead of SignedTransaction.')


if __name__ == '__main__':
    try:
        from concent_api.settings import SIGNING_SERVICE_PUBLIC_KEY
        from concent_api.settings import CONCENT_PRIVATE_KEY
        run_tests(globals())
    except Exception as exception:
        print("\nERROR: Tests failed with exception:\n", file=sys.stderr)
        sys.exit(str(exception))
