import mock

from django.test    import override_settings
from django.test    import TestCase
from django.urls    import reverse

from golem_messages import message

from ..models       import BlenderSubtaskDefinition
from ..models       import UploadReport
from ..models       import VerificationRequest
from ..tasks        import blender_verification_request


class ConductorVerificationIntegrationTest(TestCase):

    multi_db = True

    def setUp(self):
        self.source_package_path = 'blender/source/ef0dc1/ef0dc1.zzz523.zip'
        self.result_package_path = 'blender/result/ef0dc1/ef0dc1.zzz523.zip'
        self.scene_file = 'blender/scene/ef0dc1/ef0dc1.zzz523.zip'

        self.compute_task_def = message.ComputeTaskDef()
        self.compute_task_def['task_id'] = 'ef0dc1'
        self.compute_task_def['subtask_id'] = 'zzz523'

    def _prepare_verification_request_with_blender_subtask_definition(self):
        verification_request = VerificationRequest(
            subtask_id=self.compute_task_def['subtask_id'],
            source_package_path=self.source_package_path,
            result_package_path=self.result_package_path,
        )
        verification_request.full_clean()
        verification_request.save()

        blender_subtask_definition = BlenderSubtaskDefinition(
            verification_request=verification_request,
            output_format=BlenderSubtaskDefinition.OutputFormat.JPG.name,  # pylint: disable=no-member
            scene_file=self.scene_file,
        )
        blender_subtask_definition.full_clean()
        blender_subtask_definition.save()

        return verification_request

    def test_conductor_should_return_404_when_file_path_parameter_not_matching_url_pattern_is_used(self):
        response = self.client.get(
            '/conductor/report-upload/blender/result/ef0dc1/ef0dc1.zzz523.arj',
            content_type = 'application/octet-stream',
        )

        self.assertEqual(response.status_code, 404)

    def test_conductor_should_create_upload_report(self):
        response = self.client.get(
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

        response = self.client.get(
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
            subtask_id='1',
            source_package_path='blender/source/bad/bad.bad.zip',
            result_package_path='blender/result/bad/bad.bad.zip'
        )
        verification_request.full_clean()
        verification_request.save()

        response = self.client.get(
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

        with mock.patch('conductor.views.blender_verification_request.delay') as mock_task:
            response = self.client.get(
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

        mock_task.assert_called_with(
            self.compute_task_def['subtask_id'],
            self.source_package_path,
            self.result_package_path,
            BlenderSubtaskDefinition.OutputFormat.JPG.name,  # pylint: disable=no-member
            self.scene_file,
        )

    def test_blender_verification_request_task_should_create_verification_request_and_blender_subtask_definition(self):
        blender_verification_request(
            subtask_id=self.compute_task_def['subtask_id'],
            source_package_path=self.source_package_path,
            result_package_path=self.result_package_path,
            output_format=BlenderSubtaskDefinition.OutputFormat.JPG.name,  # pylint: disable=no-member
            scene_file=self.scene_file,
        )

        self.assertEqual(VerificationRequest.objects.count(), 1)

        verification_request = VerificationRequest.objects.first()
        self.assertEqual(verification_request.subtask_id,  self.compute_task_def['subtask_id'])
        self.assertEqual(verification_request.source_package_path, self.source_package_path)
        self.assertEqual(verification_request.result_package_path, self.result_package_path)
        self.assertEqual(verification_request.blender_subtask_definition.output_format, BlenderSubtaskDefinition.OutputFormat.JPG.name)  # pylint: disable=no-member
        self.assertEqual(verification_request.blender_subtask_definition.scene_file, self.scene_file)

    def test_blender_verification_request_task_should_not_link_upload_requests_to_unrelated_upload_reports(self):
        upload_report = UploadReport(
            path='blender/scene/bad/bad.bad.zip',
        )
        upload_report.full_clean()
        upload_report.save()

        blender_verification_request(
            subtask_id=self.compute_task_def['subtask_id'],
            source_package_path=self.source_package_path,
            result_package_path=self.result_package_path,
            output_format=BlenderSubtaskDefinition.OutputFormat.JPG.name,  # pylint: disable=no-member
            scene_file=self.scene_file,
        )

        self.assertEqual(VerificationRequest.objects.count(), 1)

        verification_request = VerificationRequest.objects.first()
        self.assertEqual(verification_request.upload_reports.count(), 0)
        self.assertFalse(verification_request.upload_reports.filter(path=self.source_package_path).exists())

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_blender_verification_request_task_should_schedule_verification_order_task_if_all_related_upload_requests_have_reports(self):
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

        with mock.patch('conductor.tasks.blender_verification_request.delay') as mock_task:
            blender_verification_request(
                subtask_id=self.compute_task_def['subtask_id'],
                source_package_path=self.source_package_path,
                result_package_path=self.result_package_path,
                output_format=BlenderSubtaskDefinition.OutputFormat.JPG.name,  # pylint: disable=no-member
                scene_file=self.scene_file,
            )

        mock_task.assert_called_with(
            self.compute_task_def['subtask_id'],
            self.source_package_path,
            self.result_package_path,
            BlenderSubtaskDefinition.OutputFormat.JPG.name,  # pylint: disable=no-member
            self.scene_file,
        )
