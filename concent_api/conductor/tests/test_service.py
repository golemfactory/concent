import mock

from common.helpers import get_current_utc_timestamp
from common.helpers import parse_timestamp_to_utc_datetime
from conductor.exceptions import VerificationRequestAlreadyInitiatedError
from conductor.models import ResultTransferRequest
from conductor.models import UploadReport
from conductor.models import VerificationRequest
from conductor.service import update_upload_report
from core.tests.utils import ConcentIntegrationTestCase


class ConductorReportFinishedUploadTestCase(ConcentIntegrationTestCase):

    multi_db = True

    def setUp(self):
        super().setUp()
        self.path = 'path/to/file'
        self.result_transfer_request = ResultTransferRequest(
            subtask_id=self._get_uuid(),
            result_package_path=self.path,
        )
        self.result_transfer_request.full_clean()
        self.result_transfer_request.save()

    def test_that_update_upload_report_should_update_related_upload_reports(self):
        upload_report = UploadReport(
            path=self.path
        )
        upload_report.full_clean()
        upload_report.save()

        self.result_transfer_request.upload_finished = True
        self.result_transfer_request.full_clean()
        self.result_transfer_request.save()

        with mock.patch('conductor.service.transaction.on_commit') as transaction_on_commit:
            update_upload_report(
                self.path,
                self.result_transfer_request,
            )

        upload_report.refresh_from_db()
        self.assertEqual(upload_report.result_transfer_request, self.result_transfer_request)

        transaction_on_commit.assert_not_called()

    def test_that_update_upload_report_should_schedule_result_upload_finished_if_result_transfer_request_upload_finished_is_false(self):
        with mock.patch('conductor.service.transaction.on_commit') as transaction_on_commit:
            with mock.patch('conductor.service.result_upload_finished.delay') as result_upload_finished:
                update_upload_report(
                    self.path,
                    self.result_transfer_request,
                )

        self.result_transfer_request.refresh_from_db()
        self.assertTrue(self.result_transfer_request.upload_finished)

        transaction_on_commit.assert_called_once()
        result_upload_finished.assert_not_called()

    def test_that_update_upload_report_should_raise_exception_when_related_verification_request_exist(self):
        verification_request = VerificationRequest(
            subtask_id=self._get_uuid(),
            result_package_path=self.path,
            source_package_path=self.path,
            verification_deadline=parse_timestamp_to_utc_datetime(get_current_utc_timestamp())
        )
        verification_request.full_clean()
        verification_request.save()

        with mock.patch('conductor.service.transaction.on_commit') as transaction_on_commit:
            with self.assertRaises(VerificationRequestAlreadyInitiatedError):
                update_upload_report(
                    self.path,
                    self.result_transfer_request,
                )

        self.result_transfer_request.refresh_from_db()
        self.assertFalse(self.result_transfer_request.upload_finished)

        transaction_on_commit.assert_not_called()
