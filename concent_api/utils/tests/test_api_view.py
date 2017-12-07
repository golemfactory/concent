import json
from base64                 import b64encode

from django.test            import TestCase, RequestFactory, override_settings
from django.conf            import settings
from golem_messages.message import MessageWantToComputeTask
from golem_messages         import dump, load

from utils.api_view         import api_view


@override_settings(
    CONCENT_PRIVATE_KEY = b'l\xcdh\x19\xeb$>\xbcG\xa1\xc7v\xe8\xd7o\x0c\xbf\x0e\x0fM\x89lw\x1e\xd7K\xd6Hnv$\xa2',
    CONCENT_PUBLIC_KEY  = b'\xf3\x97\x19\xcdX\xda\x86tiP\x1c&\xd39M\x9e\xa4\xddb\x89\xb5,]O\xd5cR\x84\xb85\xed\xc9\xa17e,\xb2s\xeb\n1\xcaN.l\xba\xc3\xb7\xc2\xba\xff\xabN\xde\xb3\x0b\xa6l\xbf6o\x81\xe0;'
)
class ApiViewTestCase(TestCase):
    def setUp(self):
        self.request_factory = RequestFactory()
        self.message_want_to_compute = MessageWantToComputeTask(
            node_name           = 1,
            task_id             = 2,
            perf_index          = 3,
            price               = 4,
            max_resource_size   = 5,
            max_memory_size     = 6,
            num_cores           = 7,
        )
        self.message_to_view = {
            "node_name":            self.message_want_to_compute.node_name,
            "task_id":              self.message_want_to_compute.task_id,
            "perf_index":           self.message_want_to_compute.perf_index,
            "price":                self.message_want_to_compute.price,
            "max_resource_size":    self.message_want_to_compute.max_resource_size,
            "max_memory_size":      self.message_want_to_compute.max_memory_size,
            "num_cores":            self.message_want_to_compute.num_cores,
        }

    def test_api_view_should_return_golem_message_as_octet_stream(self):
        raw_message = dump(
            self.message_want_to_compute,
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
        self.assertIsInstance(decoded_message, MessageWantToComputeTask)
        self.assertEqual(message_to_test, self.message_to_view)

    def test_api_view_should_encode_golem_message_returned_from_view(self):

        @api_view
        def dummy_view(request, message):                                       # pylint: disable=unused-argument
            return self.message_want_to_compute

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
            return self.message_want_to_compute

        request = self.request_factory.post("/dummy-url/", content_type = 'application/x-www-form-urlencoded', data = self.message_want_to_compute)
        request.META['HTTP_CONCENT_CLIENT_PUBLIC_KEY'] = b64encode(settings.CONCENT_PUBLIC_KEY).decode('ascii')

        response = dummy_view(request)                                          # pylint: disable=no-value-for-parameter

        json_response = json.loads(response.content.decode())                   # pylint: disable=no-member

        self.assertEqual(response.status_code, 415)                             # pylint: disable=no-member
        self.assertIn('error', json_response)

    def test_api_view_should_return_json_when_view_returns_a_dict(self):

        @api_view
        def dummy_view(request, message):                                       # pylint: disable=unused-argument
            return self.message_to_view

        request = self.request_factory.post("/dummy-url/", content_type='application/json', data=json.dumps(self.message_to_view))
        request.META['HTTP_CONCENT_CLIENT_PUBLIC_KEY'] = b64encode(settings.CONCENT_PUBLIC_KEY).decode('ascii')

        response = dummy_view(request)                                          # pylint: disable=no-value-for-parameter

        response_dict = json.loads(response.content.decode('ascii'))            # pylint: disable=no-member
        self.assertEqual(response['content-type'], "application/json")          # pylint: disable=unsubscriptable-object
        self.assertEqual(response.status_code, 200)                             # pylint: disable=no-member
        self.assertEqual(response_dict, self.message_to_view)

    def test_api_view_should_deserialize_json_when_content_type_is_application_json(self):
        message_inside_view = None

        @api_view
        def dummy_view(request, message):                                       # pylint: disable=unused-argument
            nonlocal message_inside_view
            message_inside_view = message
            return None

        request = self.request_factory.post("/dummy-url/", content_type='application/json', data=json.dumps(self.message_to_view))
        request.META['HTTP_CONCENT_CLIENT_PUBLIC_KEY'] = b64encode(settings.CONCENT_PUBLIC_KEY).decode('ascii')

        dummy_view(request)                                                     # pylint: disable=no-value-for-parameter

        self.assertIsInstance(message_inside_view, dict)                        # pylint: disable=no-member
        self.assertEqual(message_inside_view, self.message_to_view)


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
