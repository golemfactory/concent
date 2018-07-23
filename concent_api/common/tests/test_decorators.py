import json
import mock
from freezegun                      import freeze_time
from django.http                    import JsonResponse
from django.http                    import HttpResponse
from django.http                    import HttpResponseNotAllowed
from django.test                    import override_settings
from django.test                    import RequestFactory
from golem_messages                 import dump
from golem_messages                 import load
from golem_messages                 import message

from core.exceptions                import Http400
from core.tests.utils import ConcentIntegrationTestCase
from core.tests.utils import parse_iso_date_to_timestamp
from common.constants                import ErrorCode
from common.decorators               import handle_errors_and_responses
from common.decorators import log_task_errors
from common.decorators               import require_golem_auth_message
from common.testing_helpers          import generate_ecc_key_pair


(CONCENT_PRIVATE_KEY, CONCENT_PUBLIC_KEY)   = generate_ecc_key_pair()


@require_golem_auth_message
def dummy_view_require_golem_auth_message(_request, message, _client_public_key):  # pylint: disable=redefined-outer-name
    return message


@handle_errors_and_responses(database_name='default')
def dummy_view_handle_errors_and_responses(_request, message, _client_public_key):  # pylint: disable=redefined-outer-name
    return message


@override_settings(
    CONCENT_PRIVATE_KEY = CONCENT_PRIVATE_KEY,
    CONCENT_PUBLIC_KEY  = CONCENT_PUBLIC_KEY,
)
class DecoratorsTestCase(ConcentIntegrationTestCase):
    def setUp(self):
        super().setUp()
        self.request_factory = RequestFactory()
        self.client_auth = message.concents.ClientAuthorization()
        self.client_auth.client_public_key = self.PROVIDER_PUBLIC_KEY

    def test_require_golem_auth_message_decorator_should_return_http_400_when_auth_message_not_send(self):
        dumped_message = dump(self._create_test_ping_message(), CONCENT_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        request  = self.request_factory.post("/dummy-url/", content_type = 'application/octet-stream', data = dumped_message)
        response = dummy_view_require_golem_auth_message(request)  # pylint: disable=no-value-for-parameter

        self.assertEqual(response.status_code, 400)
        self.assertIn('error', json.loads(response.content))

    def test_require_golem_auth_message_should_return_http_200_when_message_included(self):
        with freeze_time("2017-12-31 00:00:00"):
            request = self.request_factory.post("/dummy-url/", content_type = 'application/octet-stream', data = self._create_provider_auth_message())

        with freeze_time("2017-12-31 00:00:10"):
            response = dummy_view_require_golem_auth_message(request)  # pylint: disable=no-value-for-parameter

        self.assertIsInstance(response,                 message.concents.ClientAuthorization)
        self.assertEqual(response.client_public_key,    self.PROVIDER_PUBLIC_KEY)
        self.assertEqual(response.sig,                  self._add_signature_to_message(response, self.PROVIDER_PRIVATE_KEY))
        self.assertEqual(response.timestamp, parse_iso_date_to_timestamp("2017-12-31 00:00:00"))

    def test_require_golem_auth_message_should_return_http_400_when_message_created_too_far_in_the_future(self):
        with freeze_time("2017-12-31 01:00:00"):
            request = self.request_factory.post("/dummy-url/", content_type = 'application/octet-stream', data = self._create_provider_auth_message())

        with freeze_time("2017-12-31 00:00:00"):
            response = dummy_view_require_golem_auth_message(request)  # pylint: disable=no-value-for-parameter

        self.assertEqual(response.status_code, 400)
        self.assertIn('error', json.loads(response.content))

    def test_require_golem_auth_message_should_return_http_400_when_message_is_too_old(self):
        with freeze_time("2017-12-31 00:00:00"):
            request = self.request_factory.post("/dummy-url/", content_type = 'application/octet-stream', data = self._create_provider_auth_message())

        with freeze_time("2017-12-31 01:00:00"):
            response = dummy_view_require_golem_auth_message(request)  # pylint: disable=no-value-for-parameter

        self.assertEqual(response.status_code, 400)
        self.assertIn('error', json.loads(response.content))

    def test_require_golem_auth_message_should_return_http_415_when_content_type_missing(self):

        request = self.request_factory.post("/dummy-url/")

        response = dummy_view_require_golem_auth_message(request)  # pylint: disable=no-value-for-parameter

        self.assertEqual(response.status_code, 415)
        self.assertIn('error', json.loads(response.content))

    def test_require_golem_auth_message_should_return_http_400_when_client_public_key_is_empty(self):

        client_auth = message.concents.ClientAuthorization()
        dumped_auth_message = dump(client_auth, self.PROVIDER_PRIVATE_KEY, self.PROVIDER_PUBLIC_KEY)

        request = self.request_factory.post("/dummy-url/", content_type = 'application/octet-stream', data = dumped_auth_message)

        response = dummy_view_require_golem_auth_message(request)  # pylint: disable=no-value-for-parameter

        self.assertEqual(response.status_code, 400)
        self.assertIn('error', json.loads(response.content))

    def test_require_golem_auth_message_should_return_http_400_if_content_type_is_empty(self):

        request = self.request_factory.post("/dummy-url/", content_type = '')

        response = dummy_view_require_golem_auth_message(request)  # pylint: disable=no-value-for-parameter

        self.assertEqual(response.status_code, 400)
        self.assertIn('error', json.loads(response.content))

    def test_require_golem_auth_message_should_return_json_response_http_400_when_auth_message_is_signed_with_wrong_key(self):

        request = self.request_factory.post(
            "/dummy-url/",
            content_type='application/octet-stream',
            data=self._create_client_auth_message(
                self.PROVIDER_PRIVATE_KEY,
                self.REQUESTOR_PUBLIC_KEY,
            )
        )

        response = dummy_view_require_golem_auth_message(request)  # pylint: disable=no-value-for-parameter

        self.assertEqual(response.status_code, 400)

        content = json.loads(response.content)
        self.assertIn('error', content)
        self.assertIn('error_code', content)
        self.assertEqual(content['error_code'], ErrorCode.MESSAGE_SIGNATURE_WRONG.value)

    def test_handle_errors_and_responses_should_return_http_response_with_serialized_message(self):

        dumped_message = dump(self._create_test_ping_message(), CONCENT_PRIVATE_KEY, self.PROVIDER_PUBLIC_KEY)
        request = self.request_factory.post("/dummy-url/", content_type = 'application/octet-stream', data = dumped_message)

        response = dummy_view_handle_errors_and_responses(request, dumped_message, self.PROVIDER_PUBLIC_KEY)

        loaded_response = load(response.content, self.PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(loaded_response, message.Ping)

    def test_handle_errors_and_responses_should_return_serialized_message_if_gets_deserialized(self):

        with freeze_time("2017-12-31 00:00:00"):
            client_auth = message.concents.ClientAuthorization()
            client_auth.client_public_key = self.PROVIDER_PUBLIC_KEY

        request = self.request_factory.post("/dummy-url/", content_type = 'application/octet-stream')

        with freeze_time("2017-12-31 00:00:10"):
            response = dummy_view_handle_errors_and_responses(request, client_auth, self.PROVIDER_PUBLIC_KEY)
            loaded_response = load(response.content, self.PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY)  # pylint: disable=no-member

        self.assertEqual(response.status_code, 200)  # pylint: disable=no-member
        self.assertIsInstance(loaded_response, message.concents.ClientAuthorization)
        self.assertEqual(loaded_response.timestamp, parse_iso_date_to_timestamp("2017-12-31 00:00:00"))

    def test_handle_errors_and_responses_should_return_http_response_if_it_has_been_passed_to_decorator(self):

        request = self.request_factory.post("/dummy-url/", content_type = 'application/octet-stream')

        @handle_errors_and_responses(database_name='default')
        def dummy_view_handle_http_response(_request, _message, _client_public_key):
            http_response = HttpResponse(status = 200)
            return http_response

        response = dummy_view_handle_http_response(request, self.client_auth, self.PROVIDER_PUBLIC_KEY)

        self.assertIsInstance(response, HttpResponse)
        self.assertEqual(response.status_code, 200)

    def test_handle_errors_and_responses_should_return_empty_http_response_if_view_passed_none(self):

        request = self.request_factory.post("/dummy-url/", content_type = 'application/octet-stream')

        @handle_errors_and_responses(database_name='default')
        def dummy_view_handle_none_response(_request, _message, _client_public_key):
            return None

        response = dummy_view_handle_none_response(request, self.client_auth, self.PROVIDER_PUBLIC_KEY)  # pylint: disable=assignment-from-none

        self.assertEqual(response.status_code, 204)
        self.assertEqual(len(response.content), 0)

    def test_handle_errors_and_responses_should_return_json_response_if_view_passed_dict(self):

        request = self.request_factory.post("/dummy-url/", content_type = 'application/octet-stream')

        @handle_errors_and_responses(database_name='default')
        def dummy_view_handle_dict(_request, _message, _client_public_key):
            return {'dummy': 'data'}

        response = dummy_view_handle_dict(request, self.client_auth, self.PROVIDER_PUBLIC_KEY)

        self.assertEqual(response.status_code, 200)  # pylint: disable=no-member
        self.assertIsInstance(response, JsonResponse)
        self.assertEqual(json.loads(response.content), {'dummy': 'data'})  # pylint: disable=no-member

    def test_handle_errors_and_responses_should_return_http_response_if_view_raised_http_400_exception(self):

        request = self.request_factory.post("/dummy-url/", content_type = 'application/octet-stream')

        @handle_errors_and_responses(database_name='default')
        def dummy_view_handle_http_400_exception(_request, _message, _client_public_key):
            raise Http400('dummy', error_code=ErrorCode.MESSAGE_UNEXPECTED)

        response = dummy_view_handle_http_400_exception(request, self.client_auth, self.PROVIDER_PUBLIC_KEY)  # pylint: disable=assignment-from-no-return

        self.assertEqual(response.status_code, 400)  # pylint: disable=no-member
        self.assertIn('error', json.loads(response.content))  # pylint: disable=no-member

    def test_handle_errors_and_responses_should_return_http_response_not_allowed_if_view_passed_it(self):

        request = self.request_factory.post("/dummy-url/", content_type = 'application/octet-stream')

        @handle_errors_and_responses(database_name='default')
        def dummy_view_handle_http_response_not_allowed(_request, _message, _client_public_key):
            return HttpResponseNotAllowed({}, status=405)

        response = dummy_view_handle_http_response_not_allowed(request, self.client_auth, self.PROVIDER_PUBLIC_KEY)

        self.assertEqual(response.status_code, 405)
        self.assertEqual(len(response.content), 0)

    def test_log_task_errors(self):
        @log_task_errors
        def task():
            raise Exception('test')

        with mock.patch('common.decorators.traceback.format_exc') as mock_format_exc:
            with mock.patch('common.decorators.crash_logger.error') as mock_error:
                with self.assertRaises(Exception):
                    task()

        mock_format_exc.assert_called_once()
        mock_error.assert_called_once()
