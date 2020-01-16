import mock
import pytest
from assertpy import assert_that

from golem_messages.factories.tasks import ComputeTaskDefFactory

from common.helpers import get_current_utc_timestamp
from common.helpers import parse_timestamp_to_utc_datetime
from conductor.exceptions import VerificationRequestAlreadyInitiatedError
from conductor.models import BlenderCropScriptParameters
from conductor.models import ResultTransferRequest
from conductor.models import UploadReport
from conductor.models import VerificationRequest
from conductor.service import update_upload_report
from conductor.service import _store_blender_crop_script_parameters
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

        with mock.patch('conductor.service.result_upload_finished.delay') as result_upload_finished:
            update_upload_report(
                self.path,
                self.result_transfer_request,
            )

        upload_report.refresh_from_db()
        self.assertEqual(upload_report.result_transfer_request, self.result_transfer_request)

        result_upload_finished.assert_not_called()

    def test_that_update_upload_report_should_schedule_result_upload_finished_if_result_transfer_request_upload_finished_is_false(self):
        with mock.patch('conductor.service.transaction.on_commit') as transaction_on_commit:
            update_upload_report(
                self.path,
                self.result_transfer_request,
            )

        self.result_transfer_request.refresh_from_db()
        self.assertTrue(self.result_transfer_request.upload_finished)

        transaction_on_commit.assert_called_once()

    def test_that_update_upload_report_should_raise_exception_when_related_verification_request_exist(self):
        verification_request = VerificationRequest(
            subtask_id=self._get_uuid(),
            result_package_path=self.path,
            source_package_path=self.path,
            verification_deadline=parse_timestamp_to_utc_datetime(get_current_utc_timestamp())
        )
        verification_request.full_clean()
        verification_request.save()

        with mock.patch('conductor.service.result_upload_finished.delay') as result_upload_finished:
            with self.assertRaises(VerificationRequestAlreadyInitiatedError):
                update_upload_report(
                    self.path,
                    self.result_transfer_request,
                )

        self.result_transfer_request.refresh_from_db()
        self.assertFalse(self.result_transfer_request.upload_finished)

        result_upload_finished.assert_not_called()


class TestBlenderCropScriptParameters(object):
    compute_task_def = None

    @pytest.fixture(autouse=True)
    def setup(self):
        self.compute_task_def = ComputeTaskDefFactory()
        self.compute_task_def["extra_data"] = {
            "resolution": [400, 400],
            "samples": 1,
            "use_compositing": False,
        }

    @pytest.mark.django_db
    @pytest.mark.parametrize(
        ['borders_x', 'borders_y'], [
            [[0.0, 1.0], [0.0, 1.0]],
            [['0.0', '1.0'], ['0.0', '1.0']],
            [[0, 1], [0, 1]],
            [[0.1, 0.2], [0.3333333333333, 0.66666]],
            [[0, 1], ['0.33333', '0.66666666666666666']],
        ]
    )
    def test_store_blender_crop_script_parameters(self, borders_x, borders_y):
        blender_crop_script_parameters = dict(
            resolution=self.compute_task_def['extra_data']['resolution'],
            samples=self.compute_task_def['extra_data']['samples'],
            use_compositing=self.compute_task_def['extra_data']['use_compositing'],
            borders_x=borders_x,
            borders_y=borders_y,
        )
        blender_parameters = _store_blender_crop_script_parameters(blender_crop_script_parameters)
        assert_that(blender_parameters).is_instance_of(BlenderCropScriptParameters)
