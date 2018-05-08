import json

import mock

from django.test            import override_settings
from django.test            import TestCase
from django.urls            import reverse

from golem_messages         import dump
from golem_messages         import message
from golem_messages         import __version__

from concent_api.constants import DEFAULT_ERROR_MESSAGE
from core.tests.utils import ConcentIntegrationTestCase
from utils.constants import ErrorCode
from utils.testing_helpers import generate_ecc_key_pair


(CONCENT_PRIVATE_KEY,   CONCENT_PUBLIC_KEY)   = generate_ecc_key_pair()
(PROVIDER_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY)  = generate_ecc_key_pair()


class CustomException(Exception):
    pass


class CustomExceptionWithStringRepr(Exception):
    def __init__(self, error_message):
        super().__init__()
        self.message = error_message

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
            data                           = serialized_ping_message,
            content_type                   = 'application/octet-stream',
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
                data                           = serialized_ping_message,
                content_type                   = 'application/octet-stream',
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
)
class HandleServerErrorMiddlewareTest(ConcentIntegrationTestCase):
    def test_that_middlware_does_not_intercept_2xx_http_responses(self):
        response = self.client.post(
            reverse('core:receive'),
            data=self._create_client_auth_message(PROVIDER_PRIVATE_KEY, PROVIDER_PUBLIC_KEY),
            content_type='application/octet-stream',
        )
        self.assertEqual(response.status_code, 204)

    def test_that_middleware_does_not_intercept_bad_requests(self):
        ping_message = message.Ping()
        serialized_ping_message = dump(ping_message, PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY)
        response = self.client.post(
            reverse('core:receive'),
            data=serialized_ping_message,
            content_type='application/octet-stream',
        )
        self.assertEqual(response.status_code, 400)

    def test_that_uncaught_errors_without_string_representation_are_returned_as_json_response_with_status_500_and_default_error_message(self):
        with mock.patch('core.views.handle_messages_from_database', side_effect=CustomException(), autospec=True):
            response = self.client.post(
                reverse('core:receive'),
                data=self._create_client_auth_message(PROVIDER_PRIVATE_KEY, PROVIDER_PUBLIC_KEY),
                content_type='application/octet-stream',
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
            side_effect=CustomExceptionWithStringRepr(error_message),
            autospec=True
        ):
            response = self.client.post(
                reverse('core:receive'),
                data=self._create_client_auth_message(PROVIDER_PRIVATE_KEY, PROVIDER_PUBLIC_KEY),
                content_type='application/octet-stream',
            )
            loaded_json = json.loads(response.content)
            self._assert_proper_internal_server_error_received(
                response,
                loaded_json,
                error_message,
                ErrorCode.CONCENT_APPLICATION_CRASH.value
            )

    @override_settings(
        DEBUG=True,
    )
    def test_that_with_debug_enabled_uncaught_errors_are_returned_as_json_response_with_status_500_and_stack_trace(
        self
    ):
        with mock.patch('core.views.handle_messages_from_database', side_effect=CustomException(), autospec=True):
            response = self.client.post(
                reverse('core:receive'),
                data=self._create_client_auth_message(PROVIDER_PRIVATE_KEY, PROVIDER_PUBLIC_KEY),
                content_type='application/octet-stream',
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

    def _assert_proper_internal_server_error_received(self, response, loaded_json, error_message, error_code):
        self.assertEqual(response.status_code, 500)
        self.assertIn('error_message', loaded_json)
        self.assertEqual(loaded_json['error_message'], error_message)
        self.assertEqual(loaded_json['error_code'], error_code)
