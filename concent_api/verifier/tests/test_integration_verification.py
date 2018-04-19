import mock

from django.test    import override_settings

from conductor.models import BlenderSubtaskDefinition
from core.tests.utils import ConcentIntegrationTestCase
from utils.constants import ErrorCode
from utils.helpers import get_storage_result_file_path
from utils.helpers import get_storage_source_file_path
from utils.testing_helpers  import generate_ecc_key_pair
from ..constants import VerificationResult
from ..tasks        import blender_verification_order


def mock_store_file_from_response_in_chunks_raise_exception(_response, _file_path):
    raise OSError


(CONCENT_PRIVATE_KEY, CONCENT_PUBLIC_KEY)                         = generate_ecc_key_pair()


@override_settings(
    CONCENT_PRIVATE_KEY         = CONCENT_PRIVATE_KEY,
    CONCENT_PUBLIC_KEY          = CONCENT_PUBLIC_KEY,
)
class ConductorVerificationIntegrationTest(ConcentIntegrationTestCase):

    multi_db = True

    def setUp(self):
        super().setUp()
        self.compute_task_def = self._get_deserialized_compute_task_def(
            task_id='ef0dc1',
            subtask_id='zzz523',
        )

        self.source_package_path = get_storage_source_file_path(
            self.compute_task_def['task_id'],
            self.compute_task_def['subtask_id'],
        )
        self.result_package_path = get_storage_result_file_path(
            self.compute_task_def['task_id'],
            self.compute_task_def['subtask_id'],
        )

    def test_that_blender_verification_order_should_download_two_files_and_call_verification_result_with_result_match(self):
        with mock.patch('verifier.tasks.clean_directory') as mock_clean_directory,\
            mock.patch('verifier.tasks.send_request_to_cluster_storage') as mock_send_request_to_cluster_storage,\
            mock.patch('verifier.tasks.store_file_from_response_in_chunks') as mock_store_file_from_response_in_chunks,\
            mock.patch('verifier.tasks.verification_result.delay') as mock_verification_result:  # noqa: E125
            blender_verification_order(
                subtask_id=self.compute_task_def['subtask_id'],
                source_package_path=self.source_package_path,
                result_package_path=self.result_package_path,
                output_format=BlenderSubtaskDefinition.OutputFormat(
                    self.compute_task_def['extra_data']['output_format']
                ),
                scene_file=self.compute_task_def['extra_data']['scene_file'],
                report_computed_task=self._get_deserialized_report_computed_task(
                    task_to_compute=self._get_deserialized_task_to_compute(
                        compute_task_def=self.compute_task_def
                    ),
                ),
            )

        mock_clean_directory.assert_called_once()
        mock_send_request_to_cluster_storage.assert_called()
        self.assertEqual(mock_send_request_to_cluster_storage.call_count, 2)
        mock_store_file_from_response_in_chunks.assert_called()
        self.assertEqual(mock_store_file_from_response_in_chunks.call_count, 2)
        mock_verification_result.assert_called_once_with(
            self.compute_task_def['subtask_id'],
            VerificationResult.MATCH,
        )

    def test_that_blender_verification_order_should_call_verification_result_with_result_error_if_download_fails(self):
        with mock.patch('verifier.tasks.clean_directory') as mock_clean_directory,\
            mock.patch('verifier.tasks.send_request_to_cluster_storage') as mock_send_request_to_cluster_storage,\
            mock.patch('verifier.tasks.store_file_from_response_in_chunks', mock_store_file_from_response_in_chunks_raise_exception),\
            mock.patch('verifier.tasks.verification_result.delay') as mock_verification_result:  # noqa: E125
            blender_verification_order(
                subtask_id=self.compute_task_def['subtask_id'],
                source_package_path=self.source_package_path,
                result_package_path=self.result_package_path,
                output_format=BlenderSubtaskDefinition.OutputFormat(
                    self.compute_task_def['extra_data']['output_format']
                ),
                scene_file=self.compute_task_def['extra_data']['scene_file'],
                report_computed_task=self._get_deserialized_report_computed_task(
                    task_to_compute=self._get_deserialized_task_to_compute(
                        compute_task_def=self.compute_task_def
                    ),
                ),
            )

        mock_clean_directory.assert_called_once()
        mock_send_request_to_cluster_storage.assert_called_once()
        mock_verification_result.assert_called_once_with(
            self.compute_task_def['subtask_id'],
            VerificationResult.ERROR,
            '',
            ErrorCode.VERIFIIER_FILE_DOWNLOAD_FAILED,
        )
