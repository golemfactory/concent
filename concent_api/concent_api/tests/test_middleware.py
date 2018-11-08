import json
import unittest

import mock
from django.conf import settings

from django.test            import override_settings
from django.test            import TestCase
from django.urls            import reverse

from golem_messages         import dump
from golem_messages         import message
from golem_messages         import __version__

from concent_api.constants import DEFAULT_ERROR_MESSAGE
from concent_api.middleware import determine_return_type
from core.tests.utils import ConcentIntegrationTestCase
from common.constants import ErrorCode
from common.testing_helpers import generate_ecc_key_pair


(CONCENT_PRIVATE_KEY,   CONCENT_PUBLIC_KEY)   = generate_ecc_key_pair()
(PROVIDER_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY)  = generate_ecc_key_pair()


class CustomException(Exception):
    pass


class CustomExceptionWithStringRepr(Exception):
    def __init__(self, error_message, error_code):
        super().__init__()
        self.message = error_message
        self.error_code = error_code

    def __repr__(self):
        return self.message

    def __str__(self):
        return self.message


@override_settings(
    CONCENT_PRIVATE_KEY    = CONCENT_PRIVATE_KEY,
    CONCENT_PUBLIC_KEY     = CONCENT_PUBLIC_KEY,
)
class GolemMessagesVersionMiddlewareTest(TestCase):

    def test_golem_messages_version_middleware_should_attach_http_header_to_response(self):
        """
        Tests that response from Concent:

        * Contains HTTP header 'Concent-Golem-Messages-Version'.
        * Header contains latest version of golem_messages package.
        """
        ping_message = message.Ping()
        serialized_ping_message = dump(ping_message, PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        response = self.client.post(
            reverse('core:send'),
            data=serialized_ping_message,
            content_type='application/octet-stream',
            HTTP_X_Golem_Messages=settings.GOLEM_MESSAGES_VERSION,
        )

        self.assertFalse(500 <= response.status_code < 600)
        self.assertIn('concent-golem-messages-version', response._headers)
        self.assertEqual(
            response._headers['concent-golem-messages-version'][0],
            'Concent-Golem-Messages-Version'
        )
        self.assertEqual(
            response._headers['concent-golem-messages-version'][1],
            __version__
        )


@override_settings(
    CONCENT_PRIVATE_KEY    = CONCENT_PRIVATE_KEY,
    CONCENT_PUBLIC_KEY     = CONCENT_PUBLIC_KEY,
)
class ConcentVersionMiddlewareTest(TestCase):

    def test_golem_messages_version_middleware_should_attach_http_header_to_response(self):
        """
        Tests that response from Concent:

        * Contains HTTP header 'Concent-Version'.
        * Header contains version of Concent taken from settings.
        """
        ping_message = message.Ping()
        serialized_ping_message = dump(ping_message, PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with mock.patch('concent_api.middleware.ConcentVersionMiddleware._concent_version', '1.0'):
            response = self.client.post(
                reverse('core:send'),
                data=serialized_ping_message,
                content_type='application/octet-stream',
                HTTP_X_Golem_Messages=settings.GOLEM_MESSAGES_VERSION,
            )

        self.assertFalse(500 <= response.status_code < 600)
        self.assertIn('concent-golem-messages-version', response._headers)
        self.assertEqual(
            response._headers['concent-version'][0],
            'Concent-Version'
        )
        self.assertEqual(
            response._headers['concent-version'][1],
            '1.0'
        )


@override_settings(
    CONCENT_PRIVATE_KEY=CONCENT_PRIVATE_KEY,
    CONCENT_PUBLIC_KEY=CONCENT_PUBLIC_KEY,
    DEBUG=False,
    DEBUG_INFO_IN_ERROR_RESPONSES=False,
    MIDDLEWARE=[
        'concent_api.middleware.HandleServerErrorMiddleware',
        'django.middleware.security.SecurityMiddleware',
        'django.contrib.sessions.middleware.SessionMiddleware',
        'django.middleware.common.CommonMiddleware',
        'django.middleware.csrf.CsrfViewMiddleware',
        'django.contrib.auth.middleware.AuthenticationMiddleware',
        'django.contrib.messages.middleware.MessageMiddleware',
        'django.middleware.clickjacking.XFrameOptionsMiddleware',
        'concent_api.middleware.GolemMessagesVersionMiddleware',
        'concent_api.middleware.ConcentVersionMiddleware',
    ]
)
class HandleServerErrorMiddlewareTest(ConcentIntegrationTestCase):
    def test_that_middlware_does_not_intercept_2xx_http_responses(self):
        response = self.client.post(
            reverse('core:receive'),
            data=self._create_client_auth_message(PROVIDER_PRIVATE_KEY, PROVIDER_PUBLIC_KEY),
            content_type='application/octet-stream',
            HTTP_X_Golem_Messages=settings.GOLEM_MESSAGES_VERSION,
        )
        self.assertEqual(response.status_code, 204)

    def test_that_middleware_does_not_intercept_bad_requests(self):
        ping_message = message.Ping()
        serialized_ping_message = dump(ping_message, PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY)
        response = self.client.post(
            reverse('core:receive'),
            data=serialized_ping_message,
            content_type='application/octet-stream',
            HTTP_X_Golem_Messages=settings.GOLEM_MESSAGES_VERSION,
        )
        self.assertEqual(response.status_code, 400)

    def test_that_uncaught_errors_without_string_representation_are_returned_as_json_response_with_status_500_and_default_error_message(self):
        with mock.patch('core.views.handle_messages_from_database', side_effect=CustomException(), autospec=True):
            response = self.client.post(
                reverse('core:receive'),
                data=self._create_client_auth_message(PROVIDER_PRIVATE_KEY, PROVIDER_PUBLIC_KEY),
                content_type='application/octet-stream',
                HTTP_X_Golem_Messages=settings.GOLEM_MESSAGES_VERSION,
            )
            loaded_json = json.loads(response.content)
            self._assert_proper_internal_server_error_received(
                response,
                loaded_json,
                DEFAULT_ERROR_MESSAGE,
                ErrorCode.CONCENT_APPLICATION_CRASH.value
            )

    def test_that_uncaught_errors_with_string_representation_are_returned_as_json_response_with_status_500(self):
        error_message = "I am sorry, it's all my fault"
        with mock.patch(
            'core.views.handle_messages_from_database',
            side_effect=CustomExceptionWithStringRepr(error_message, ErrorCode.MESSAGE_OPERATION_INVALID),
            autospec=True
        ):
            response = self.client.post(
                reverse('core:receive'),
                data=self._create_client_auth_message(PROVIDER_PRIVATE_KEY, PROVIDER_PUBLIC_KEY),
                content_type='application/octet-stream',
                HTTP_X_Golem_Messages=settings.GOLEM_MESSAGES_VERSION,
            )
            loaded_json = json.loads(response.content)
            self._assert_proper_internal_server_error_received(
                response,
                loaded_json,
                error_message,
                ErrorCode.MESSAGE_OPERATION_INVALID.value
            )

    @override_settings(
        DEBUG=True,
    )
    def test_that_with_debug_enabled_uncaught_errors_are_returned_as_json_response_with_status_500_and_stack_trace(
        self
    ):
        del settings.DEBUG_INFO_IN_ERROR_RESPONSES
        with mock.patch('core.views.handle_messages_from_database', side_effect=CustomException(), autospec=True):
            response = self.client.post(
                reverse('core:receive'),
                data=self._create_client_auth_message(PROVIDER_PRIVATE_KEY, PROVIDER_PUBLIC_KEY),
                content_type='application/octet-stream',
                HTTP_X_Golem_Messages=settings.GOLEM_MESSAGES_VERSION,
            )
            loaded_json = json.loads(response.content)
            self._assert_proper_internal_server_error_received(
                response,
                loaded_json,
                DEFAULT_ERROR_MESSAGE,
                ErrorCode.CONCENT_APPLICATION_CRASH.value
            )
            self.assertIn('stack_trace', loaded_json)
            self.assertTrue(len(loaded_json['stack_trace']) > 0)

    @override_settings(
        DEBUG_INFO_IN_ERROR_RESPONSES=True,
    )
    def test_that_with_debug_info_enabled_uncaught_errors_are_returned_as_json_response_with_status_500_and_stack_trace(self):
        with mock.patch('core.views.handle_messages_from_database', side_effect=CustomException(), autospec=True):
            response = self.client.post(
                reverse('core:receive'),
                data=self._create_client_auth_message(PROVIDER_PRIVATE_KEY, PROVIDER_PUBLIC_KEY),
                content_type='application/octet-stream',
                HTTP_X_Golem_Messages=settings.GOLEM_MESSAGES_VERSION,
            )
            loaded_json = json.loads(response.content)
            self._assert_proper_internal_server_error_received(
                response,
                loaded_json,
                DEFAULT_ERROR_MESSAGE,
                ErrorCode.CONCENT_APPLICATION_CRASH.value
            )
            self.assertIn('stack_trace', loaded_json)
            self.assertTrue(len(loaded_json['stack_trace']) > 0)

    def test_that_uncought_errors_are_returned_as_html_when_client_wants_html(self):
        with mock.patch('core.views.handle_messages_from_database', side_effect=CustomException(), autospec=True):
            response = self.client.post(
                reverse('core:receive'),
                data=self._create_client_auth_message(PROVIDER_PRIVATE_KEY, PROVIDER_PUBLIC_KEY),
                content_type='application/octet-stream',
                HTTP_ACCEPT="text/html",
                HTTP_X_Golem_Messages=settings.GOLEM_MESSAGES_VERSION,
            )

            self.assertEqual(response.status_code, 500)
            self.assertEqual(response.reason_phrase, 'Internal Server Error')
            self.assertEqual(response._headers['content-type'][1], 'text/html')

    def test_that_broken_accept_header_causes_http_406_in_case_of_unhandled_internal_server_error(self):
        with mock.patch('core.views.handle_messages_from_database', side_effect=CustomException(), autospec=True):
            response = self.client.post(
                reverse('core:receive'),
                data=self._create_client_auth_message(PROVIDER_PRIVATE_KEY, PROVIDER_PUBLIC_KEY),
                content_type='application/octet-stream',
                HTTP_ACCEPT="applicati;q=-7on/json",
                HTTP_X_Golem_Messages=settings.GOLEM_MESSAGES_VERSION,
            )

            self.assertEqual(response.status_code, 406)

    @override_settings(
        DEBUG_INFO_IN_ERROR_RESPONSES=True,
    )
    def test_that_with_debug_info_enabled_uncaught_errors_are_returned_as_returned_as_html_with_stack_trace_when_client_wants_html(
        self
    ):
        with mock.patch('core.views.handle_messages_from_database', side_effect=CustomException(), autospec=True):
            response = self.client.post(
                reverse('core:receive'),
                data=self._create_client_auth_message(PROVIDER_PRIVATE_KEY, PROVIDER_PUBLIC_KEY),
                content_type='application/octet-stream',
                HTTP_ACCEPT="text/html",
                HTTP_X_Golem_Messages=settings.GOLEM_MESSAGES_VERSION,
            )

            self.assertEqual(response.status_code, 500)
            self.assertEqual(response.reason_phrase, 'Internal Server Error')
            self.assertEqual(response._headers['content-type'][1], 'text/html')
            self.assertIn(b"Traceback", response.content)

    def _assert_proper_internal_server_error_received(self, response, loaded_json, error_message, error_code):
        self.assertEqual(response.status_code, 500)
        self.assertIn('error_message', loaded_json)
        self.assertEqual(loaded_json['error_message'], error_message)
        self.assertEqual(loaded_json['error_code'], error_code)


class TestDetermineReturnType(unittest.TestCase):
    def test_that_with_no_information_in_request_json_is_used(self):
        request_headers = {}

        return_type = determine_return_type(request_headers)

        self.assertEqual(return_type, "application/json")

    def test_that_with_acceptance_of_html_html_is_used(self):
        request_headers = {
            "HTTP_ACCEPT": "text/html"
        }

        return_type = determine_return_type(request_headers)

        self.assertEqual(return_type, "text/html")

    def test_that_order_doest_not_matter_when_no_weight_is_given(self):
        request_headers = {
            "HTTP_ACCEPT": "text/html, application/json"
        }

        return_type = determine_return_type(request_headers)

        self.assertEqual(return_type, "application/json")

    def test_that_weight_determines_return_type(self):
        request_headers = {
            "HTTP_ACCEPT": "text/html;q=0.79, application/json;q=0.8"
        }

        return_type = determine_return_type(request_headers)

        self.assertEqual(return_type, "application/json")

    def test_that_empty_string_is_returned_when_accept_header_is_malformed(self):
        request_headers = {
            "HTTP_ACCEPT": "applicati;q=-7on/json"
        }

        return_type = determine_return_type(request_headers)

        self.assertEqual(return_type, "")

    def test_that_with_wildcard_accept_header_value_in_request_json_is_used(self):
        request_headers = {
            "HTTP_ACCEPT": '*/*'
        }

        return_type = determine_return_type(request_headers)

        self.assertEqual(return_type, "application/json")
