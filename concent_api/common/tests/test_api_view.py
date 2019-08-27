import json
from contextlib import suppress

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
from golem_messages.factories       import tasks
from golem_messages.factories.tasks import ComputeTaskDefFactory
from golem_messages.factories.tasks import WantToComputeTaskFactory
from golem_messages.utils import encode_hex

from common.constants import ErrorCode
from common.helpers import get_current_utc_timestamp
from common.helpers import sign_message
from common.testing_helpers import generate_ecc_key_pair
from core.decorators import handle_errors_and_responses
from core.decorators import require_golem_message
from core.exceptions import Http400
from core.message_handlers import store_subtask
from core.models import Client
from core.models import Subtask
from core.utils import hex_to_bytes_convert

(CONCENT_PRIVATE_KEY,   CONCENT_PUBLIC_KEY)   = generate_ecc_key_pair()
(PROVIDER_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY)  = generate_ecc_key_pair()
(PROVIDER_ETHEREUM_PRIVATE_KEY,  PROVIDER_ETHERUM_PUBLIC_KEY)  = generate_ecc_key_pair()
(REQUESTOR_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY) = generate_ecc_key_pair()
(REQUESTOR_ETHEREUM_PRIVATE_KEY,  REQUESTOR_ETHERUM_PUBLIC_KEY)  = generate_ecc_key_pair()


class CustomException(Exception):
    pass


@override_settings(
    CONCENT_PRIVATE_KEY = CONCENT_PRIVATE_KEY,
    CONCENT_PUBLIC_KEY  = CONCENT_PUBLIC_KEY,
)
class ApiViewTestCase(TestCase):
    def setUp(self):
        self.request_factory = RequestFactory()
        self.want_to_compute = WantToComputeTaskFactory()
        self.message_to_view = {
            "task_id":              self.want_to_compute.task_id,               # pylint: disable=no-member
            "perf_index":           self.want_to_compute.perf_index,            # pylint: disable=no-member
            "price":                self.want_to_compute.price,                 # pylint: disable=no-member
            "max_resource_size":    self.want_to_compute.max_resource_size,     # pylint: disable=no-member
            "max_memory_size":      self.want_to_compute.max_memory_size,       # pylint: disable=no-member
        }
        deadline_offset = 10
        message_timestamp = get_current_utc_timestamp() + deadline_offset
        compute_task_def = tasks.ComputeTaskDefFactory(
            deadline=message_timestamp,
        )
        task_to_compute = tasks.TaskToComputeFactory(
            compute_task_def=compute_task_def,
            requestor_public_key=encode_hex(REQUESTOR_PUBLIC_KEY),
            provider_public_key=encode_hex(PROVIDER_PUBLIC_KEY),
            price=0,
        )
        task_to_compute = load(
            dump(
                task_to_compute,
                REQUESTOR_PRIVATE_KEY,
                settings.CONCENT_PUBLIC_KEY,
            ),
            settings.CONCENT_PRIVATE_KEY,
            REQUESTOR_PUBLIC_KEY,
            check_time=False,
        )

        self.force_report_computed_task = message.concents.ForceReportComputedTask()
        self.force_report_computed_task.report_computed_task = message.tasks.ReportComputedTask()
        self.force_report_computed_task.report_computed_task.task_to_compute = task_to_compute

    def test_api_view_should_return_golem_message_as_octet_stream(self):
        raw_message = dump(
            self.force_report_computed_task,
            settings.CONCENT_PRIVATE_KEY,
            settings.CONCENT_PUBLIC_KEY,
        )

        decoded_message = None

        @require_golem_message
        @handle_errors_and_responses(database_name='default')
        def dummy_view(request, _message, _client_public_key):  # pylint: disable=unused-argument
            nonlocal decoded_message
            decoded_message = _message
            return None
        request = self.request_factory.post(
            "/dummy-url/",
            content_type='application/octet-stream',
            data=raw_message,
            HTTP_X_GOLEM_MESSAGES=settings.GOLEM_MESSAGES_VERSION,
        )

        dummy_view(request)                                                     # pylint: disable=no-value-for-parameter

        self.assertIsInstance(decoded_message, message.concents.ForceReportComputedTask)
        self.assertEqual(decoded_message, self.force_report_computed_task)

    def test_api_view_should_return_http_415_when_request_content_type_is_not_supported(self):

        @require_golem_message
        @handle_errors_and_responses(database_name='default')
        def dummy_view(request, _message, _client_public_key):  # pylint: disable=unused-argument
            return self.want_to_compute

        request = self.request_factory.post("/dummy-url/", content_type = 'application/x-www-form-urlencoded', data = self.want_to_compute)

        response = dummy_view(request)                                          # pylint: disable=no-value-for-parameter

        json_response = json.loads(response.content.decode())                   # pylint: disable=no-member

        self.assertEqual(response.status_code, 415)                             # pylint: disable=no-member
        self.assertIn('error', json_response)

    def test_api_view_should_return_http_415_when_request_content_type_is_appplication_json(self):

        @require_golem_message
        @handle_errors_and_responses(database_name='default')
        def dummy_view(request, _message, _client_public_key):  # pylint: disable=unused-argument
            return self.message_to_view

        request = self.request_factory.post("/dummy-url/", content_type = 'application/json', data = json.dumps(self.message_to_view))

        response = dummy_view(request)                                          # pylint: disable=no-value-for-parameter

        self.assertEqual(response['content-type'], "application/json")
        self.assertEqual(response.status_code, 415)                             # pylint: disable=no-member

    def test_request_with_not_allowed_http_method_should_return_405_error(self):
        """
        Tests if request to Concent with will return HTTP 405 error
        if not allowed HTTP method by view is used.
        """
        raw_message = dump(
            self.force_report_computed_task,
            settings.CONCENT_PRIVATE_KEY,
            settings.CONCENT_PUBLIC_KEY,
        )

        @require_golem_message
        @handle_errors_and_responses(database_name='default')
        @require_POST
        def dummy_view(_request, _message, _client_public_key):
            self.fail()

        request = self.request_factory.put(
            "/dummy-url/",
            content_type='application/octet-stream',
            data=raw_message,
            HTTP_X_GOLEM_MESSAGES = settings.GOLEM_MESSAGES_VERSION,
        )

        response = dummy_view(request)  # pylint: disable=no-value-for-parameter,assignment-from-no-return

        self.assertEqual(response.status_code,  405)


