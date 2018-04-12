import mock

from django.test    import override_settings
from django.test    import TestCase
from django.urls    import reverse

from golem_messages import message

from utils.helpers import get_result_file_path
from ..models       import UploadReport
from ..models       import UploadRequest
from ..models       import VerificationRequest
from ..tasks        import verification_request_task


class ConductorVerificationIntegrationTest(TestCase):

    multi_db = True

    def setUp(self):
        self.file_path = get_result_file_path('ef0dc1', 'zzz523')

        self.compute_task_def = message.ComputeTaskDef()
        self.compute_task_def['task_id'] = 'ef0dc1'
        self.compute_task_def['subtask_id'] = 'zzz523'

    @staticmethod
    def _prepare_verification_request():
        verification_request = VerificationRequest(
            task_id='1',
            subtask_id='1',
        )
        verification_request.full_clean()
        verification_request.save()
        return verification_request

    @staticmethod
    def _prepare_upload_request(path, verification_request=None):
        upload_request = UploadRequest(
            path=path,
        )
        if verification_request is not None:
            upload_request.verification_request = verification_request
        upload_request.full_clean()
        upload_request.save()
        return upload_request

    def test_conductor_should_return_404_when_file_path_parameter_not_matching_url_pattern_is_used(self):
        response = self.client.get(
            '/conductor/report-upload/blender/result/ef0dc1/ef0dc1.zzz523.arj',
            content_type = 'application/octet-stream',
        )

        self.assertEqual(response.status_code, 404)

    def test_conductor_should_create_upload_report(self):
        response = self.client.get(
            reverse(
                'conductor:report_upload',
                kwargs = {
                    'file_path': self.file_path
                }
            ),
            content_type = 'application/octet-stream',
        )

        self.assertEqual(response.status_code,         200)
        self.assertEqual(UploadReport.objects.count(), 1)

        upload_report = UploadReport.objects.first()
        self.assertEqual(upload_report.path,           self.file_path)
        self.assertEqual(upload_report.upload_request, None)

    def test_conductor_should_create_upload_report_and_link_to_related_upload_request(self):
        verification_request = self._prepare_verification_request()
        upload_request_first = self._prepare_upload_request(self.file_path, verification_request)

        # Create second UploadRequest so view doesn't call verification_order_task.
        self._prepare_upload_request('blender/result/ef0dc1/ef0dc1.aaa523.zip', verification_request)

        response = self.client.get(
            reverse(
                'conductor:report_upload',
                kwargs = {
                    'file_path': self.file_path
                }
            ),
            content_type = 'application/octet-stream',
        )

        self.assertEqual(response.status_code,         200)
        self.assertEqual(UploadReport.objects.count(), 1)

        upload_report = UploadReport.objects.first()
        self.assertEqual(upload_report.path,           self.file_path)
        self.assertEqual(upload_report.upload_request, upload_request_first)

    def test_conductor_should_create_upload_report_and_do_not_link_to_unrelated_upload_request(self):
        verification_request = self._prepare_verification_request()
        self._prepare_upload_request('blender/result/ef0dc1/ef0dc1.zzz523.arj', verification_request)

        response = self.client.get(
            reverse(
                'conductor:report_upload',
                kwargs = {
                    'file_path': self.file_path
                }
            ),
            content_type = 'application/octet-stream',
        )

        self.assertEqual(response.status_code,         200)
        self.assertEqual(UploadReport.objects.count(), 1)

        upload_report = UploadReport.objects.first()
        self.assertEqual(upload_report.path,           self.file_path)
        self.assertEqual(upload_report.upload_request, None)

    def test_conductor_should_schedule_verification_order_task_if_all_related_upload_requests_have_reports(self):
        verification_request = self._prepare_verification_request()
        upload_request = self._prepare_upload_request(self.file_path, verification_request)

        with mock.patch('conductor.views.verification_order_task.delay') as mock_task:
            response = self.client.get(
                reverse(
                    'conductor:report_upload',
                    kwargs = {
                        'file_path': self.file_path
                    }
                ),
                content_type = 'application/octet-stream',
            )

        self.assertEqual(response.status_code,         200)
        self.assertEqual(UploadReport.objects.count(), 1)

        upload_report = UploadReport.objects.first()
        self.assertEqual(upload_report.path,           self.file_path)
        self.assertEqual(upload_report.upload_request, upload_request)

        mock_task.assert_called()

    def test_verification_request_task_should_create_verification_request_and_upload_requests(self):
        files = [
            self.file_path,
            get_result_file_path('ef0dc1', 'aaa523'),
        ]

        verification_request_task(
            compute_task_def = self.compute_task_def,
            files            = files,
        )

        self.assertEqual(VerificationRequest.objects.count(), 1)

        verification_request = VerificationRequest.objects.first()
        self.assertEqual(verification_request.subtask_id,               self.compute_task_def['subtask_id'])
        self.assertEqual(verification_request.upload_requests.count(),  2)

        self.assertEqual(UploadRequest.objects.count(),   2)

        for file in files:
            self.assertTrue(UploadRequest.objects.filter(path = file).exists())

    def test_verification_request_task_should_not_link_upload_requests_to_unrelated_upload_reports(self):
        files = [
            self.file_path
        ]

        upload_report = UploadReport(
            path=get_result_file_path('ef0dc1', 'aaa523'),
        )
        upload_report.full_clean()
        upload_report.save()

        verification_request_task(
            compute_task_def = self.compute_task_def,
            files            = files,
        )

        self.assertEqual(VerificationRequest.objects.count(), 1)

        verification_request = VerificationRequest.objects.first()
        self.assertEqual(verification_request.subtask_id,               self.compute_task_def['subtask_id'])
        self.assertEqual(verification_request.upload_requests.count(),  1)

        self.assertEqual(UploadRequest.objects.count(), 1)

        for file in files:
            self.assertTrue(UploadRequest.objects.filter(path = file).exists())

            upload_request = UploadRequest.objects.filter(path = file).first()
            self.assertEqual(upload_request.upload_reports.count(), 0)

    @override_settings(CELERY_TASK_ALWAYS_EAGER = True)
    def test_verification_request_task_should_schedule_verification_order_task_if_all_related_upload_requests_have_reports(self):
        files = [
            self.file_path
        ]

        upload_report = UploadReport(
            path = files[0],
        )
        upload_report.full_clean()
        upload_report.save()

        verification_request_task(
            compute_task_def = self.compute_task_def,
            files            = files,
        )

        self.assertEqual(VerificationRequest.objects.count(), 1)

        verification_request = VerificationRequest.objects.first()
        self.assertEqual(verification_request.subtask_id,               self.compute_task_def['subtask_id'])
        self.assertEqual(verification_request.upload_requests.count(),  1)

        self.assertEqual(UploadRequest.objects.count(), 1)

        for file in files:
            self.assertTrue(UploadRequest.objects.filter(path = file).exists())

            upload_request = UploadRequest.objects.filter(path = file).first()
            self.assertEqual(upload_request.upload_reports.count(), 1)
