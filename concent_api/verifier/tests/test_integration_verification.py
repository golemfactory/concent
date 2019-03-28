import mock

from django.test import override_settings
from numpy.core.multiarray import ndarray

from common.constants import ErrorCode
from common.helpers import get_current_utc_timestamp
from common.helpers import get_storage_result_file_path
from common.helpers import get_storage_source_file_path
from common.testing_helpers import generate_ecc_key_pair
from conductor.models import BlenderSubtaskDefinition
from core.constants import VerificationResult
from core.tasks import verification_result
from core.tests.utils import ConcentIntegrationTestCase
from core.utils import extract_blender_parameters_from_compute_task_def
from verifier.exceptions import VerificationError
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
        self.task_to_compute = self._get_deserialized_task_to_compute()
        self.compute_task_def = self.task_to_compute.compute_task_def
        self.blender_crop_script_parameters = extract_blender_parameters_from_compute_task_def(self.compute_task_def['extra_data'])
        self.source_package_path = get_storage_source_file_path(
            self.task_to_compute.subtask_id,
            self.task_to_compute.task_id,
        )
        self.result_package_path = get_storage_result_file_path(
            self.task_to_compute.subtask_id,
            self.task_to_compute.task_id,
        )
        self.frames = [1]
        self.report_computed_task = self._get_deserialized_report_computed_task(task_to_compute=self.task_to_compute)

        self.subtask_id = self.compute_task_def['subtask_id']
        self.scene_file = self.compute_task_def['extra_data']['scene_file']
        self.output_format = self.compute_task_def['extra_data']['output_format']

        self.mock_image1 = mock.create_autospec(spec=ndarray, spec_set=True)
        self.mock_image2 = mock.create_autospec(spec=ndarray, spec_set=True)
        self.loaded_images = (self.mock_image1, self.mock_image2)

        self.mock_verification_result = mock.create_autospec(spec=verification_result, spec_set=True)
        self.parsed_all_files = {
            1: [
                '/tmp/result_0001.png',
                '/tmp/out_scene-Helicopter-27-internal.blend_0001.png'
            ]
        }
        self.blender_output_file_name_list = [
            '/tmp/out_scene-Helicopter-27-internal.blend_0001.png',
        ]
        self.parsed_multi_frames_files = {
            1: [
                '/tmp/result_0001.png',
                '/tmp/out_scene-Helicopter-27-internal.blend_0001.png'
            ],
            2: [
                '/tmp/result_0002.png',
                '/tmp/out_scene-Helicopter-27-internal.blend_0002.png'
            ]
        }
        self.multi_frames_blender_output_file_name_list = [
            '/tmp/out_scene-Helicopter-27-internal.blend_0001.png',
            '/tmp/out_scene-Helicopter-27-internal.blend_0002.png'
        ]
        self.multi_frames = [1, 2]

    def mocked_parse_result_files_with_frames(self):
        mocked_dict = {}
        for frame in self.frames:
            mocked_dict[frame] = (str(frame), str(frame))
        return mocked_dict

    def test_that_blender_verification_order_should_perform_full_verification_with_match_result(self):
        with mock.patch('verifier.tasks.download_archives_from_storage', autospec=True) as mock_download_archives_from_storage,\
            mock.patch('verifier.tasks.validate_downloaded_archives', autospec=True) as mock_validate_downloaded_archives, \
            mock.patch('verifier.tasks.unpack_archives', autospec=True) as mock_unpack_archives, \
            mock.patch('verifier.tasks.get_files_list_from_archive', autospec=True, side_effect=[self.frames]) as mock_get_files_list_from_archive, \
            mock.patch('verifier.tasks.parse_result_files_with_frames', autospec=True, return_value=self.mocked_parse_result_files_with_frames()) as mock_parse_result_files_with_frames, \
            mock.patch('verifier.tasks.render_images_by_frames', autospec=True, return_value=(self.blender_output_file_name_list, self.parsed_all_files)) as mock_render_image, \
            mock.patch('verifier.tasks.delete_source_files', autospec=True) as mock_delete_source_files, \
            mock.patch('verifier.tasks.upload_blender_output_file', autospec=True) as mock_try_to_upload_file, \
            mock.patch('verifier.tasks.compare_all_rendered_images_with_user_results_files') as compare_all_rendered_images_with_user_results_files, \
            mock.patch('verifier.tasks.compare_minimum_ssim_with_results', side_effect=self._verification_results_match(self.subtask_id)) as compare_minimum_ssim_with_results:  # noqa: E125

            current_time = get_current_utc_timestamp()
            self._send_blender_verification_order(current_time=current_time)

        self.assertEqual(mock_download_archives_from_storage.call_count, 1)
        self.assertEqual(mock_validate_downloaded_archives.call_count, 1)
        self.assertEqual(mock_unpack_archives.call_count, 1)
        mock_render_image.assert_called_once_with(
            frames=self.frames,
            parsed_files_to_compare=self.mocked_parse_result_files_with_frames(),
            output_format=self.output_format,
            scene_file=self.scene_file,
            subtask_id=self.subtask_id,
            verification_deadline=self._get_verification_deadline_as_timestamp(
                current_time,
                self.report_computed_task.size,
            ),
            blender_crop_script_parameters=self.blender_crop_script_parameters,
        )
        self.assertEqual(mock_delete_source_files.call_count, 1)
        self.assertEqual(mock_get_files_list_from_archive.call_count, 1)
        self.assertEqual(mock_try_to_upload_file.call_count, 1)
        self.assertEqual(compare_all_rendered_images_with_user_results_files.call_count, 1)
        self.assertEqual(compare_minimum_ssim_with_results.call_count, 1)
        self.assertEqual(mock_parse_result_files_with_frames.call_count, 1)
        self.mock_verification_result.assert_called_once_with(
            self.subtask_id,
            VerificationResult.MATCH.name,
        )

    def test_that_blender_verification_order_should_perform_full_verification_with_mismatch_result(self):
        with mock.patch('verifier.tasks.download_archives_from_storage', autospec=True) as mock_download_archives_from_storage, \
            mock.patch('verifier.tasks.validate_downloaded_archives', autospec=True) as mock_validate_downloaded_archives, \
            mock.patch('verifier.tasks.unpack_archives', autospec=True) as mock_unpack_archives, \
            mock.patch('verifier.tasks.get_files_list_from_archive', autospec=True, side_effect=[self.frames]) as mock_get_files_list_from_archive, \
            mock.patch('verifier.tasks.parse_result_files_with_frames', autospec=True, return_value=self.mocked_parse_result_files_with_frames()) as mock_parse_result_files_with_frames, \
            mock.patch('verifier.tasks.render_images_by_frames', autospec=True, return_value=(self.blender_output_file_name_list, self.parsed_all_files)) as mock_render_image, \
            mock.patch('verifier.tasks.delete_source_files', autospec=True) as mock_delete_source_files, \
            mock.patch('verifier.tasks.upload_blender_output_file', autospec=True) as mock_try_to_upload_file, \
            mock.patch('verifier.tasks.compare_all_rendered_images_with_user_results_files', autospec=True) as mock_compare_all_rendered_images_with_user_results_files, \
            mock.patch('verifier.tasks.compare_minimum_ssim_with_results', side_effect=self._verification_results_mismatch(self.subtask_id)) as compare_minimum_ssim_with_results:  # noqa: E125
            current_time = get_current_utc_timestamp()
            self._send_blender_verification_order(current_time=current_time)

        self.assertEqual(mock_download_archives_from_storage.call_count, 1)
        self.assertEqual(mock_validate_downloaded_archives.call_count, 1)
        self.assertEqual(mock_unpack_archives.call_count, 1)
        mock_render_image.assert_called_once_with(
            frames=self.frames,
            parsed_files_to_compare=self.mocked_parse_result_files_with_frames(),
            output_format=self.output_format,
            scene_file=self.scene_file,
            subtask_id=self.subtask_id,
            verification_deadline=self._get_verification_deadline_as_timestamp(
                current_time,
                self.report_computed_task.size,
            ),
            blender_crop_script_parameters=self.blender_crop_script_parameters,
        )
        self.assertEqual(mock_delete_source_files.call_count, 1)
        self.assertEqual(mock_parse_result_files_with_frames.call_count, 1)
        self.assertEqual(mock_try_to_upload_file.call_count, 1)
        self.assertEqual(mock_get_files_list_from_archive.call_count, 1)
        self.assertEqual(compare_minimum_ssim_with_results.call_count, 1)
        self.assertEqual(mock_compare_all_rendered_images_with_user_results_files.call_count, 1)
        self.mock_verification_result.assert_called_once_with(
            self.subtask_id,
            VerificationResult.MISMATCH.name,
        )

    def test_that_blender_verification_order_should_call_verification_result_with_result_error_if_download_fails(self):
        with mock.patch(
                'verifier.tasks.download_archives_from_storage',
                autospec=True,
                side_effect=VerificationError(
                    'error',
                    ErrorCode.VERIFIER_FILE_DOWNLOAD_FAILED,
                    self.compute_task_def['subtask_id']
                )
            ) as mock_download_archives_from_storage, \
            mock.patch('core.tasks.verification_result.delay', autospec=True) as mock_verification_result:  # noqa: E129
            self._send_blender_verification_order()

        self.assertEqual(mock_download_archives_from_storage.call_count, 1)
        mock_verification_result.assert_called_once_with(
            self.compute_task_def['subtask_id'],
            VerificationResult.ERROR.name,
            'error',
            ErrorCode.VERIFIER_FILE_DOWNLOAD_FAILED.name,
        )

    def test_that_blender_verification_order_should_call_verification_result_with_result_error_if_validation_of_downloaded_archives_fails(self):
        with mock.patch('verifier.tasks.download_archives_from_storage', autospec=True) as mock_download_archives_from_storage, \
            mock.patch(
                'verifier.tasks.validate_downloaded_archives',
                side_effect=VerificationError(
                    'error',
                    ErrorCode.VERIFIER_UNPACKING_ARCHIVE_FAILED,
                    self.subtask_id
                )
            ),  \
            mock.patch('core.tasks.verification_result.delay', autospec=True) as mock_verification_result:  # noqa: E125
            self._send_blender_verification_order()

        self.assertEqual(mock_download_archives_from_storage.call_count, 1)
        mock_verification_result.assert_called_once_with(
            self.subtask_id,
            VerificationResult.ERROR.name,
            'error',
            ErrorCode.VERIFIER_UNPACKING_ARCHIVE_FAILED.name,
        )

    def test_blender_verification_order_should_call_verification_result_with_result_error_if_unpacking_archive_fails(self):
        with  mock.patch('verifier.tasks.download_archives_from_storage', autospec=True) as mock_download_archives_from_storage, \
            mock.patch('verifier.tasks.validate_downloaded_archives', autospec=True) as mock_validate_downloaded_archives, \
            mock.patch('verifier.tasks.unpack_archives', side_effect=VerificationError(
            "error",
            ErrorCode.VERIFIER_UNPACKING_ARCHIVE_FAILED,
            self.subtask_id
        ), autospec=True), \
            mock.patch('core.tasks.verification_result.delay', autospec=True) as mock_verification_result:  # noqa: E125

            self._send_blender_verification_order()

        self.assertEqual(mock_download_archives_from_storage.call_count, 1)
        self.assertEqual(mock_validate_downloaded_archives.call_count, 1)
        mock_verification_result.assert_called_once_with(
            self.subtask_id,
            VerificationResult.ERROR.name,
            'error',
            ErrorCode.VERIFIER_UNPACKING_ARCHIVE_FAILED.name,
        )

    def test_blender_verification_order_should_call_verification_result_with_result_error_if_render_image_raises_exception(self):
        with mock.patch('verifier.tasks.download_archives_from_storage', autospec=True) as mock_download_archives_from_storage, \
            mock.patch('verifier.tasks.validate_downloaded_archives', autospec=True) as mock_validate_downloaded_archives, \
            mock.patch('verifier.tasks.unpack_archives', autospec=True) as mock_unpack_archives, \
            mock.patch('verifier.tasks.get_files_list_from_archive', autospec=True, side_effect=[self.frames]) as mock_get_files_list_from_archive, \
            mock.patch('verifier.tasks.parse_result_files_with_frames', autospec=True, return_value=self.mocked_parse_result_files_with_frames()) as mock_parse_result_files_with_frames, \
            mock.patch('core.tasks.verification_result.delay', autospec=True) as mock_verification_result, \
            mock.patch(
                'verifier.tasks.render_images_by_frames',
                side_effect=VerificationError(
                    'error',
                    ErrorCode.VERIFIER_RUNNING_BLENDER_FAILED,
                    self.subtask_id
                ),
                autospec=True, return_value=(True, True)):  # noqa: E125

            self._send_blender_verification_order()

        self.assertEqual(mock_download_archives_from_storage.call_count, 1)
        self.assertEqual(mock_validate_downloaded_archives.call_count, 1)
        self.assertEqual(mock_get_files_list_from_archive.call_count, 1)
        self.assertEqual(mock_parse_result_files_with_frames.call_count, 1)
        self.assertEqual(mock_unpack_archives.call_count, 1)
        mock_verification_result.assert_called_once_with(
            self.subtask_id,
            VerificationResult.ERROR.name,
            'error',
            ErrorCode.VERIFIER_RUNNING_BLENDER_FAILED.name,
        )

    def test_blender_verification_order_should_call_verification_result_with_result_error_if_load_images_fails(self):
        with mock.patch('verifier.tasks.download_archives_from_storage', autospec=True) as mock_download_archives_from_storage, \
            mock.patch('verifier.tasks.validate_downloaded_archives', autospec=True) as mock_validate_downloaded_archives, \
            mock.patch('verifier.tasks.unpack_archives', autospec=True) as mock_unpack_archives, \
            mock.patch('verifier.tasks.get_files_list_from_archive', autospec=True, side_effect=[self.frames]) as mock_get_files_list_from_archive, \
            mock.patch('verifier.tasks.parse_result_files_with_frames', autospec=True, return_value=self.mocked_parse_result_files_with_frames()) as mock_parse_result_files_with_frames, \
            mock.patch('verifier.tasks.render_images_by_frames', autospec=True, return_value=(self.blender_output_file_name_list, self.parsed_all_files)) as mock_render_image, \
            mock.patch('verifier.tasks.delete_source_files', autospec=True) as mock_delete_source_files, \
            mock.patch('verifier.tasks.upload_blender_output_file', autospec=True) as mock_try_to_upload_file, \
            mock.patch(
                'verifier.tasks.compare_all_rendered_images_with_user_results_files',
                autospec=True,
                side_effect=VerificationError(
                    'error',
                    ErrorCode.VERIFIER_LOADING_FILES_INTO_MEMORY_FAILED,
                    self.subtask_id
                ),
            ), \
            mock.patch('core.tasks.verification_result.delay', autospec=True) as mock_verification_result:  # noqa: E125

            current_time = get_current_utc_timestamp()
            self._send_blender_verification_order(current_time=current_time)

        self.assertEqual(mock_download_archives_from_storage.call_count, 1)
        self.assertEqual(mock_parse_result_files_with_frames.call_count, 1)
        self.assertEqual(mock_validate_downloaded_archives.call_count, 1)
        self.assertEqual(mock_get_files_list_from_archive.call_count, 1)
        self.assertEqual(mock_unpack_archives.call_count, 1)
        mock_render_image.assert_called_once_with(
            frames=self.frames,
            parsed_files_to_compare=self.mocked_parse_result_files_with_frames(),
            output_format=self.output_format,
            scene_file=self.scene_file,
            subtask_id=self.subtask_id,
            verification_deadline=self._get_verification_deadline_as_timestamp(
                current_time,
                self.report_computed_task.size,
            ),
            blender_crop_script_parameters=self.blender_crop_script_parameters,
        )
        self.assertEqual(mock_delete_source_files.call_count, 1)
        self.assertEqual(mock_try_to_upload_file.call_count, 1)
        mock_verification_result.assert_called_once_with(
            self.subtask_id,
            VerificationResult.ERROR.name,
            'error',
            ErrorCode.VERIFIER_LOADING_FILES_INTO_MEMORY_FAILED.name,
        )

    def test_blender_verification_order_should_call_verification_result_with_result_error_if_compare_ssim_raise_value_error(self):
        with mock.patch('verifier.tasks.download_archives_from_storage', autospec=True) as mock_download_archives_from_storage, \
            mock.patch('verifier.tasks.validate_downloaded_archives', autospec=True) as mock_validate_downloaded_archives, \
            mock.patch('verifier.tasks.unpack_archives', autospec=True) as mock_unpack_archives, \
            mock.patch('verifier.tasks.get_files_list_from_archive', autospec=True, side_effect=[self.frames]) as mock_get_files_list_from_archive, \
            mock.patch('verifier.tasks.parse_result_files_with_frames', autospec=True, return_value=self.mocked_parse_result_files_with_frames()) as mock_parse_result_files_with_frames, \
            mock.patch('verifier.tasks.render_images_by_frames', autospec=True, return_value=(self.blender_output_file_name_list, self.parsed_all_files)) as mock_render_image, \
            mock.patch('verifier.tasks.delete_source_files', autospec=True) as mock_delete_source_files, \
            mock.patch('verifier.tasks.upload_blender_output_file', autospec=True) as mock_try_to_upload_file, \
            mock.patch(
                'verifier.tasks.compare_all_rendered_images_with_user_results_files',
                autospec=True,
                side_effect=VerificationError(
                    'error',
                    ErrorCode.VERIFIER_COMPUTING_SSIM_FAILED,
                    self.subtask_id
                ),
            ), \
            mock.patch('core.tasks.verification_result.delay', autospec=True) as mock_verification_result:  # noqa: E125

            current_time = get_current_utc_timestamp()
            self._send_blender_verification_order(current_time=current_time)

        self.assertEqual(mock_download_archives_from_storage.call_count, 1)
        self.assertEqual(mock_parse_result_files_with_frames.call_count, 1)
        self.assertEqual(mock_validate_downloaded_archives.call_count, 1)
        self.assertEqual(mock_get_files_list_from_archive.call_count, 1)
        self.assertEqual(mock_unpack_archives.call_count, 1)
        mock_render_image.assert_called_once_with(
            frames=self.frames,
            parsed_files_to_compare=self.mocked_parse_result_files_with_frames(),
            output_format=self.output_format,
            scene_file=self.scene_file,
            subtask_id=self.subtask_id,
            verification_deadline=self._get_verification_deadline_as_timestamp(
                current_time,
                self.report_computed_task.size,
            ),
            blender_crop_script_parameters=self.blender_crop_script_parameters,
        )
        self.assertEqual(mock_delete_source_files.call_count, 1)
        self.assertEqual(mock_try_to_upload_file.call_count, 1)
        mock_verification_result.assert_called_once_with(
            self.subtask_id,
            VerificationResult.ERROR.name,
            'error',
            ErrorCode.VERIFIER_COMPUTING_SSIM_FAILED.name,
        )

    def test_that_blender_verification_order_should_work_properly_when_there_is_more_than_one_frame_to_render(self):
        with mock.patch('verifier.tasks.download_archives_from_storage', autospec=True) as mock_download_archives_from_storage,\
            mock.patch('verifier.tasks.validate_downloaded_archives', autospec=True) as mock_validate_downloaded_archives, \
            mock.patch('verifier.tasks.unpack_archives', autospec=True) as mock_unpack_archives, \
            mock.patch('verifier.tasks.get_files_list_from_archive', autospec=True, side_effect=[self.multi_frames]) as mock_get_files_list_from_archive, \
            mock.patch('verifier.tasks.parse_result_files_with_frames', autospec=True, return_value=self.parsed_multi_frames_files) as mock_parse_result_files_with_frames, \
            mock.patch('verifier.tasks.render_images_by_frames', autospec=True, return_value=(self.multi_frames_blender_output_file_name_list, self.parsed_multi_frames_files)) as mock_render_image, \
            mock.patch('verifier.tasks.delete_source_files', autospec=True) as mock_delete_source_files, \
            mock.patch('verifier.tasks.upload_blender_output_file', autospec=True) as mock_try_to_upload_file, \
            mock.patch('verifier.tasks.compare_all_rendered_images_with_user_results_files', autospec=True) as mock_compare_all_rendered_images_with_user_results_files, \
            mock.patch('verifier.tasks.compare_minimum_ssim_with_results', side_effect=self._verification_results_match(self.subtask_id)) as compare_minimum_ssim_with_results:  # noqa: E125

            current_time = get_current_utc_timestamp()

            self._send_blender_verification_order(
                current_time=current_time,
                frames=self.multi_frames,
            )

        self.assertEqual(mock_download_archives_from_storage.call_count, 1)
        self.assertEqual(mock_validate_downloaded_archives.call_count, 1)
        self.assertEqual(mock_unpack_archives.call_count, 1)
        mock_render_image.assert_called_once_with(
            frames=self.multi_frames,
            parsed_files_to_compare=self.parsed_multi_frames_files,
            output_format=self.output_format,
            scene_file=self.scene_file,
            subtask_id=self.subtask_id,
            verification_deadline=self._get_verification_deadline_as_timestamp(
                current_time,
                self.report_computed_task.size,
            ),
            blender_crop_script_parameters=self.blender_crop_script_parameters,
        )
        self.assertEqual(mock_delete_source_files.call_count, 1)
        self.assertEqual(mock_get_files_list_from_archive.call_count, 1)
        self.assertEqual(mock_try_to_upload_file.call_count, 1)
        self.assertEqual(mock_compare_all_rendered_images_with_user_results_files.call_count, 1)
        self.assertEqual(compare_minimum_ssim_with_results.call_count, 1)
        self.assertEqual(mock_parse_result_files_with_frames.call_count, 1)
        self.mock_verification_result.assert_called_once_with(
            self.subtask_id,
            VerificationResult.MATCH.name,
        )

    def _verification_results_match(self, subtask_id):
        self.mock_verification_result(
            subtask_id,
            VerificationResult.MATCH.name
        )

    def _verification_results_mismatch(self, subtask_id):
        self.mock_verification_result(
            subtask_id,
            VerificationResult.MISMATCH.name
        )

    def _compare_images_positive(self, _image_1, _image_2, subtask_id):
        self.mock_verification_result(
            subtask_id,
            VerificationResult.MATCH.name
        )

    def _compare_images_negative(self, _image_1, _image_2, subtask_id):
        self.mock_verification_result(
            subtask_id,
            VerificationResult.MISMATCH.name
        )

    def _send_blender_verification_order(self, current_time: int= get_current_utc_timestamp(), frames=None):
        blender_verification_order(
            subtask_id=self.subtask_id,
            source_package_path=self.source_package_path,
            source_size=self.report_computed_task.task_to_compute.size,
            source_package_hash=self.report_computed_task.task_to_compute.package_hash,
            result_package_path=self.result_package_path,
            result_size=self.report_computed_task.size,  # pylint: disable=no-member
            result_package_hash=self.report_computed_task.package_hash,  # pylint: disable=no-member  # pylint: disable=no-member
            output_format=BlenderSubtaskDefinition.OutputFormat[
                self.output_format
            ].name,
            scene_file=self.scene_file,
            verification_deadline=self._get_verification_deadline_as_timestamp(
                current_time,
                self.report_computed_task.size,
            ),
            frames=frames if frames is not None else self.frames,
            blender_crop_script_parameters=self.blender_crop_script_parameters,
        )