def _create_client_and_raise_http400_error_mock(*_args, **_kwargs):
    _create_client_mock_and_return_none()
    raise Http400('', error_code=ErrorCode.MESSAGE_UNEXPECTED)


def _create_client_and_raise_http500_exception_mock(*_args, **_kwargs):
    _create_client_mock_and_return_none()
    raise CustomException


def _create_client_mock_and_return_none(*_args, **_kwargs) -> None:
    number_of_clients = Client.objects.count()
    Client.objects.create(public_key_bytes=generate_ecc_key_pair()[1])
    assert Client.objects.count() == number_of_clients + 1
    return None


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

    multi_db = True

    def setUp(self):
        super().setUp()

        deadline_offset = 10
        message_timestamp = get_current_utc_timestamp() + deadline_offset
        self.compute_task_def = ComputeTaskDefFactory()
        self.compute_task_def['deadline'] = message_timestamp
        want_to_compute_task = WantToComputeTaskFactory(
            provider_public_key=encode_hex(PROVIDER_PUBLIC_KEY),
        )
        want_to_compute_task = sign_message(want_to_compute_task, PROVIDER_PRIVATE_KEY)
        task_to_compute = tasks.TaskToComputeFactory(
            compute_task_def=self.compute_task_def,
            requestor_public_key=encode_hex(REQUESTOR_PUBLIC_KEY),
            requestor_ethereum_public_key=encode_hex(REQUESTOR_ETHERUM_PUBLIC_KEY),
            want_to_compute_task=want_to_compute_task,
            price=1,
        )
        task_to_compute.generate_ethsig(REQUESTOR_ETHEREUM_PRIVATE_KEY)
        task_to_compute.sign_all_promissory_notes(
            deposit_contract_address=settings.GNT_DEPOSIT_CONTRACT_ADDRESS,
            private_key=REQUESTOR_ETHEREUM_PRIVATE_KEY,
        )
        self.task_to_compute = load(
            dump(
                task_to_compute,
                REQUESTOR_PRIVATE_KEY,
                settings.CONCENT_PUBLIC_KEY,
            ),
            settings.CONCENT_PRIVATE_KEY,
            REQUESTOR_PUBLIC_KEY,
            check_time=False,
        )
        report_computed_task = tasks.ReportComputedTaskFactory(
            task_to_compute=self.task_to_compute
        )
        self.report_computed_task = load(
            dump(
                report_computed_task,
                PROVIDER_PRIVATE_KEY,
                settings.CONCENT_PUBLIC_KEY,
            ),
            settings.CONCENT_PRIVATE_KEY,
            PROVIDER_PUBLIC_KEY,
            check_time=False,
        )
        self.force_report_computed_task = message.concents.ForceReportComputedTask(
            report_computed_task=self.report_computed_task
        )

        self.force_get_task_result = message.concents.ForceGetTaskResult(
            report_computed_task=self.report_computed_task
        )

    def test_that_api_view_should_not_rollback_changes_from_first_transaction_when_second_raises_exception(self):
        self.assertEqual(Client.objects.count(), 0)
        with mock.patch(
            'core.subtask_helpers.get_one_or_none',
            side_effect=_create_client_mock_and_return_none
        ) as _update_timed_out_subtask_correct_response_mock_function, \
            mock.patch(
            'core.message_handlers.get_one_or_none',
            side_effect=_create_client_and_raise_http400_error_mock
        ) as _create_client_and_raise_http400_error_mock_function:
            self.client.post(
                reverse('core:send'),
                data=dump(
                    self.force_get_task_result,
                    PROVIDER_PRIVATE_KEY,
                    CONCENT_PUBLIC_KEY
                ),
                content_type='application/octet-stream',
                HTTP_X_GOLEM_MESSAGES=settings.GOLEM_MESSAGES_VERSION,
            )
        _update_timed_out_subtask_correct_response_mock_function.assert_called()
        _create_client_and_raise_http400_error_mock_function.assert_called()

        self.assertEqual(Client.objects.count(), 1)

    def test_api_view_should_rollback_changes_on_500_error(self):

        store_subtask(
            task_id=self.compute_task_def['task_id'],
            subtask_id=self.compute_task_def['subtask_id'],
            provider_public_key=hex_to_bytes_convert(self.report_computed_task.task_to_compute.provider_public_key),
            requestor_public_key=hex_to_bytes_convert(self.report_computed_task.task_to_compute.requestor_public_key),
            state=Subtask.SubtaskState.FORCING_RESULT_TRANSFER,
            next_deadline=(get_current_utc_timestamp() - 10),
            task_to_compute=self.task_to_compute,
            report_computed_task=self.report_computed_task,
            force_get_task_result=self.force_get_task_result,
        )
        self.assertEqual(Client.objects.count(), 2)

        with mock.patch(
            'core.subtask_helpers.verify_file_status',
            side_effect=_create_client_and_raise_http500_exception_mock
        ) as _create_client_and_raise_http500_error_mock_function:
            with suppress(CustomException):
                self.client.post(
                    reverse('core:send'),
                    data=dump(
                        self.force_report_computed_task,
                        PROVIDER_PRIVATE_KEY,
                        CONCENT_PUBLIC_KEY
                    ),
                    content_type='application/octet-stream',
                    HTTP_X_GOLEM_MESSAGES=settings.GOLEM_MESSAGES_VERSION,
                )

        _create_client_and_raise_http500_error_mock_function.assert_called()
        self.assertEqual(Client.objects.count(), 2)

    def test_api_view_should_rollback_changes_on_400_error(self):

        store_subtask(
            task_id=self.compute_task_def['task_id'],
            subtask_id=self.compute_task_def['subtask_id'],
            provider_public_key=hex_to_bytes_convert(self.report_computed_task.task_to_compute.provider_public_key),
            requestor_public_key=hex_to_bytes_convert(self.report_computed_task.task_to_compute.requestor_public_key),
            state=Subtask.SubtaskState.FORCING_RESULT_TRANSFER,
            next_deadline=(get_current_utc_timestamp() - 10),
            task_to_compute=self.task_to_compute,
            report_computed_task= self.report_computed_task,
            force_get_task_result=self.force_get_task_result,
        )
        self.assertEqual(Client.objects.count(), 2)
        with mock.patch(
            'core.subtask_helpers.verify_file_status',
            side_effect=_create_client_and_raise_http400_error_mock
        ) as _create_client_and_raise_error_mock_function:
            self.client.post(
                reverse('core:send'),
                data=dump(
                    self.force_report_computed_task,
                    PROVIDER_PRIVATE_KEY,
                    CONCENT_PUBLIC_KEY
                ),
                content_type='application/octet-stream',
                HTTP_X_GOLEM_MESSAGES=settings.GOLEM_MESSAGES_VERSION,
            )

        _create_client_and_raise_error_mock_function.assert_called()
        self.assertEqual(Client.objects.count(), 2)

    def test_api_view_should_not_rollback_changes_on_correct_response(self):
        with mock.patch(
            'core.subtask_helpers.get_one_or_none',
            side_effect=_create_client_mock_and_return_none
        ) as _update_timed_out_subtask_correct_response_mock_function:
            response = self.client.post(
                reverse('core:send'),
                data=dump(
                    self.force_report_computed_task,
                    PROVIDER_PRIVATE_KEY,
                    CONCENT_PUBLIC_KEY
                ),
                content_type='application/octet-stream',
                HTTP_X_GOLEM_MESSAGES=settings.GOLEM_MESSAGES_VERSION,
            )

        _update_timed_out_subtask_correct_response_mock_function.assert_called()
        self.assertEqual(response.status_code,   202)
        self.assertEqual(Client.objects.count(), 3)  # 3 because view itself is creating 2 clients.

    def test_non_api_view_should_rollback_changes_on_500_error(self):

        with mock.patch(
            'gatekeeper.views.gatekeeper_access_denied_response',
            side_effect=_create_client_and_raise_http500_exception_mock
        ) as gatekeeper_access_denied_response_500_mock_function:
            with suppress(CustomException):
                self.client.post(
                    reverse('gatekeeper:upload'),
                    data                                = '',
                    content_type                        = 'application/octet-stream',
                )

        gatekeeper_access_denied_response_500_mock_function.assert_called()
        self.assertEqual(Client.objects.count(), 0)

    def test_non_api_view_should_rollback_changes_on_400_error(self):

        with mock.patch(
            'gatekeeper.views.gatekeeper_access_denied_response',
            side_effect=_create_client_and_raise_http400_error_mock
        ) as gatekeeper_access_denied_response_400_mock_function:
            try:
                self.client.post(
                    reverse('gatekeeper:upload'),
                    data                                = '',
                    content_type                        = 'application/octet-stream',
                )
            except Http400:
                pass

        gatekeeper_access_denied_response_400_mock_function.assert_called()
        self.assertEqual(Client.objects.count(), 0)

    def test_non_api_view_should_not_rollback_changes_on_200_response(self):

        with mock.patch(
            'gatekeeper.views.gatekeeper_access_denied_response',
            side_effect=gatekeeper_access_denied_response_200_mock
        ) as gatekeeper_access_denied_response_200_mock_function:
            response = self.client.post(
                reverse('gatekeeper:upload'),
                data                                = '',
                content_type                        = 'application/octet-stream',
            )

        gatekeeper_access_denied_response_200_mock_function.assert_called()
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
