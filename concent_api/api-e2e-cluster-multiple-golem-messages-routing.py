#!/usr/bin/env python3

import os
import sys
import requests

from golem_messages.message import Ping

from api_testing_common import api_request
from api_testing_common import count_fails
from api_testing_common import PROVIDER_PRIVATE_KEY
from api_testing_common import run_tests
from protocol_constants import ProtocolConstants


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "concent_api.settings")


@count_fails
def test_case_ping_message_send_to_concent_with_supported_golem_messages_should_get_http400_response_with_message_unknown_error(
    cluster_url: str,
    cluster_consts: ProtocolConstants,
    concent_1_golem_messages_version: str,
    concent_2_golem_messages_version: str,
) -> None:
    # Sending Ping message to concent with supported versions of Golem Messages.
    # Expected: nginx-router will forward it to the cluster with that version, user will receive Http400,
    # with error code ErrorCode.MESSAGE_UNKNOWN, because concent doesn't handle Ping message.
    api_request(
        cluster_url,
        'send',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        Ping(),
        expected_status=400,
        expected_golem_version=concent_1_golem_messages_version,
        expected_error_code='message.unknown',
    )
    api_request(
        cluster_url,
        'send',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        Ping(),
        expected_status=400,
        expected_golem_version=concent_2_golem_messages_version,
        expected_error_code='message.unknown',
    )


@count_fails
def test_case_ping_message_send_to_concent_with_unsupported_golem_messages_should_get_http404_response_with_not_found_error(
    cluster_url: str,
    cluster_consts: ProtocolConstants,
    concent_1_golem_messages_version: str,
    concent_2_golem_messages_version: str,
) -> None:
    # Sending Ping message to concent with unsupported version of Golem Messages.
    # Expected: nginx-router will respond with Http404.
    api_request(
        cluster_url,
        'send',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        Ping(),
        headers={
            'Content-Type': 'application/octet-stream',
            'X-Golem-Messages': '1.0.0'
        },
        expected_status=404,
        expected_error_code='not-found',
    )


@count_fails
def test_case_ping_message_send_to_concent_with_malformed_golem_messages_should_get_http400_response_with_bad_request_error(
    cluster_url: str,
    cluster_consts: ProtocolConstants,
    concent_1_golem_messages_version: str,
    concent_2_golem_messages_version: str,
) -> None:
    # Sending Ping message to concent with malformed header(Golem Messages version has a wrong, non-semver format).
    # Expected: ngingx-router will respond with Http400 with error code "bad-request".
    api_request(
        cluster_url,
        'send',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        Ping(),
        headers={
            'Content-Type': 'application/octet-stream',
            'X-Golem-Messages': 'X.X.X'
        },
        expected_status=400,
        expected_error_code='bad-request',
    )


if __name__ == '__main__':
    try:
        from concent_api.settings import CONCENT_PUBLIC_KEY
        status = run_tests(globals())
        exit(status)
    except requests.exceptions.ConnectionError as exception:
        print("\nERROR: Failed connect to the server.\n", file=sys.stderr)
        sys.exit(str(exception))
