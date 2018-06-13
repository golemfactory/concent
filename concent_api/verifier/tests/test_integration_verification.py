from subprocess import SubprocessError
import mock

from django.conf import settings
from django.test import override_settings

from conductor.models import BlenderSubtaskDefinition
from core.constants import VerificationResult
from core.tests.utils import ConcentIntegrationTestCase
from utils.constants import ErrorCode
from utils.helpers import get_storage_result_file_path
from utils.helpers import get_storage_source_file_path
from utils.testing_helpers import generate_ecc_key_pair
from ..tasks import blender_verification_order


(CONCENT_PRIVATE_KEY, CONCENT_PUBLIC_KEY) = generate_ecc_key_pair()


def mock_store_file_from_response_in_chunks_raise_exception(_response, _file_path):
    raise OSError


def mock_unpack_archive_raise_exception(_file_path):
    raise OSError


def mock_run_blender(_scene_file, _output_format, script_file=''):  # pylint: disable=unused-argument
    class CompletedProcess:
        returncode = 0
        stdout = ''
        stderr = ''

    return CompletedProcess()


def mock_run_blender_with_error(_scene_file, _output_format, script_file=''):  # pylint: disable=unused-argument
    class CompletedProcessWithError:
        returncode = 1
        stdout = ''
        stderr = 'error'

    return CompletedProcessWithError()


def mock_run_blender_raise_exception(_scene_file, _output_format, script_file=''):  # pylint: disable=unused-argument
    raise SubprocessError


