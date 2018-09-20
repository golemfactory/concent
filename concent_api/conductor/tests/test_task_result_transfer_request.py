import mock

from conductor.models import ResultTransferRequest
from conductor.models import UploadReport
from conductor.tasks import result_transfer_request
from core.tests.utils import ConcentIntegrationTestCase


class ConductorResultTransferRequestTaskTestCase(ConcentIntegrationTestCase):

    multi_db = True

    def setUp(self):
        super().setUp()
        self.subtask_id = self._get_uuid()
        self.path = 'path/to/file'

    def test_that_result_transfer_request_create_result_transfer_request(self):
        result_transfer_request(
            self.subtask_id,
            self.path,
        )

        result_transfer_request_obj = ResultTransferRequest.objects.first()

        self.assertIsNotNone(result_transfer_request_obj)
        self.assertEqual(result_transfer_request_obj.subtask_id, self.subtask_id)
        self.assertEqual(result_transfer_request_obj.result_package_path, self.path)

    def test_that_result_transfer_request_create_result_transfer_request_and_call_report_finished_upload_if_related_upload_report_exists(self):
        upload_report = UploadReport(
            path=self.path
        )
        upload_report.full_clean()
        upload_report.save()

        with mock.patch('conductor.tasks.report_finished_upload') as report_finished_upload:
            result_transfer_request(
                self.subtask_id,
                self.path,
            )

        report_finished_upload.assert_called_once()
