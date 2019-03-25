import mock

from django.urls import reverse

from common.helpers import get_current_utc_timestamp
from common.helpers import get_storage_result_file_path
from common.helpers import get_storage_source_file_path
from conductor.models import BlenderCropScriptParameters
from conductor.models import BlenderSubtaskDefinition
from conductor.models import ResultTransferRequest
from conductor.models import UploadReport
from conductor.models import VerificationRequest
from conductor.tasks import blender_verification_request
from core.message_handlers import store_subtask
from core.models import Subtask
from core.tests.utils import ConcentIntegrationTestCase


class ConductorVerificationIntegrationTest(ConcentIntegrationTestCase):

    multi_db = True

    def setUp(self):
        super().setUp()
        self.task_to_compute = self._get_deserialized_task_to_compute()
        self.compute_task_def = self.task_to_compute.compute_task_def
        self.blender_crop_script_parameters = dict(
            resolution=self.compute_task_def['extra_data']['resolution'],
            samples=self.compute_task_def['extra_data']['samples'],
            use_compositing=self.compute_task_def['extra_data']['use_compositing'],
            borders_x=self.compute_task_def['extra_data']['crops'][0]['borders_x'],
            borders_y=self.compute_task_def['extra_data']['crops'][0]['borders_y'],
        )
        self.source_package_path = get_storage_source_file_path(
            self.task_to_compute.subtask_id,
            self.task_to_compute.task_id,
        )
        self.result_package_path = get_storage_result_file_path(
            self.task_to_compute.subtask_id,
            self.task_to_compute.task_id,
        )
        self.report_computed_task = self._get_deserialized_report_computed_task(task_to_compute=self.task_to_compute)

        store_subtask(
            task_id=self.compute_task_def['task_id'],
            subtask_id=self.compute_task_def['subtask_id'],
            provider_public_key=self.PROVIDER_PUBLIC_KEY,
            requestor_public_key=self.REQUESTOR_PUBLIC_KEY,
            state=Subtask.SubtaskState.REPORTED,
            task_to_compute=self.report_computed_task.task_to_compute,
            report_computed_task=self.report_computed_task,
            next_deadline=None
        )

    def _prepare_verification_request_with_blender_subtask_definition(self):
        verification_request = VerificationRequest(
            subtask_id=self.compute_task_def['subtask_id'],
            source_package_path=self.source_package_path,
            result_package_path=self.result_package_path,
            verification_deadline=self._get_verification_deadline_as_datetime(
                get_current_utc_timestamp(),
                self.report_computed_task.size,
            ),
        )
        verification_request.full_clean()
        verification_request.save()

        blender_subtask_definition = BlenderSubtaskDefinition(
            verification_request=verification_request,
            output_format=BlenderSubtaskDefinition.OutputFormat.JPEG.name,  # pylint: disable=no-member
            scene_file=self.compute_task_def['extra_data']['scene_file'],
            blender_crop_script=self.compute_task_def['extra_data']['script_src'],
        )
        blender_subtask_definition.full_clean()
        blender_subtask_definition.save()

        return verification_request

    def test_conductor_should_return_404_when_file_path_parameter_not_matching_url_pattern_is_used(self):
        response = self.client.post(
            '/conductor/report-upload/',
            content_type = 'application/octet-stream',
        )

        self.assertEqual(response.status_code, 404)

    def test_conductor_should_create_upload_report(self):
        response = self.client.post(
            reverse(
                'conductor:report-upload',
                kwargs={
                    'file_path': self.source_package_path
                }
            ),
            content_type = 'application/octet-stream',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(UploadReport.objects.count(), 1)

        upload_report = UploadReport.objects.first()
        self.assertEqual(upload_report.path, self.source_package_path)
        self.assertEqual(upload_report.verification_request, None)

    def test_conductor_should_create_upload_report_and_link_to_related_verification_request(self):
        verification_request = self._prepare_verification_request_with_blender_subtask_definition()

        response = self.client.post(
            reverse(
                'conductor:report-upload',
                kwargs={
                    'file_path': self.source_package_path
                }
            ),
            content_type='application/octet-stream',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(UploadReport.objects.count(), 1)

        upload_report = UploadReport.objects.first()
        self.assertEqual(upload_report.path, self.source_package_path)
        self.assertEqual(upload_report.verification_request, verification_request)

    def test_conductor_should_create_upload_report_and_do_not_link_to_unrelated_verification_request(self):
        verification_request = VerificationRequest(
            subtask_id=self._get_uuid(),
            source_package_path='blender/source/bad/bad.bad.zip',
            result_package_path='blender/result/bad/bad.bad.zip',
            verification_deadline=self._get_verification_deadline_as_datetime(
                get_current_utc_timestamp(),
                self.report_computed_task.size,
            ),
        )
        verification_request.full_clean()
        verification_request.save()

        response = self.client.post(
            reverse(
                'conductor:report-upload',
                kwargs={
                    'file_path': self.source_package_path
                }
            ),
            content_type='application/octet-stream',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(UploadReport.objects.count(), 1)

        upload_report = UploadReport.objects.first()
        self.assertEqual(upload_report.path, self.source_package_path)
        self.assertEqual(upload_report.verification_request, None)

    def test_conductor_should_schedule_verification_order_task_if_all_related_upload_requests_have_reports(self):
        verification_request = self._prepare_verification_request_with_blender_subtask_definition()

        upload_report = UploadReport(
            path=verification_request.result_package_path,
            verification_request=verification_request,
        )
        upload_report.full_clean()
        upload_report.save()

        with mock.patch('conductor.views.transaction.on_commit') as mock_transaction_on_commit:
            response = self.client.post(
                reverse(
                    'conductor:report-upload',
                    kwargs={
                        'file_path': self.source_package_path
                    }
                ),
                content_type='application/octet-stream',
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(UploadReport.objects.count(), 2)

        upload_report = UploadReport.objects.last()
        self.assertEqual(upload_report.path, self.source_package_path)

        mock_transaction_on_commit.assert_called_once()

        verification_request.refresh_from_db()
        self.assertTrue(verification_request.upload_finished)

    def test_conductor_should_not_schedule_verification_order_task_if_it_was_already_scheduled_for_given_verification(self):
        verification_request = self._prepare_verification_request_with_blender_subtask_definition()

        upload_report = UploadReport(
            path=verification_request.result_package_path,
            verification_request=verification_request,
        )
        upload_report.full_clean()
        upload_report.save()

        with mock.patch('conductor.views.transaction.on_commit') as mock_transaction_on_commit:
            response = self.client.post(
                reverse(
                    'conductor:report-upload',
                    kwargs={
                        'file_path': self.source_package_path
                    }
                ),
                content_type='application/octet-stream',
            )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(UploadReport.objects.count(), 2)

            mock_transaction_on_commit.assert_called_once()

            verification_request.refresh_from_db()
            self.assertTrue(verification_request.upload_finished)

            response = self.client.post(
                reverse(
                    'conductor:report-upload',
                    kwargs={
                        'file_path': self.source_package_path
                    }
                ),
                content_type='application/octet-stream',
            )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(UploadReport.objects.count(), 3)
            self.assertEqual(mock_transaction_on_commit.call_count, 1)

    def test_that_conductor_should_schedule_verification_order_task_if_uploaded_file_path_was_not_existing_before_and_other_requirements_are_met(self):
        verification_request = self._prepare_verification_request_with_blender_subtask_definition()

        upload_report = UploadReport(
            path=verification_request.result_package_path,
            verification_request=verification_request,
        )
        upload_report.full_clean()
        upload_report.save()

        with mock.patch('conductor.views.transaction.on_commit') as mock_transaction_on_commit:
            response = self.client.post(
                reverse(
                    'conductor:report-upload',
                    kwargs={
                        'file_path': self.result_package_path
                    }
                ),
                content_type='application/octet-stream',
            )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(UploadReport.objects.count(), 2)

            mock_transaction_on_commit.assert_not_called()

            verification_request.refresh_from_db()
            self.assertFalse(verification_request.upload_finished)

            response = self.client.post(
                reverse(
                    'conductor:report-upload',
                    kwargs={
                        'file_path': self.source_package_path
                    }
                ),
                content_type='application/octet-stream',
            )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(UploadReport.objects.count(), 3)

            mock_transaction_on_commit.assert_called_once()

            verification_request.refresh_from_db()
            self.assertTrue(verification_request.upload_finished)

    def test_that_conductor_should_not_schedule_verification_order_task_if_same_file_was_uploaded_again(self):
        verification_request = self._prepare_verification_request_with_blender_subtask_definition()

        upload_report = UploadReport(
            path=verification_request.result_package_path,
            verification_request=verification_request,
        )
        upload_report.full_clean()
        upload_report.save()

        with mock.patch('conductor.views.upload_finished.delay') as mock_task:
            response = self.client.post(
                reverse(
                    'conductor:report-upload',
                    kwargs={
                        'file_path': self.result_package_path
                    }
                ),
                content_type='application/octet-stream',
            )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(UploadReport.objects.count(), 2)

            mock_task.assert_not_called()

            verification_request.refresh_from_db()
            self.assertFalse(verification_request.upload_finished)

    def test_that_conductor_should_call_update_upload_report_task_if_related_result_transfer_request_exists(self):
        result_transfer_request = ResultTransferRequest(
            subtask_id=self._get_uuid(),
            result_package_path=self.result_package_path,
        )
        result_transfer_request.full_clean()
        result_transfer_request.save()

        with mock.patch('conductor.views.update_upload_report') as update_upload_report:
            response = self.client.post(
                reverse(
                    'conductor:report-upload',
                    kwargs={
                        'file_path': self.result_package_path
                    }
                ),
                content_type='application/octet-stream',
            )

        self.assertEqual(response.status_code, 200)

        update_upload_report.assert_called_once()

    def test_blender_verification_request_task_should_create_verification_request_and_blender_subtask_definition(self):
        blender_verification_request(
            frames=self.compute_task_def['extra_data']['frames'],
            subtask_id=self.compute_task_def['subtask_id'],
            source_package_path=self.source_package_path,
            result_package_path=self.result_package_path,
            output_format=BlenderSubtaskDefinition.OutputFormat.JPEG.name,  # pylint: disable=no-member
            scene_file=self.compute_task_def['extra_data']['scene_file'],
            verification_deadline=self._get_verification_deadline_as_timestamp(
                get_current_utc_timestamp(),
                self.report_computed_task.size,
            ),
            blender_crop_script_parameters=self.blender_crop_script_parameters,
        )

        self.assertEqual(VerificationRequest.objects.count(), 1)

        verification_request = VerificationRequest.objects.first()
        self.assertEqual(verification_request.subtask_id,  self.compute_task_def['subtask_id'])
        self.assertEqual(verification_request.source_package_path, self.source_package_path)
        self.assertEqual(verification_request.result_package_path, self.result_package_path)
        self.assertEqual(verification_request.blender_subtask_definition.output_format, BlenderSubtaskDefinition.OutputFormat.JPEG.name)  # pylint: disable=no-member
        self.assertEqual(verification_request.blender_subtask_definition.scene_file, self.compute_task_def['extra_data']['scene_file'])
        self.assertIsInstance(verification_request.blender_subtask_definition.blender_crop_script_parameters, BlenderCropScriptParameters)

    def test_blender_verification_request_task_should_not_link_upload_requests_to_unrelated_upload_reports(self):
        upload_report = UploadReport(
            path='blender/scene/bad/bad.bad.zip',
        )
        upload_report.full_clean()
        upload_report.save()

        blender_verification_request(
            frames=self.compute_task_def['extra_data']['frames'],
            subtask_id=self.compute_task_def['subtask_id'],
            source_package_path=self.source_package_path,
            result_package_path=self.result_package_path,
            output_format=BlenderSubtaskDefinition.OutputFormat.JPEG.name,  # pylint: disable=no-member
            scene_file = self.compute_task_def['extra_data']['scene_file'],
            verification_deadline=self._get_verification_deadline_as_timestamp(
                get_current_utc_timestamp(),
                self.report_computed_task.size,
            ),
            blender_crop_script_parameters=self.blender_crop_script_parameters,
        )

        self.assertEqual(VerificationRequest.objects.count(), 1)

        verification_request = VerificationRequest.objects.first()
        self.assertEqual(verification_request.upload_reports.count(), 0)
        self.assertFalse(verification_request.upload_reports.filter(path=self.source_package_path).exists())
        self.assertIsInstance(verification_request.blender_subtask_definition.blender_crop_script_parameters, BlenderCropScriptParameters)

    def test_blender_verification_request_task_should_schedule_upload_finished_task_if_all_related_upload_requests_have_reports(self):
        upload_report = UploadReport(
            path=self.source_package_path,
        )
        upload_report.full_clean()
        upload_report.save()

        upload_report = UploadReport(
            path=self.result_package_path,
        )
        upload_report.full_clean()
        upload_report.save()

        with mock.patch('conductor.tasks.tasks.transaction.on_commit') as transaction_on_commit:
            blender_verification_request(
                frames=self.compute_task_def['extra_data']['frames'],
                subtask_id=self.compute_task_def['subtask_id'],
                source_package_path=self.source_package_path,
                result_package_path=self.result_package_path,
                output_format=BlenderSubtaskDefinition.OutputFormat.JPEG.name,  # pylint: disable=no-member
                scene_file = self.compute_task_def['extra_data']['scene_file'],
                verification_deadline=self._get_verification_deadline_as_timestamp(
                    get_current_utc_timestamp(),
                    self.report_computed_task.size,
                ),
                blender_crop_script_parameters=self.blender_crop_script_parameters,
            )

        transaction_on_commit.assert_called_once()
