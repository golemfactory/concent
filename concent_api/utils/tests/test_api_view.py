import json
from base64                         import b64encode

from django.conf                    import settings
from django.test                    import TestCase, RequestFactory, override_settings
from django.views.decorators.http   import require_POST

from golem_messages.message         import WantToComputeTask
from golem_messages                 import dump, load

from utils.api_view                 import api_view
from utils.testing_helpers          import generate_ecc_key_pair


(CONCENT_PRIVATE_KEY, CONCENT_PUBLIC_KEY) = generate_ecc_key_pair()


@override_settings(
    CONCENT_PRIVATE_KEY = CONCENT_PRIVATE_KEY,
    CONCENT_PUBLIC_KEY  = CONCENT_PUBLIC_KEY,
)
class ApiViewTestCase(TestCase):
    def setUp(self):
        self.request_factory = RequestFactory()
        self.want_to_compute = WantToComputeTask(
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
        def dummy_view(request, message):                                       # pylint: disable=unused-argument
            nonlocal decoded_message
            decoded_message = message
            return None

        request = self.request_factory.post("/dummy-url/", content_type = 'application/octet-stream', data = raw_message)
        request.META['HTTP_CONCENT_CLIENT_PUBLIC_KEY'] = b64encode(settings.CONCENT_PUBLIC_KEY).decode('ascii')

        dummy_view(request)                                                     # pylint: disable=no-value-for-parameter

        message_to_test = message_to_dict(decoded_message)
        self.assertIsInstance(decoded_message, WantToComputeTask)
        self.assertEqual(message_to_test, self.message_to_view)

    def test_api_view_should_encode_golem_message_returned_from_view(self):

        @api_view
        def dummy_view(request, message):                                       # pylint: disable=unused-argument
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
        def dummy_view(request, message):                                       # pylint: disable=unused-argument
            return self.want_to_compute

        request = self.request_factory.post("/dummy-url/", content_type = 'application/x-www-form-urlencoded', data = self.want_to_compute)
        request.META['HTTP_CONCENT_CLIENT_PUBLIC_KEY'] = b64encode(settings.CONCENT_PUBLIC_KEY).decode('ascii')

        response = dummy_view(request)                                          # pylint: disable=no-value-for-parameter

        json_response = json.loads(response.content.decode())                   # pylint: disable=no-member

        self.assertEqual(response.status_code, 415)                             # pylint: disable=no-member
        self.assertIn('error', json_response)

    def test_api_view_should_return_http_415_when_request_content_type_is_appplication_json(self):

        @api_view
        def dummy_view(request, message):                                       # pylint: disable=unused-argument
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
