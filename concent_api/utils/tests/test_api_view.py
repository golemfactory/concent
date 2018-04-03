from base64                         import b64encode
import json
import mock

from django.conf                    import settings
from django.http.response           import HttpResponse
from django.shortcuts               import reverse
from django.test                    import override_settings
from django.test                    import RequestFactory
from django.test                    import TestCase
from django.test                    import TransactionTestCase
from django.views.decorators.http   import require_POST
from golem_messages                 import dump
from golem_messages                 import load
from golem_messages                 import message

from core.exceptions                import Http400
from core.models                    import Client
from utils.api_view                 import api_view
from utils.helpers                  import get_current_utc_timestamp
from utils.testing_helpers          import generate_ecc_key_pair


(CONCENT_PRIVATE_KEY,   CONCENT_PUBLIC_KEY)   = generate_ecc_key_pair()
(PROVIDER_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY)  = generate_ecc_key_pair()
(REQUESTOR_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY) = generate_ecc_key_pair()


@override_settings(
    CONCENT_PRIVATE_KEY = CONCENT_PRIVATE_KEY,
    CONCENT_PUBLIC_KEY  = CONCENT_PUBLIC_KEY,
)
class ApiViewTestCase(TestCase):
    def setUp(self):
        self.request_factory = RequestFactory()
        self.want_to_compute = message.WantToComputeTask(
            node_name           = 1,
            task_id             = 2,
            perf_index          = 3,
            price               = 4,
            max_resource_size   = 5,
            max_memory_size     = 6,
            num_cores           = 7,
        )
        self.message_to_view = {
            "node_name":            self.want_to_compute.node_name,             # pylint: disable=no-member
            "task_id":              self.want_to_compute.task_id,               # pylint: disable=no-member
            "perf_index":           self.want_to_compute.perf_index,            # pylint: disable=no-member
            "price":                self.want_to_compute.price,                 # pylint: disable=no-member
            "max_resource_size":    self.want_to_compute.max_resource_size,     # pylint: disable=no-member
            "max_memory_size":      self.want_to_compute.max_memory_size,       # pylint: disable=no-member
            "num_cores":            self.want_to_compute.num_cores,             # pylint: disable=no-member
        }

    def test_api_view_should_return_golem_message_as_octet_stream(self):
        raw_message = dump(
            self.want_to_compute,
            settings.CONCENT_PRIVATE_KEY,
            settings.CONCENT_PUBLIC_KEY,
        )

        decoded_message = None

        @api_view
        def dummy_view(request, _message):                                       # pylint: disable=unused-argument
            nonlocal decoded_message
            decoded_message = _message
            return None

        request = self.request_factory.post("/dummy-url/", content_type = 'application/octet-stream', data = raw_message)
        request.META['HTTP_CONCENT_CLIENT_PUBLIC_KEY'] = b64encode(settings.CONCENT_PUBLIC_KEY).decode('ascii')

        dummy_view(request)                                                     # pylint: disable=no-value-for-parameter

        message_to_test = message_to_dict(decoded_message)
        self.assertIsInstance(decoded_message, message.WantToComputeTask)
        self.assertEqual(message_to_test, self.message_to_view)

    def test_api_view_should_encode_golem_message_returned_from_view(self):

        @api_view
        def dummy_view(request, _message):                                      # pylint: disable=unused-argument
            return self.want_to_compute

        request = self.request_factory.post("/dummy-url/", content_type = '', data = '')
        request.META['HTTP_CONCENT_CLIENT_PUBLIC_KEY'] = b64encode(settings.CONCENT_PUBLIC_KEY).decode('ascii')

        response = dummy_view(request)                                          # pylint: disable=no-value-for-parameter

        decoded_message = load(
            response.content,                                                   # pylint: disable=no-member
            settings.CONCENT_PRIVATE_KEY,
            settings.CONCENT_PUBLIC_KEY,
        )

        message_to_test = message_to_dict(decoded_message)
        self.assertEqual(response['content-type'], "application/octet-stream")  # pylint: disable=unsubscriptable-object
        self.assertEqual(response.status_code, 200)                             # pylint: disable=no-member
        self.assertEqual(message_to_test, self.message_to_view)

    def test_api_view_should_return_http_415_when_request_content_type_is_not_supported(self):

        @api_view
        def dummy_view(request, _message):                                      # pylint: disable=unused-argument
            return self.want_to_compute

        request = self.request_factory.post("/dummy-url/", content_type = 'application/x-www-form-urlencoded', data = self.want_to_compute)
        request.META['HTTP_CONCENT_CLIENT_PUBLIC_KEY'] = b64encode(settings.CONCENT_PUBLIC_KEY).decode('ascii')

        response = dummy_view(request)                                          # pylint: disable=no-value-for-parameter

        json_response = json.loads(response.content.decode())                   # pylint: disable=no-member

        self.assertEqual(response.status_code, 415)                             # pylint: disable=no-member
        self.assertIn('error', json_response)

    def test_api_view_should_return_http_415_when_request_content_type_is_appplication_json(self):

        @api_view
        def dummy_view(request, _message):                                      # pylint: disable=unused-argument
            return self.message_to_view

        request = self.request_factory.post("/dummy-url/", content_type = 'application/json', data = json.dumps(self.message_to_view))
        request.META['HTTP_CONCENT_CLIENT_PUBLIC_KEY'] = b64encode(settings.CONCENT_PUBLIC_KEY).decode('ascii')

        response = dummy_view(request)                                          # pylint: disable=no-value-for-parameter

        self.assertEqual(response['content-type'], "application/json")
        self.assertEqual(response.status_code, 415)                             # pylint: disable=no-member

    def test_request_with_not_allowed_http_method_should_return_405_error(self):
        """
        Tests if request to Concent with will return HTTP 405 error
        if not allowed HTTP method by view is used.
        """

        @api_view
        @require_POST
        def dummy_view(_request, _message):
            self.fail()

        request = self.request_factory.get(
            "/dummy-url/",
            content_type = 'application/octet-stream',
            data         = '',
        )
        request.META['HTTP_CONCENT_CLIENT_PUBLIC_KEY'] = b64encode(settings.CONCENT_PUBLIC_KEY).decode('ascii')

        response = dummy_view(request)  # pylint: disable=no-value-for-parameter,assignment-from-no-return

        self.assertEqual(response.status_code,  405)