@override_settings(
    CONCENT_PRIVATE_KEY=CONCENT_PRIVATE_KEY,
    CONCENT_PUBLIC_KEY=CONCENT_PUBLIC_KEY,
    MINIMUM_UPLOAD_RATE=1
)
class VerifierVerificationIntegrationTest(ConcentIntegrationTestCase):

    multi_db = True

    def setUp(self):
        super().setUp()
        self.compute_task_def = self._get_deserialized_compute_task_def(
            task_id='ef0dc1',
            subtask_id='zzz523',
        )

        self.source_package_path = get_storage_source_file_path(
            task_id=self.compute_task_def['task_id'],
            subtask_id=self.compute_task_def['subtask_id'],
        )
        self.result_package_path = get_storage_result_file_path(
            task_id=self.compute_task_def['task_id'],
            subtask_id=self.compute_task_def['subtask_id'],
        )
        self.report_computed_task=self._get_deserialized_report_computed_task(
            package_hash='sha1:95a0f391c7ad86686ab1366bcd519ba5ab3cce89',
            size=2,
            task_to_compute=self._get_deserialized_task_to_compute(
                package_hash='sha1:230fb0cad8c7ed29810a2183f0ec1d39c9df3f4a',
                size=1,
                compute_task_def=self.compute_task_def
            )
        )

    def test_that_blender_verification_order_should_download_two_files_and_call_verification_result_with_result_match(self):
        with mock.patch('verifier.tasks.clean_directory', autospec=True) as mock_clean_directory,\
            mock.patch('verifier.tasks.send_request_to_storage_cluster', autospec=True) as mock_send_request_to_storage_cluster,\
            mock.patch('verifier.tasks.store_file_from_response_in_chunks', autospec=True) as mock_store_file_from_response_in_chunks,\
            mock.patch('verifier.tasks.unpack_archive', autospec=True) as mock_unpack_archive,\
            mock.patch('core.tasks.verification_result.delay', autospec=True) as mock_verification_result,\
            mock.patch('verifier.tasks.run_blender', mock_run_blender),\
            mock.patch('verifier.tasks.get_files_list_from_archive') as mock_get_files_list_from_archive,\
            mock.patch('verifier.tasks.delete_file') as mock_delete_file:  # noqa: E125
            blender_verification_order(
                subtask_id=self.compute_task_def['subtask_id'],
                source_package_path=self.source_package_path,
                source_size=self.report_computed_task.task_to_compute.size,
                source_package_hash=self.report_computed_task.task_to_compute.package_hash,
                result_package_path=self.result_package_path,
                result_size=self.report_computed_task.size,  # pylint: disable=no-member
                result_package_hash=self.report_computed_task.package_hash,  # pylint: disable=no-member  # pylint: disable=no-member
                output_format=BlenderSubtaskDefinition.OutputFormat(
                    self.compute_task_def['extra_data']['output_format']
                ).name,
                scene_file=self.compute_task_def['extra_data']['scene_file'],
            )

        mock_clean_directory.assert_called_once_with(settings.VERIFIER_STORAGE_PATH)
        self.assertEqual(mock_send_request_to_storage_cluster.call_count, 2)
        self.assertEqual(mock_store_file_from_response_in_chunks.call_count, 2)
        self.assertEqual(mock_unpack_archive.call_count, 2)
        mock_get_files_list_from_archive.assert_called_once()
        mock_delete_file.assert_not_called()
        mock_verification_result.assert_called_once_with(
            self.compute_task_def['subtask_id'],
            VerificationResult.MATCH.name,
        )

    def test_that_blender_verification_order_should_call_verification_result_with_result_error_if_download_fails(self):
        with mock.patch('verifier.tasks.clean_directory', autospec=True) as mock_clean_directory,\
            mock.patch('verifier.tasks.send_request_to_storage_cluster') as mock_send_request_to_storage_cluster,\
            mock.patch('verifier.tasks.store_file_from_response_in_chunks', mock_store_file_from_response_in_chunks_raise_exception),\
            mock.patch('core.tasks.verification_result.delay', autospec=True) as mock_verification_result:  # noqa: E125
            blender_verification_order(
                subtask_id=self.compute_task_def['subtask_id'],
                source_package_path=self.source_package_path,
                source_size=self.report_computed_task.task_to_compute.size,
                source_package_hash=self.report_computed_task.task_to_compute.package_hash,
                result_package_path=self.result_package_path,
                result_size=self.report_computed_task.size,  # pylint: disable=no-member
                result_package_hash=self.report_computed_task.package_hash,  # pylint: disable=no-member
                output_format=BlenderSubtaskDefinition.OutputFormat(
                    self.compute_task_def['extra_data']['output_format']
                ).name,
                scene_file=self.compute_task_def['extra_data']['scene_file'],
            )

        mock_clean_directory.assert_called_once_with(settings.VERIFIER_STORAGE_PATH)
        mock_send_request_to_storage_cluster.assert_called_once()
        mock_verification_result.assert_called_once_with(
            self.compute_task_def['subtask_id'],
            VerificationResult.ERROR.name,
            '',
            ErrorCode.VERIFIIER_FILE_DOWNLOAD_FAILED.name,
        )

    def test_blender_verification_order_should_call_verification_result_with_result_error_if_unpacking_archive_fails(self):
        with mock.patch('verifier.tasks.clean_directory', autospec=True) as mock_clean_directory,\
            mock.patch('verifier.tasks.send_request_to_storage_cluster', autospec=True) as mock_send_request_to_storage_cluster,\
            mock.patch('verifier.tasks.store_file_from_response_in_chunks', autospec=True) as mock_store_file_from_response_in_chunks, \
            mock.patch('verifier.tasks.unpack_archive', side_effect=OSError, autospec=True), \
            mock.patch('core.tasks.verification_result.delay', autospec=True) as mock_verification_result:  # noqa: E125
            blender_verification_order(
                subtask_id=self.compute_task_def['subtask_id'],
                source_package_path=self.source_package_path,
                source_size=self.report_computed_task.task_to_compute.size,
                source_package_hash=self.report_computed_task.task_to_compute.package_hash,
                result_package_path=self.result_package_path,
                result_size=self.report_computed_task.size,  # pylint: disable=no-member
                result_package_hash=self.report_computed_task.package_hash,  # pylint: disable=no-member
                output_format=BlenderSubtaskDefinition.OutputFormat(
                    self.compute_task_def['extra_data']['output_format']
                ).name,
                scene_file=self.compute_task_def['extra_data']['scene_file'],
            )

        mock_clean_directory.assert_called_once_with(settings.VERIFIER_STORAGE_PATH)
        self.assertEqual(mock_send_request_to_storage_cluster.call_count, 2)
        self.assertEqual(mock_store_file_from_response_in_chunks.call_count, 2)
        mock_verification_result.assert_called_once_with(
            self.compute_task_def['subtask_id'],
            VerificationResult.ERROR.name,
            '',
            ErrorCode.VERIFIIER_UNPACKING_ARCHIVE_FAILED.name,
        )

    def test_blender_verification_order_should_call_verification_result_with_result_error_if_running_subprocess_raise_exception(self):
        with mock.patch('verifier.tasks.clean_directory') as mock_clean_directory, \
            mock.patch('verifier.tasks.send_request_to_storage_cluster') as mock_send_request_to_storage_cluster, \
            mock.patch('verifier.tasks.store_file_from_response_in_chunks') as mock_store_file_from_response_in_chunks, \
            mock.patch('verifier.tasks.unpack_archive') as mock_unpack_archive, \
            mock.patch('verifier.tasks.run_blender', mock_run_blender_raise_exception), \
            mock.patch('core.tasks.verification_result.delay') as mock_verification_result:  # noqa: E125
            blender_verification_order(
                subtask_id=self.compute_task_def['subtask_id'],
                source_package_path=self.source_package_path,
                source_size=self.report_computed_task.task_to_compute.size,
                source_package_hash=self.report_computed_task.task_to_compute.package_hash,
                result_package_path=self.result_package_path,
                result_size=self.report_computed_task.size,  # pylint: disable=no-member
                result_package_hash=self.report_computed_task.package_hash,  # pylint: disable=no-member
                output_format=BlenderSubtaskDefinition.OutputFormat(
                    self.compute_task_def['extra_data']['output_format']
                ).name,
                scene_file=self.compute_task_def['extra_data']['scene_file'],
            )

        mock_clean_directory.assert_called_once()
        mock_send_request_to_storage_cluster.assert_called()
        self.assertEqual(mock_send_request_to_storage_cluster.call_count, 2)
        mock_store_file_from_response_in_chunks.assert_called()
        self.assertEqual(mock_store_file_from_response_in_chunks.call_count, 2)
        mock_unpack_archive.assert_called()
        self.assertEqual(mock_unpack_archive.call_count, 2)
        mock_verification_result.assert_called_once_with(
            self.compute_task_def['subtask_id'],
            VerificationResult.ERROR,
            '',
            'verifier.blender_verification_order.running_blender',
        )

    def test_blender_verification_order_should_call_verification_result_with_result_error_if_running_subprocess_return_non_zero_code(self):
        with mock.patch('verifier.tasks.clean_directory') as mock_clean_directory, \
            mock.patch('verifier.tasks.send_request_to_storage_cluster') as mock_send_request_to_storage_cluster, \
            mock.patch('verifier.tasks.store_file_from_response_in_chunks') as mock_store_file_from_response_in_chunks, \
            mock.patch('verifier.tasks.unpack_archive') as mock_unpack_archive, \
            mock.patch('verifier.tasks.run_blender', mock_run_blender_with_error), \
            mock.patch('core.tasks.verification_result.delay') as mock_verification_result:  # noqa: E125
            blender_verification_order(
                subtask_id=self.compute_task_def['subtask_id'],
                source_package_path=self.source_package_path,
                source_size=self.report_computed_task.task_to_compute.size,
                source_package_hash=self.report_computed_task.task_to_compute.package_hash,
                result_package_path=self.result_package_path,
                result_size=self.report_computed_task.size,  # pylint: disable=no-member
                result_package_hash=self.report_computed_task.package_hash,  # pylint: disable=no-member
                output_format=BlenderSubtaskDefinition.OutputFormat(
                    self.compute_task_def['extra_data']['output_format']
                ).name,
                scene_file=self.compute_task_def['extra_data']['scene_file'],
            )

        mock_clean_directory.assert_called_once()
        mock_send_request_to_storage_cluster.assert_called()
        self.assertEqual(mock_send_request_to_storage_cluster.call_count, 2)
        mock_store_file_from_response_in_chunks.assert_called()
        self.assertEqual(mock_store_file_from_response_in_chunks.call_count, 2)
        mock_unpack_archive.assert_called()
        self.assertEqual(mock_unpack_archive.call_count, 2)
        mock_verification_result.assert_called_once_with(
            self.compute_task_def['subtask_id'],
            VerificationResult.ERROR,
            'error',
            'verifier.blender_verification_order.running_blender',
        )
