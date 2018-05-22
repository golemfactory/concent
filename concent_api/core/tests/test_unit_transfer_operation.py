import datetime
from django.conf import settings
from django.test import override_settings
from django.test import TestCase
import mock
from freezegun import freeze_time

from golem_messages.factories.tasks import ReportComputedTaskFactory
from golem_messages.message import FileTransferToken

from core.tests.utils import ConcentIntegrationTestCase
from core.exceptions import UnexpectedResponse
from core.transfer_operations import create_file_transfer_token_for_concent
from core.transfer_operations import create_file_transfer_token_for_golem_client
from core.transfer_operations import request_upload_status
from utils.helpers import calculate_maximum_download_time
from utils.helpers import parse_datetime_to_timestamp

from utils.testing_helpers import generate_ecc_key_pair


def mock_send_request_to_cluster_correct_response(_headers, _request_http):
    mocked_object = mock.Mock()
    mocked_object.status_code = 200
    return mocked_object


def mock_send_incorrect_request_to_cluster_incorrect_response(_headers, _request_http):
    mocked_object = mock.Mock()
    mocked_object.status_code = 404
    return mocked_object


def mock_send_incorrect_request_to_cluster_unexpected_response(_headers, _request_http):
    mocked_object = mock.Mock()
    mocked_object.status_code = 500
    return mocked_object


(CONCENT_PRIVATE_KEY, CONCENT_PUBLIC_KEY)       = generate_ecc_key_pair()


@override_settings(
    CONCENT_PRIVATE_KEY       = CONCENT_PRIVATE_KEY,
    CONCENT_PUBLIC_KEY        = CONCENT_PUBLIC_KEY,
)
class RequestUploadStatusTest(ConcentIntegrationTestCase):
    def test_properly_work_of_request_upload_status_function(self):

        report_computed_task = self._get_deserialized_report_computed_task(
            subtask_id = '1',
            task_to_compute = self._get_deserialized_task_to_compute(
                task_id                         = '1/1',
                subtask_id                      = '1',
            )
        )

        with mock.patch(
            'core.transfer_operations.send_request_to_storage_cluster',
            side_effect=mock_send_request_to_cluster_correct_response
        ) as mock_send_request_to_cluster_correct_response_function:
            cluster_response = request_upload_status(report_computed_task)

        self.assertEqual(cluster_response, True)
        mock_send_request_to_cluster_correct_response_function.assert_called()

        with mock.patch(
            'core.transfer_operations.send_request_to_storage_cluster',
            side_effect=mock_send_incorrect_request_to_cluster_incorrect_response
        ) as mock_send_incorrect_request_to_cluster_incorrect_response_function:
            cluster_response_2 = request_upload_status(
                report_computed_task)

        self.assertEqual(cluster_response_2, False)
        mock_send_incorrect_request_to_cluster_incorrect_response_function.assert_called()

        with self.assertRaises(UnexpectedResponse):
            with mock.patch(
                'core.transfer_operations.send_request_to_storage_cluster',
                side_effect=mock_send_incorrect_request_to_cluster_unexpected_response
            ) as mock_send_incorrect_request_to_cluster_unexpected_response_function:
                request_upload_status(report_computed_task)

        mock_send_incorrect_request_to_cluster_unexpected_response_function.assert_called()


@override_settings(
    CONCENT_PRIVATE_KEY=CONCENT_PRIVATE_KEY,
    CONCENT_PUBLIC_KEY=CONCENT_PUBLIC_KEY,
    MINIMUM_UPLOAD_RATE=1,
    DOWNLOAD_LEADIN_TIME= 10,
    CONCENT_MESSAGING_TIME=20,
)
class FileTransferTokenCreationTest(TestCase):
    def setUp(self):
        self.time = datetime.datetime.strptime("2017-11-17 10:00:00", "%Y-%m-%d %H:%M:%S")
        self.deadline = 10
        self.authorized_client_public_key = b'7' * 64
        self.report_computed_task = ReportComputedTaskFactory(
            task_to_compute__compute_task_def__deadline=parse_datetime_to_timestamp(self.time) + self.deadline
        )

    def test_that_file_transfer_token_for_concent_is_never_out_of_date(self):
        report_computed_task = ReportComputedTaskFactory()

        token = create_file_transfer_token_for_concent(
            report_computed_task,
            FileTransferToken.Operation.download
        )
        self.assertTrue(token.timestamp < token.token_expiration_deadline)

    def test_that_download_file_transfer_token_for_golem_client_is_can_be_out_of_date(self):
        with freeze_time(self.time):
            new_time = self._get_deadline_exceeded_time_for_download_token(self.report_computed_task.size)
            with freeze_time(new_time):
                download_token = create_file_transfer_token_for_golem_client(
                    self.report_computed_task,
                    self.authorized_client_public_key,
                    FileTransferToken.Operation.download
                )
                self.assertTrue(download_token.timestamp > download_token.token_expiration_deadline)

    def test_that_upload_file_transfer_token_for_golem_client_is_can_be_out_of_date(self):
        with freeze_time(self.time):
            new_time = self._get_deadline_exceeded_time_for_upload_token()
            with freeze_time(new_time):
                upload_token = create_file_transfer_token_for_golem_client(
                    self.report_computed_task,
                    self.authorized_client_public_key,
                    FileTransferToken.Operation.download
                )
                self.assertTrue(upload_token.timestamp > upload_token.token_expiration_deadline)

    def _get_deadline_exceeded_time_for_upload_token(self):
        return self.time + datetime.timedelta(
            seconds=10 + self.deadline + 1
        )

    def _get_deadline_exceeded_time_for_download_token(self, size):
        return self.time + datetime.timedelta(
            seconds=3 * settings.CONCENT_MESSAGING_TIME + 2 * calculate_maximum_download_time(size) + self.deadline + 1
        )
