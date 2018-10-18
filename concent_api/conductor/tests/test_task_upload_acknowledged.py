import mock

from freezegun import freeze_time
from django.conf import settings

from common.helpers import get_current_utc_timestamp
from common.helpers import get_storage_result_file_path
from common.helpers import get_storage_source_file_path
from common.helpers import parse_datetime_to_timestamp
from conductor.exceptions import VerificationRequestAlreadyAcknowledgedError
from conductor.models import BlenderSubtaskDefinition
from conductor.models import VerificationRequest
from conductor.tasks import upload_acknowledged
from core.message_handlers import store_subtask
from core.models import Subtask
from core.tests.utils import ConcentIntegrationTestCase


class ConductorUploadAcknowledgedTaskTestCase(ConcentIntegrationTestCase):

    multi_db = True

    def setUp(self):
        super().setUp()
        self.task_to_compute = self._get_deserialized_task_to_compute()
        self.compute_task_def = self.task_to_compute.compute_task_def
        self.source_package_path = get_storage_source_file_path(
            self.task_to_compute.subtask_id,
            self.task_to_compute.task_id,
        )
        self.result_package_path = get_storage_result_file_path(
            self.task_to_compute.subtask_id,
            self.task_to_compute.task_id,
        )
        self.report_computed_task = self._get_deserialized_report_computed_task(task_to_compute=self.task_to_compute)

        self.verification_request = VerificationRequest(
            subtask_id=self.report_computed_task.subtask_id,
            source_package_path=self.source_package_path,
            result_package_path=self.result_package_path,
            verification_deadline=self._get_verification_deadline_as_datetime(
                get_current_utc_timestamp(),
                self.report_computed_task.task_to_compute,
            )
        )
        self.verification_request.full_clean()
        self.verification_request.save()

        blender_subtask_definition = BlenderSubtaskDefinition(
            verification_request=self.verification_request,
            output_format=BlenderSubtaskDefinition.OutputFormat.JPG.name,  # pylint: disable=no-member
            scene_file=self.compute_task_def['extra_data']['scene_file'],
            blender_crop_script=self.compute_task_def['extra_data']['script_src'],
        )
        blender_subtask_definition.full_clean()
        blender_subtask_definition.save()

    def test_that_upload_acknowledged_task_should_change_upload_finished_on_existing_related_verification_request_to_true_and_call_blender_verification_order_task(self):
        with freeze_time():
            store_subtask(
                task_id=self.report_computed_task.task_to_compute.compute_task_def['task_id'],
                subtask_id=self.report_computed_task.task_to_compute.compute_task_def['subtask_id'],
                provider_public_key=self.PROVIDER_PUBLIC_KEY,
                requestor_public_key=self.REQUESTOR_PUBLIC_KEY,
                state=Subtask.SubtaskState.ADDITIONAL_VERIFICATION,
                next_deadline=get_current_utc_timestamp() + settings.CONCENT_MESSAGING_TIME,
                task_to_compute=self.report_computed_task.task_to_compute,
                report_computed_task=self.report_computed_task,
            )

            with mock.patch('conductor.tasks.blender_verification_order.delay') as mock_blender_verification_order, \
                mock.patch('conductor.tasks.filter_frames_by_blender_subtask_definition', return_value=[1]) as mock_frames_filtering:  # noqa: E125
                upload_acknowledged(
                    subtask_id=self.report_computed_task.subtask_id,
                    source_file_size=self.report_computed_task.task_to_compute.size,
                    source_package_hash=self.report_computed_task.task_to_compute.package_hash,
                    result_file_size=self.report_computed_task.size,
                    result_package_hash=self.report_computed_task.package_hash,
                )

            self.verification_request.refresh_from_db()

            self.assertTrue(self.verification_request.upload_acknowledged)
            mock_blender_verification_order.assert_called_once_with(
                frames=[1],
                subtask_id=self.verification_request.subtask_id,
                source_package_path=self.verification_request.source_package_path,
                source_size=self.report_computed_task.task_to_compute.size,
                source_package_hash=self.report_computed_task.task_to_compute.package_hash,
                result_package_path=self.verification_request.result_package_path,
                result_size=self.report_computed_task.size,
                result_package_hash=self.report_computed_task.package_hash,
                output_format=self.verification_request.blender_subtask_definition.output_format,
                scene_file=self.verification_request.blender_subtask_definition.scene_file,
                verification_deadline=parse_datetime_to_timestamp(self.verification_request.verification_deadline),
                blender_crop_script=self.verification_request.blender_subtask_definition.blender_crop_script,
            )
            mock_frames_filtering.assert_called_once()

    @mock.patch("conductor.tasks.log_string_message")
    def test_that_upload_acknowledged_task_should_log_error_when_verification_request_with_given_subtask_id_does_not_exist(self, mock_logging_error):
        subtask_id = self._get_uuid('o')

        upload_acknowledged(
            subtask_id=subtask_id,
            source_file_size=self.report_computed_task.task_to_compute.size,
            source_package_hash=self.report_computed_task.task_to_compute.package_hash,
            result_file_size=self.report_computed_task.size,
            result_package_hash=self.report_computed_task.package_hash,
        )

        self.verification_request.refresh_from_db()

        self.assertFalse(self.verification_request.upload_acknowledged)
        mock_logging_error.assert_called()
        self.assertIn(
            f'Task `upload_acknowledged` tried to get VerificationRequest object with ID {subtask_id} but it does not exist.',
            str(mock_logging_error.call_args_list)
        )

    def test_that_upload_acknowledged_task_should_raise_exception_when_verification_request_is_already_acknowledged(self):
        self.verification_request.upload_acknowledged = True
        self.verification_request.full_clean()
        self.verification_request.save()

        with self.assertRaises(VerificationRequestAlreadyAcknowledgedError):
            upload_acknowledged(
                subtask_id=self.report_computed_task.subtask_id,
                source_file_size=self.report_computed_task.task_to_compute.size,
                source_package_hash=self.report_computed_task.task_to_compute.package_hash,
                result_file_size=self.report_computed_task.size,
                result_package_hash=self.report_computed_task.package_hash,
            )
