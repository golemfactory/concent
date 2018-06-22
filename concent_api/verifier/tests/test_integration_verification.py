from subprocess import SubprocessError
from zipfile import BadZipFile
import io
import mock

from django.conf import settings
from django.test import override_settings

from conductor.models import BlenderSubtaskDefinition
from core.constants import VerificationResult
from core.tests.utils import ConcentIntegrationTestCase
from common.constants import ErrorCode
from common.helpers import get_storage_result_file_path
from common.helpers import get_storage_source_file_path
from common.testing_helpers import generate_ecc_key_pair
from ..tasks import blender_verification_order


(CONCENT_PRIVATE_KEY, CONCENT_PUBLIC_KEY) = generate_ecc_key_pair()


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

    def test_that_blender_verification_order_should_perform_full_verification_with_match_result(self):
        with mock.patch('verifier.tasks.clean_directory', autospec=True) as mock_clean_directory,\
            mock.patch('verifier.tasks.send_request_to_storage_cluster', autospec=True) as mock_send_request_to_storage_cluster,\
            mock.patch('verifier.tasks.store_file_from_response_in_chunks', autospec=True) as mock_store_file_from_response_in_chunks,\
            mock.patch('verifier.tasks.unpack_archive', autospec=True) as mock_unpack_archive,\
            mock.patch('core.tasks.verification_result.delay', autospec=True) as mock_verification_result,\
            mock.patch('verifier.tasks.run_blender', mock_run_blender),\
            mock.patch('verifier.tasks.upload_file_to_storage_cluster', autospec=True) as mock_upload_file, \
            mock.patch('builtins.open', autospec=True, side_effect=[io.StringIO('test'), io.StringIO('test')]), \
            mock.patch('verifier.tasks.get_files_list_from_archive', return_value=['file_name']) as mock_get_files_list_from_archive, \
            mock.patch('verifier.tasks.cv2.imread', autospec=True) as mock_imread, \
            mock.patch('verifier.tasks.compare_ssim', return_value=1.0) as mock_compare_ssim, \
            mock.patch('verifier.tasks.delete_file', autospec=True) as mock_delete_file:  # noqa: E125
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

        self.assertEqual(mock_clean_directory.call_count, 2)
        self.assertEqual(mock_send_request_to_storage_cluster.call_count, 2)
        self.assertEqual(mock_store_file_from_response_in_chunks.call_count, 2)
        self.assertEqual(mock_unpack_archive.call_count, 2)
        self.assertEqual(mock_get_files_list_from_archive.call_count, 4)
        self.assertEqual(mock_delete_file.call_count, 2)
        self.assertEqual(mock_imread.call_count, 2)
        self.assertEqual(mock_upload_file.call_count, 1)
        mock_verification_result.assert_called_once_with(
            self.compute_task_def['subtask_id'],
            VerificationResult.MATCH.name,
        )
        mock_compare_ssim.assert_called_once()

    def test_that_blender_verification_order_should_perform_full_verification_with_mismatch_result(self):
        with mock.patch('verifier.tasks.clean_directory', autospec=True) as mock_clean_directory,\
            mock.patch('verifier.tasks.send_request_to_storage_cluster', autospec=True) as mock_send_request_to_storage_cluster,\
            mock.patch('verifier.tasks.store_file_from_response_in_chunks', autospec=True) as mock_store_file_from_response_in_chunks,\
            mock.patch('verifier.tasks.unpack_archive', autospec=True) as mock_unpack_archive, \
            mock.patch('verifier.tasks.upload_file_to_storage_cluster', autospec=True) as mock_upload_file_to_storage_cluster, \
            mock.patch('verifier.tasks.verification_result.delay', autospec=True) as mock_verification_result,\
            mock.patch('verifier.tasks.run_blender', mock_run_blender), \
            mock.patch('verifier.tasks.upload_file_to_storage_cluster', autospec=True) as mock_upload_file, \
            mock.patch('builtins.open', autospec=True, side_effect=[io.StringIO('test'), io.StringIO('test')]), \
            mock.patch('verifier.tasks.get_files_list_from_archive', autospec=True, return_value=['file_name']) as mock_get_files_list_from_archive, \
            mock.patch('verifier.tasks.cv2.imread', autospec=True) as mock_imread, \
            mock.patch('verifier.tasks.compare_ssim', return_value=(settings.VERIFIER_MIN_SSIM - 0.1)) as mock_compare_ssim, \
            mock.patch('verifier.tasks.delete_file', autospec=True) as mock_delete_file:  # noqa: E125
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

        self.assertEqual(mock_clean_directory.call_count, 2)
        self.assertEqual(mock_send_request_to_storage_cluster.call_count, 2)
        self.assertEqual(mock_store_file_from_response_in_chunks.call_count, 2)
        self.assertEqual(mock_unpack_archive.call_count, 2)
        self.assertEqual(mock_upload_file_to_storage_cluster.call_count, 1)
        self.assertEqual(mock_get_files_list_from_archive.call_count, 4)
        self.assertEqual(mock_delete_file.call_count, 2)
        self.assertEqual(mock_imread.call_count, 2)
        self.assertEqual(mock_upload_file.call_count, 1)
        mock_compare_ssim.assert_called_once()
        mock_verification_result.assert_called_once_with(
            self.compute_task_def['subtask_id'],
            VerificationResult.MISMATCH.name,
        )

    def test_that_blender_verification_order_should_call_verification_result_with_result_error_if_download_fails(self):
        with mock.patch('verifier.tasks.clean_directory', autospec=True) as mock_clean_directory,\
            mock.patch('verifier.tasks.send_request_to_storage_cluster') as mock_send_request_to_storage_cluster,\
            mock.patch('core.tasks.verification_result.delay', autospec=True) as mock_verification_result,\
            mock.patch('verifier.tasks.store_file_from_response_in_chunks', autospec=True, side_effect=OSError('error')):  # noqa: E125
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
            'error',
            ErrorCode.VERIFIER_FILE_DOWNLOAD_FAILED.name,
        )

    def test_blender_verification_order_should_call_verification_result_with_result_error_if_unpacking_archive_fails(self):
        with mock.patch('verifier.tasks.clean_directory', autospec=True) as mock_clean_directory,\
            mock.patch('verifier.tasks.send_request_to_storage_cluster', autospec=True) as mock_send_request_to_storage_cluster,\
            mock.patch('verifier.tasks.store_file_from_response_in_chunks', autospec=True) as mock_store_file_from_response_in_chunks, \
            mock.patch('verifier.tasks.unpack_archive', side_effect=BadZipFile, autospec=True), \
            mock.patch('verifier.tasks.get_files_list_from_archive', return_value=['file_name']) as mock_get_files_list_from_archive, \
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

        self.assertEqual(mock_send_request_to_storage_cluster.call_count, 2)
        self.assertEqual(mock_store_file_from_response_in_chunks.call_count, 2)
        self.assertEqual(mock_get_files_list_from_archive.call_count, 2)
        mock_clean_directory.assert_called_once_with(settings.VERIFIER_STORAGE_PATH)
        mock_verification_result.assert_called_once_with(
            self.compute_task_def['subtask_id'],
            VerificationResult.ERROR.name,
            '',
            ErrorCode.VERIFIER_UNPACKING_ARCHIVE_FAILED.name,
        )

    def test_blender_verification_order_should_call_verification_result_with_result_error_if_running_subprocess_raise_exception(self):
        with mock.patch('verifier.tasks.clean_directory') as mock_clean_directory, \
            mock.patch('verifier.tasks.send_request_to_storage_cluster') as mock_send_request_to_storage_cluster, \
            mock.patch('verifier.tasks.store_file_from_response_in_chunks') as mock_store_file_from_response_in_chunks, \
            mock.patch('verifier.tasks.unpack_archive') as mock_unpack_archive, \
            mock.patch('core.tasks.verification_result.delay', autospec=True) as mock_verification_result, \
            mock.patch('verifier.tasks.get_files_list_from_archive', return_value=['file_name']) as mock_get_files_list_from_archive, \
            mock.patch('verifier.tasks.run_blender', autospec=True, side_effect=SubprocessError('error')):  # noqa: E125
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

        self.assertEqual(mock_send_request_to_storage_cluster.call_count, 2)
        self.assertEqual(mock_store_file_from_response_in_chunks.call_count, 2)
        self.assertEqual(mock_unpack_archive.call_count, 2)
        self.assertEqual(mock_get_files_list_from_archive.call_count, 2)
        mock_clean_directory.assert_called_once()
        mock_send_request_to_storage_cluster.assert_called()
        mock_store_file_from_response_in_chunks.assert_called()
        mock_unpack_archive.assert_called()
        mock_verification_result.assert_called_once_with(
            self.compute_task_def['subtask_id'],
            VerificationResult.ERROR.name,
            'error',
            ErrorCode.VERIFIER_RUNNING_BLENDER_FAILED.name,
        )

    def test_blender_verification_order_should_call_verification_result_with_result_error_if_running_subprocess_return_non_zero_code(self):
        with mock.patch('verifier.tasks.clean_directory') as mock_clean_directory, \
            mock.patch('verifier.tasks.send_request_to_storage_cluster') as mock_send_request_to_storage_cluster, \
            mock.patch('verifier.tasks.store_file_from_response_in_chunks') as mock_store_file_from_response_in_chunks, \
            mock.patch('verifier.tasks.unpack_archive') as mock_unpack_archive, \
            mock.patch('verifier.tasks.run_blender', mock_run_blender_with_error), \
            mock.patch('verifier.tasks.get_files_list_from_archive', return_value=['file_name']) as mock_get_files_list_from_archive, \
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

        self.assertEqual(mock_send_request_to_storage_cluster.call_count, 2)
        self.assertEqual(mock_store_file_from_response_in_chunks.call_count, 2)
        self.assertEqual(mock_unpack_archive.call_count, 2)
        self.assertEqual(mock_get_files_list_from_archive.call_count, 2)
        mock_clean_directory.assert_called_once()
        mock_send_request_to_storage_cluster.assert_called()
        mock_store_file_from_response_in_chunks.assert_called()
        mock_unpack_archive.assert_called()
        mock_verification_result.assert_called_once_with(
            self.compute_task_def['subtask_id'],
            VerificationResult.ERROR.name,
            'error',
            ErrorCode.VERIFIER_RUNNING_BLENDER_FAILED.name,
        )

    def test_blender_verification_order_should_call_verification_result_with_result_error_if_opening_first_file_raise_memory_error(self):
        with mock.patch('verifier.tasks.clean_directory', autospec=True) as mock_clean_directory,\
            mock.patch('verifier.tasks.send_request_to_storage_cluster', autospec=True) as mock_send_request_to_storage_cluster,\
            mock.patch('verifier.tasks.store_file_from_response_in_chunks', autospec=True) as mock_store_file_from_response_in_chunks,\
            mock.patch('verifier.tasks.unpack_archive', autospec=True) as mock_unpack_archive,\
            mock.patch('verifier.tasks.verification_result.delay', autospec=True) as mock_verification_result,\
            mock.patch('verifier.tasks.run_blender', mock_run_blender), \
            mock.patch('builtins.open', autospec=True, side_effect=MemoryError('error')), \
            mock.patch('verifier.tasks.get_files_list_from_archive', return_value=['file_name']) as mock_get_files_list_from_archive, \
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

        self.assertEqual(mock_clean_directory.call_count, 1)
        self.assertEqual(mock_send_request_to_storage_cluster.call_count, 2)
        self.assertEqual(mock_store_file_from_response_in_chunks.call_count, 2)
        self.assertEqual(mock_unpack_archive.call_count, 2)
        self.assertEqual(mock_get_files_list_from_archive.call_count, 3)
        self.assertEqual(mock_delete_file.call_count, 2)
        mock_verification_result.assert_called_once_with(
            self.compute_task_def['subtask_id'],
            VerificationResult.ERROR.name,
            'error',
            ErrorCode.VERIFIER_LOADING_FILES_INTO_MEMORY_FAILED.name,
        )

    def test_blender_verification_order_should_continue_verification_if_opening_blender_output_file_raises_os_error(self):
        with mock.patch('verifier.tasks.clean_directory', autospec=True) as mock_clean_directory,\
            mock.patch('verifier.tasks.send_request_to_storage_cluster', autospec=True) as mock_send_request_to_storage_cluster,\
            mock.patch('verifier.tasks.store_file_from_response_in_chunks', autospec=True) as mock_store_file_from_response_in_chunks,\
            mock.patch('verifier.tasks.unpack_archive', autospec=True) as mock_unpack_archive,\
            mock.patch('verifier.tasks.verification_result.delay', autospec=True) as mock_verification_result,\
            mock.patch('verifier.tasks.run_blender', mock_run_blender), \
            mock.patch('builtins.open', autospec=True, side_effect=OSError('error')), \
            mock.patch('verifier.tasks.get_files_list_from_archive', return_value=['file_name']) as mock_get_files_list_from_archive, \
            mock.patch('verifier.tasks.cv2.imread', autospec=True) as mock_imread, \
            mock.patch('verifier.tasks.compare_ssim', return_value=1.0) as mock_compare_ssim, \
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

        self.assertEqual(mock_clean_directory.call_count, 2)
        self.assertEqual(mock_send_request_to_storage_cluster.call_count, 2)
        self.assertEqual(mock_store_file_from_response_in_chunks.call_count, 2)
        self.assertEqual(mock_unpack_archive.call_count, 2)
        self.assertEqual(mock_get_files_list_from_archive.call_count, 4)
        self.assertEqual(mock_delete_file.call_count, 2)
        self.assertEqual(mock_imread.call_count, 2)
        mock_verification_result.assert_called_once_with(
            self.compute_task_def['subtask_id'],
            VerificationResult.MATCH.name,
        )
        mock_compare_ssim.assert_called_once()

    def test_blender_verification_order_should_call_verification_result_with_result_error_if_cv2_imread_raise_memory_error(self):
        with mock.patch('verifier.tasks.clean_directory', autospec=True) as mock_clean_directory,\
            mock.patch('verifier.tasks.send_request_to_storage_cluster', autospec=True) as mock_send_request_to_storage_cluster,\
            mock.patch('verifier.tasks.store_file_from_response_in_chunks', autospec=True) as mock_store_file_from_response_in_chunks,\
            mock.patch('verifier.tasks.unpack_archive', autospec=True) as mock_unpack_archive, \
            mock.patch('verifier.tasks.upload_file_to_storage_cluster', autospec=True) as mock_upload_file_to_storage_cluster, \
            mock.patch('verifier.tasks.verification_result.delay', autospec=True) as mock_verification_result,\
            mock.patch('verifier.tasks.run_blender', mock_run_blender), \
            mock.patch('verifier.tasks.upload_file_to_storage_cluster', autospec=True) as mock_upload_file, \
            mock.patch('builtins.open', autospec=True, side_effect=[io.StringIO('test'), io.StringIO('test')]), \
            mock.patch('verifier.tasks.get_files_list_from_archive', autospec=True, return_value=['file_name']) as mock_get_files_list_from_archive, \
            mock.patch('verifier.tasks.cv2.imread', autospec=True, side_effect=MemoryError('error')) as mock_imread, \
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

        self.assertEqual(mock_clean_directory.call_count, 1)
        self.assertEqual(mock_send_request_to_storage_cluster.call_count, 2)
        self.assertEqual(mock_store_file_from_response_in_chunks.call_count, 2)
        self.assertEqual(mock_unpack_archive.call_count, 2)
        self.assertEqual(mock_upload_file_to_storage_cluster.call_count, 1)
        self.assertEqual(mock_get_files_list_from_archive.call_count, 4)
        self.assertEqual(mock_delete_file.call_count, 2)
        self.assertEqual(mock_imread.call_count, 1)
        self.assertEqual(mock_upload_file.call_count, 1)
        mock_verification_result.assert_called_once_with(
            self.compute_task_def['subtask_id'],
            VerificationResult.ERROR.name,
            'error',
            ErrorCode.VERIFIER_LOADING_FILES_INTO_MEMORY_FAILED.name,
        )

    def test_blender_verification_order_should_call_verification_result_with_result_error_if_cv2_imread_returns_none(self):
        with mock.patch('verifier.tasks.clean_directory', autospec=True) as mock_clean_directory,\
            mock.patch('verifier.tasks.send_request_to_storage_cluster', autospec=True) as mock_send_request_to_storage_cluster,\
            mock.patch('verifier.tasks.store_file_from_response_in_chunks', autospec=True) as mock_store_file_from_response_in_chunks,\
            mock.patch('verifier.tasks.unpack_archive', autospec=True) as mock_unpack_archive, \
            mock.patch('verifier.tasks.upload_file_to_storage_cluster', autospec=True) as mock_upload_file_to_storage_cluster, \
            mock.patch('verifier.tasks.verification_result.delay', autospec=True) as mock_verification_result,\
            mock.patch('verifier.tasks.run_blender', mock_run_blender), \
            mock.patch('verifier.tasks.upload_file_to_storage_cluster', autospec=True) as mock_upload_file, \
            mock.patch('builtins.open', autospec=True, side_effect=[io.StringIO('test'), io.StringIO('test')]), \
            mock.patch('verifier.tasks.get_files_list_from_archive', autospec=True, return_value=['file_name']) as mock_get_files_list_from_archive, \
            mock.patch('verifier.tasks.cv2.imread', autospec=True, side_effect=[None, None]) as mock_imread, \
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

        self.assertEqual(mock_clean_directory.call_count, 1)
        self.assertEqual(mock_send_request_to_storage_cluster.call_count, 2)
        self.assertEqual(mock_store_file_from_response_in_chunks.call_count, 2)
        self.assertEqual(mock_unpack_archive.call_count, 2)
        self.assertEqual(mock_upload_file_to_storage_cluster.call_count, 1)
        self.assertEqual(mock_get_files_list_from_archive.call_count, 4)
        self.assertEqual(mock_delete_file.call_count, 2)
        self.assertEqual(mock_imread.call_count, 2)
        self.assertEqual(mock_upload_file.call_count, 1)
        mock_verification_result.assert_called_once_with(
            self.compute_task_def['subtask_id'],
            VerificationResult.ERROR.name,
            'Loading files using OpenCV fails.',
            ErrorCode.VERIFIER_LOADING_FILES_WITH_OPENCV_FAILED.name,
        )

    def test_blender_verification_order_should_call_verification_result_with_result_error_if_compare_ssim_raise_value_error(self):
        with mock.patch('verifier.tasks.clean_directory', autospec=True) as mock_clean_directory,\
            mock.patch('verifier.tasks.send_request_to_storage_cluster', autospec=True) as mock_send_request_to_storage_cluster,\
            mock.patch('verifier.tasks.store_file_from_response_in_chunks', autospec=True) as mock_store_file_from_response_in_chunks,\
            mock.patch('verifier.tasks.unpack_archive', autospec=True) as mock_unpack_archive,\
            mock.patch('verifier.tasks.upload_file_to_storage_cluster', autospec=True) as mock_upload_file_to_storage_cluster,\
            mock.patch('verifier.tasks.verification_result.delay', autospec=True) as mock_verification_result,\
            mock.patch('verifier.tasks.run_blender', mock_run_blender), \
            mock.patch('verifier.tasks.upload_file_to_storage_cluster', autospec=True) as mock_upload_file, \
            mock.patch('builtins.open', autospec=True, side_effect=[io.StringIO('test'), io.StringIO('test')]), \
            mock.patch('verifier.tasks.get_files_list_from_archive', return_value=['file_name']) as mock_get_files_list_from_archive, \
            mock.patch('verifier.tasks.cv2.imread', autospec=True) as mock_imread, \
            mock.patch('verifier.tasks.compare_ssim', side_effect=ValueError('error')) as mock_compare_ssim, \
            mock.patch('verifier.tasks.delete_file', autospec=True) as mock_delete_file:  # noqa: E125
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

        self.assertEqual(mock_clean_directory.call_count, 1)
        self.assertEqual(mock_send_request_to_storage_cluster.call_count, 2)
        self.assertEqual(mock_store_file_from_response_in_chunks.call_count, 2)
        self.assertEqual(mock_unpack_archive.call_count, 2)
        self.assertEqual(mock_upload_file_to_storage_cluster.call_count, 1)
        self.assertEqual(mock_get_files_list_from_archive.call_count, 4)
        self.assertEqual(mock_delete_file.call_count, 2)
        self.assertEqual(mock_imread.call_count, 2)
        self.assertEqual(mock_upload_file.call_count, 1)
        mock_compare_ssim.assert_called_once()
        mock_verification_result.assert_called_once_with(
            self.compute_task_def['subtask_id'],
            VerificationResult.ERROR.name,
            'error',
            ErrorCode.VERIFIER_COMPUTING_SSIM_FAILED.name,
        )