def _log_message_received_500_mock(_message, _client_public_key):
    Client.objects.get_or_create_full_clean(
        CONCENT_PUBLIC_KEY
    )
    raise TypeError


def _log_message_received_400_mock(_message, _client_public_key):
    Client.objects.get_or_create_full_clean(
        CONCENT_PUBLIC_KEY
    )
    raise Http400


def _log_message_received_correct_response_mock(_message, _client_public_key):
    Client.objects.get_or_create_full_clean(
        CONCENT_PUBLIC_KEY
    )


def gatekeeper_access_denied_response_500_mock(_message, _path = None, _subtask_id = None, _client_key = None):
    Client.objects.get_or_create_full_clean(
        CONCENT_PUBLIC_KEY
    )
    raise TypeError


def gatekeeper_access_denied_response_400_mock(_message, _path = None, _subtask_id = None, _client_key = None):
    Client.objects.get_or_create_full_clean(
        CONCENT_PUBLIC_KEY
    )
    raise Http400


def gatekeeper_access_denied_response_200_mock(_message, _path = None, _subtask_id = None, _client_key = None):
    Client.objects.get_or_create_full_clean(
        CONCENT_PUBLIC_KEY
    )
    return HttpResponse()


@override_settings(
    CONCENT_PRIVATE_KEY = CONCENT_PRIVATE_KEY,
    CONCENT_PUBLIC_KEY  = CONCENT_PUBLIC_KEY,
)
class ApiViewTransactionTestCase(TransactionTestCase):

    def test_api_view_should_rollback_changes_on_500_error(self):

        with mock.patch('core.views.logging.log_message_received', _log_message_received_500_mock):
            try:
                self.client.post(
                    reverse('core:send'),
                    data                                = '',
                    content_type                        = 'application/octet-stream',
                    HTTP_CONCENT_CLIENT_PUBLIC_KEY      = b64encode(settings.CONCENT_PUBLIC_KEY).decode('ascii'),
                )
            except TypeError:
                pass

        self.assertEqual(Client.objects.count(), 0)

    def test_api_view_should_rollback_changes_on_400_error(self):

        with mock.patch('core.views.logging.log_message_received', _log_message_received_400_mock):
            self.client.post(
                reverse('core:send'),
                data                                = '',
                content_type                        = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY      = b64encode(settings.CONCENT_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(Client.objects.count(), 0)

    def test_api_view_should_not_rollback_changes_on_correct_response(self):

        message_timestamp              = get_current_utc_timestamp()
        compute_task_def               = message.ComputeTaskDef()
        compute_task_def['task_id']    = '8'
        compute_task_def['subtask_id'] = '8'
        compute_task_def['deadline']   = message_timestamp
        task_to_compute                = message.TaskToCompute(
            compute_task_def     = compute_task_def,
            requestor_public_key = REQUESTOR_PUBLIC_KEY,
            provider_public_key  = PROVIDER_PUBLIC_KEY,
        )

        force_report_computed_task                                      = message.ForceReportComputedTask()
        force_report_computed_task.report_computed_task                 = message.tasks.ReportComputedTask()
        force_report_computed_task.report_computed_task.task_to_compute = task_to_compute

        with mock.patch('core.views.logging.log_message_received', _log_message_received_correct_response_mock):
            response = self.client.post(
                reverse('core:send'),
                data                                = dump(
                    force_report_computed_task,
                    PROVIDER_PRIVATE_KEY,
                    CONCENT_PUBLIC_KEY
                ),
                content_type                        = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY      = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
                HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response.status_code,   202)
        self.assertEqual(Client.objects.count(), 3)  # 3 because view itself is creating 2 clients.

    def test_non_api_view_should_rollback_changes_on_500_error(self):

        with mock.patch('gatekeeper.views.gatekeeper_access_denied_response', gatekeeper_access_denied_response_500_mock):
            try:
                self.client.post(
                    reverse('gatekeeper:upload'),
                    data                                = '',
                    content_type                        = 'application/octet-stream',
                    HTTP_CONCENT_CLIENT_PUBLIC_KEY      = b64encode(settings.CONCENT_PUBLIC_KEY).decode('ascii'),
                )
            except TypeError:
                pass

        self.assertEqual(Client.objects.count(), 0)

    def test_non_api_view_should_rollback_changes_on_400_error(self):

        with mock.patch('gatekeeper.views.gatekeeper_access_denied_response', gatekeeper_access_denied_response_400_mock):
            try:
                self.client.post(
                    reverse('gatekeeper:upload'),
                    data                                = '',
                    content_type                        = 'application/octet-stream',
                    HTTP_CONCENT_CLIENT_PUBLIC_KEY      = b64encode(settings.CONCENT_PUBLIC_KEY).decode('ascii'),
                )
            except Http400:
                pass

        self.assertEqual(Client.objects.count(), 0)

    def test_non_api_view_should_not_rollback_changes_on_200_response(self):

        with mock.patch('gatekeeper.views.gatekeeper_access_denied_response', gatekeeper_access_denied_response_200_mock):
            response = self.client.post(
                reverse('gatekeeper:upload'),
                data                                = '',
                content_type                        = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY      = b64encode(settings.CONCENT_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response.status_code,   200)
        self.assertEqual(Client.objects.count(), 1)


def message_to_dict(message_from_view):
    message_to_review = {
        "node_name":            message_from_view.node_name,
        "task_id":              message_from_view.task_id,
        "perf_index":           message_from_view.perf_index,
        "price":                message_from_view.price,
        "max_resource_size":    message_from_view.max_resource_size,
        "max_memory_size":      message_from_view.max_memory_size,
        "num_cores":            message_from_view.num_cores,
    }
    return message_to_review
