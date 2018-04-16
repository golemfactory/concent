from django.test import override_settings
import mock

from golem_messages.message import FileTransferToken

from core.tests.utils import ConcentIntegrationTestCase
from core.exceptions import UnexpectedResponse

from core.transfer_operations import create_file_transfer_token
from core.transfer_operations import request_upload_status

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
        file_transfer_token = create_file_transfer_token(
            report_computed_task,
            self.REQUESTOR_PUBLIC_KEY,
            FileTransferToken.Operation.upload,
        )

        with mock.patch('core.transfer_operations.send_request_to_cluster_storage', mock_send_request_to_cluster_correct_response):
            cluster_response = request_upload_status(
                file_transfer_token,
                report_computed_task,
            )

        self.assertEqual(cluster_response, True)

        with mock.patch('core.transfer_operations.send_request_to_cluster_storage', mock_send_incorrect_request_to_cluster_incorrect_response):
            cluster_response_2 = request_upload_status(
                file_transfer_token,
                report_computed_task,
            )

        self.assertEqual(cluster_response_2, False)

        with self.assertRaises(UnexpectedResponse):
            with mock.patch('core.transfer_operations.send_request_to_cluster_storage', mock_send_incorrect_request_to_cluster_unexpected_response):
                request_upload_status(
                    file_transfer_token,
                    report_computed_task,
                )
