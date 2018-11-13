import tempfile
from unittest import TestCase
import zipfile

from assertpy import assert_that
from django.conf import settings
from django.test import override_settings
import mock
from numpy import ones
from numpy import zeros
from numpy.core.records import ndarray
import pytest

from common.constants import ErrorCode
from core.constants import VerificationResult
from core.utils import generate_uuid
from verifier.exceptions import VerificationError
from verifier.exceptions import VerificationMismatch
from verifier.utils import adjust_format_name
from verifier.utils import get_files_list_from_archive
from verifier.utils import are_image_sizes_and_color_channels_equal
from verifier.utils import compare_all_rendered_images_with_user_results_files
from verifier.utils import compare_images
from verifier.utils import compare_minimum_ssim_with_results
from verifier.utils import ensure_enough_result_files_provided
from verifier.utils import ensure_frames_have_related_files_to_compare
from verifier.utils import generate_base_blender_output_file_name
from verifier.utils import generate_full_blender_output_file_name
from verifier.utils import generate_upload_file_path
from verifier.utils import generate_verifier_storage_file_path
from verifier.utils import parse_result_files_with_frames
from verifier.utils import render_images_by_frames
from verifier.utils import upload_blender_output_file
from verifier.utils import validate_downloaded_archives


class VerifierUtilsTest(TestCase):

    def setUp(self):
        super().setUp()
        self.frames = [1, 2]
        self.result_files_list = ['result_240001.png', 'result_240002.png']
        self.output_format = 'PNG'
        self.parsed_files_to_compare = {
            1: ['/tmp/result_240001.png'],
            2: ['/tmp/result_240002.png'],
        }
        self.scene_file = 'scene-Helicopter-27-internal.blend'
        self.subtask_id = generate_uuid()
        self.correct_parsed_all_files = {
            1: [
                '/tmp/result_240001.png',
                '/tmp/out_scene-Helicopter-27-internal.blend_0001.png'
            ],
            2: [
                '/tmp/result_240002.png',
                '/tmp/out_scene-Helicopter-27-internal.blend_0002.png'
            ]
        }
        self.correct_blender_output_file_name_list = [
            '/tmp/out_scene-Helicopter-27-internal.blend_0001.png',
            '/tmp/out_scene-Helicopter-27-internal.blend_0002.png'
        ]
        self.image = mock.create_autospec(spec=ndarray, spec_set=True)
        self.image.shape = (2000, 3000, 3)
        self.image_diffrent_color_channel = mock.create_autospec(spec=ndarray, spec_set=True)
        self.image_diffrent_color_channel.shape = (2000, 3000)
        self.image_diffrent_size = mock.create_autospec(spec=ndarray, spec_set=True)
        self.image_diffrent_size.shape = (3000, 4000, 3)

        self.ssim_list = [0.99, 0.95]
        self.image_pairs = [
            (self.image, self.image),
            (self.image, self.image),
        ]
        self.image_ones = ones(shape=(1920, 1080, 3), dtype='uint8')
        self.image_zeros = zeros(shape=(1920, 1080, 3), dtype='uint8')
        self.image_diffrent_size = zeros(shape=(1080, 1920, 3), dtype='uint8')

    def test_that_are_image_sizes_and_color_channels_equal_should_return_false_if_sizes_in_pixels_are_not_equal(self):
        result = are_image_sizes_and_color_channels_equal(self.image, self.image_diffrent_size)
        self.assertEqual(result, False)

    def test_that_are_image_sizes_and_color_channels_equal_should_return_false_if_color_channels_are_not_equal(self):
        result = are_image_sizes_and_color_channels_equal(self.image, self.image_diffrent_color_channel)
        self.assertEqual(result, False)

    def test_that_are_image_sizes_and_color_channels_equal_should_return_true_if_sizes_in_pixels_are_equal(self):
        result = are_image_sizes_and_color_channels_equal(self.image, self.image)
        self.assertEqual(result, True)

    def test_that_parse_result_files_with_frames_function_should_return_correct_dict(self):
        parsed_files_to_compare = parse_result_files_with_frames(
            frames=self.frames,
            result_files_list=self.result_files_list,
            output_format=self.output_format,
        )

        self.assertEqual(parsed_files_to_compare, self.parsed_files_to_compare)

    def test_that_parse_results_files_with_frames_function_should_return_empty_dict_because_of_wrong_output_format(self):
        parsed_files_to_compare = parse_result_files_with_frames(
            frames=self.frames,
            result_files_list=self.result_files_list,
            output_format='JPG',
        )

        self.assertEqual(parsed_files_to_compare, {})

    def test_that_render_images_by_frames_function_should_return_correct_output_files_names(self):
        with mock.patch('verifier.utils.render_image', autospec=True) as mock_render_image:
            (blender_output_file_name_list, parsed_files_to_compare) = render_images_by_frames(
                parsed_files_to_compare=self.parsed_files_to_compare,
                frames=self.frames,
                output_format=self.output_format,
                scene_file=self.scene_file,
                subtask_id=self.subtask_id,
                verification_deadline=None,
                blender_crop_script=None,
            )
            self.assertEqual(self.correct_parsed_all_files, parsed_files_to_compare)
            self.assertEqual(self.correct_blender_output_file_name_list, blender_output_file_name_list)
            self.assertEqual(mock_render_image.call_count, 2)

    def test_that_upload_blender_output_file_should_correctly_upload_files(self):
        with mock.patch('verifier.utils.try_to_upload_blender_output_file', autospec=True) as mock_try_to_upload:
            try:
                upload_blender_output_file(
                    frames=self.frames,
                    blender_output_file_name_list=self.correct_blender_output_file_name_list,
                    output_format=self.output_format,
                    subtask_id=self.subtask_id,
                )
            except Exception:  # pylint: disable=broad-except
                self.fail()

        self.assertEqual(mock_try_to_upload.call_count, 2)

    def test_that_method_should_raise_verification_mismatch_when_any_result_file_missing(self):
        with self.assertRaises(VerificationMismatch):
            ensure_enough_result_files_provided(
                frames=[1, 2, 3],
                result_files_list=self.result_files_list,
                subtask_id=self.subtask_id,
            )

    def test_that_method_should_accept_frames_and_result_files_when_correct_variable_is_passed(self):
        try:
            ensure_enough_result_files_provided(
                frames=self.frames,
                result_files_list=self.result_files_list,
                subtask_id=self.subtask_id,
            )
        except Exception:  # pylint: disable=broad-except
            self.fail()

    def test_that_method_should_log_warning_if_there_is_more_result_files_than_frames(self):
        with mock.patch('verifier.utils.logger.warning') as logging_warning_mock:
            ensure_enough_result_files_provided(
                frames=[1],
                result_files_list=self.result_files_list,
                subtask_id=self.subtask_id,
            )
            logging_warning_mock.assert_called_once_with(f'SUBTASK_ID: {self.subtask_id}. There is more result files than frames to render')

    def test_that_method_should_raise_verification_mismatch_when_frames_and_parsed_files_are_not_the_same(self):
        with self.assertRaises(VerificationMismatch):
            ensure_frames_have_related_files_to_compare(
                frames=[1],
                parsed_files_to_compare=self.correct_parsed_all_files,
                subtask_id=self.subtask_id,
            )

    def test_that_method_should_accept_correct_frames_list_and_parsed_result_files(self):
        try:
            ensure_frames_have_related_files_to_compare(
                frames=self.frames,
                parsed_files_to_compare=self.correct_parsed_all_files,
                subtask_id=self.subtask_id,
            )
        except Exception:  # pylint: disable=broad-except
            self.fail()

    def test_that_method_should_add_ssim_to_list(self):
        with mock.patch('verifier.utils.load_images', side_effect=self.image_pairs) as mock_load_images, \
            mock.patch('verifier.utils.are_image_sizes_and_color_channels_equal', return_value=True) as mock_are_image_sizes_and_color_channels_equal, \
            mock.patch('verifier.utils.compare_images', side_effect=self.ssim_list) as mock_compare_images:  # noqa: E125

            ssim_list = compare_all_rendered_images_with_user_results_files(
                parsed_files_to_compare=self.correct_parsed_all_files,
                subtask_id=self.subtask_id,
            )

        self.assertEqual(mock_load_images.call_count, 2)
        self.assertEqual(mock_are_image_sizes_and_color_channels_equal.call_count, 2)
        self.assertEqual(mock_compare_images.call_count, 2)
        self.assertEqual(self.ssim_list, ssim_list)

    @override_settings(
        VERIFIER_MIN_SSIM=0.95
    )
    def test_that_method_should_raise_verification_mismatch_if_any_of_ssim_from_list_is_lower_than_verifier_min_ssim(self):
        with self.assertRaises(VerificationMismatch):
            compare_minimum_ssim_with_results(
                ssim_list=[0.96, 0.90, 0.97],
                subtask_id=self.subtask_id,
            )

    @override_settings(
        VERIFIER_MIN_SSIM=0.95
    )
    def test_that_method_should_accept_ssim_list_and_delay_verification_result_with_match(self):
        with mock.patch('verifier.utils.verification_result.delay', autospec=True) as mock_verification_result:
            compare_minimum_ssim_with_results(
                ssim_list=[0.96, 0.99, 0.97],
                subtask_id=self.subtask_id,
            )

            mock_verification_result.assert_called_once_with(
                self.subtask_id,
                VerificationResult.MATCH.name,
            )

    def test_that_for_the_same_images_metod_produces_ssim_equal_one(self):
        ssim = compare_images(self.image_ones, self.image_ones, 'subtask_id')
        self.assertEqual(ssim, 1.0)

    @override_settings(
        VERIFIER_MIN_SSIM=0.95
    )
    def test_that_for_different_images_calculated_ssim_is_below_min(self):
        ssim = compare_images(self.image_ones, self.image_zeros, 'subtask_id')
        self.assertTrue(ssim < settings.VERIFIER_MIN_SSIM)

    def test_that_method_raise_verification_error_when_images_have_diffrent_sizes(self):
        with self.assertRaises(VerificationError):
            compare_images(self.image_ones, self.image_diffrent_size, 'subtask_id')


class TestGenerateFilePathMethods():

    @pytest.mark.parametrize(('storage_path', 'file_name', 'expected'), [
        ('tmp/', 'test_file.png', 'tmp/test_file.png'),
        ('tmp', 'test_file.png', 'tmp/test_file.png'),
    ])  # pylint: disable=no-self-use
    def test_that_method_returns_correct_verifier_storage_file_path(self, storage_path, file_name, expected):
        with override_settings(VERIFIER_STORAGE_PATH=storage_path):
            verifier_storage_file_path = generate_verifier_storage_file_path(file_name=file_name)

            assert_that(verifier_storage_file_path).is_equal_to(expected)

    @pytest.mark.parametrize(('subtask_id', 'extension', 'frame_number', 'expected'), [
        ('subtask_id', 'PNG', '22', 'blender/verifier-output/subtask_id/subtask_id_0022.png'),
        ('subtask_id', 'PNG', 22, 'blender/verifier-output/subtask_id/subtask_id_0022.png'),
    ])  # pylint: disable=no-self-use
    def test_that_method_returns_correct_upload_file_path(self, subtask_id, extension, frame_number, expected):
        upload_file_path = generate_upload_file_path(
            subtask_id=subtask_id,
            extension=extension,
            frame_number=frame_number,
        )

        assert_that(upload_file_path).is_equal_to(expected)

    @pytest.mark.parametrize(('storage_path', 'scene_file', 'expected'), [
        ('tmp/', 'test_scene_file', 'tmp/out_test_scene_file_'),
        ('tmp', 'test_scene_file', 'tmp/out_test_scene_file_'),
    ])  # pylint: disable=no-self-use
    def test_that_method_returns_correct_base_blender_output_file_name(self, storage_path, scene_file, expected):
        with override_settings(VERIFIER_STORAGE_PATH=storage_path):
            blender_output_file_name = generate_base_blender_output_file_name(scene_file)

        assert_that(blender_output_file_name).is_equal_to(expected)

    @pytest.mark.parametrize(('scene_file', 'frame_number', 'output_format', 'expected'), [
        ('test_scene_file', 4, 'PNG', '/tmp/out_test_scene_file_0004.png'),
        ('test_scene_file', 4, 'png', '/tmp/out_test_scene_file_0004.png'),
        ('test_scene_file', 44444, 'PNG', '/tmp/out_test_scene_file_44444.png'),
    ])  # pylint: disable=no-self-use
    def test_that_method_returns_correct_full_blender_output_file_name(self, scene_file, frame_number, output_format, expected):
        full_blender_output_file = generate_full_blender_output_file_name(
            scene_file=scene_file,
            frame_number=frame_number,
            output_format=output_format,
        )

        assert_that(full_blender_output_file).is_equal_to(expected)

    @pytest.mark.parametrize(('output_format', 'expected'), [
        ('png', 'PNG'),
        ('PNG', 'PNG'),
        ('jpg', 'JPEG'),
        ('JPG', 'JPEG'),
        ('jpeg', 'JPEG'),
        ('JPEG', 'JPEG'),
        ('exr', 'EXR'),
        ('EXR', 'EXR'),
    ])  # pylint: disable=no-self-use
    def test_that_method_returns_correct_format_name(self, output_format, expected):
        upper_output_format = adjust_format_name(output_format)

        assert_that(upper_output_format).is_equal_to(expected)


class TestValidateDownloadedArchives(object):
    @pytest.fixture(autouse=True)
    def setUp(self):
        self.scene_file = "kitten.blend"
        self.subtask_id = generate_uuid()
        self.archives_list = ["source.zip", "result.zip"]

    def test_that_if_archive_is_not_a_zip_file_verification_mismatch_is_raised(self):
        with mock.patch("verifier.utils.get_files_list_from_archive", side_effect=zipfile.BadZipFile):
            with pytest.raises(VerificationMismatch) as exception_wrapper:
                validate_downloaded_archives(self.subtask_id, self.archives_list, self.scene_file)
            assert_that(exception_wrapper.value.subtask_id).is_equal_to(self.subtask_id)

    def test_that_if_scene_file_is_missing_in_archived_files_verification_mismatch_is_raised(self):
        with mock.patch("verifier.utils.get_files_list_from_archive", side_effect=["", "result.png"]):
            with pytest.raises(VerificationMismatch) as exception_wrapper:
                validate_downloaded_archives(self.subtask_id, self.archives_list, self.scene_file)
            assert_that(exception_wrapper.value.subtask_id).is_equal_to(self.subtask_id)

    def test_that_if_one_of_the_files_to_be_unpacked_already_exists_verification_error_is_raised(self):
        with mock.patch("verifier.utils.get_files_list_from_archive", side_effect=["kitten.blend", "result.png"]):
            with mock.patch("verifier.utils.os.listdir", return_value="result.png"):
                with pytest.raises(VerificationError) as exception_wrapper:
                    validate_downloaded_archives(self.subtask_id, self.archives_list, self.scene_file)
                assert_that(exception_wrapper.value.subtask_id).is_equal_to(self.subtask_id)
                assert_that(exception_wrapper.value.error_code).\
                    is_equal_to(ErrorCode.VERIFIER_UNPACKING_ARCHIVE_FAILED)


@pytest.mark.parametrize('expected_list', [
    (['result1.blend', 'result2.blend', 'result3.blend']),
    (['tmp.txt', 'tmp']),
    (['tmp.txt']),
])
def test_that_method_returns_correct_archives_list(expected_list):
    with tempfile.TemporaryFile(prefix='archive_', suffix='.zip') as tmp:
        with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as archive:
            for file in expected_list:
                archive.writestr(file, 'Some content here')
        files_list = get_files_list_from_archive(tmp)
        assert_that(files_list).is_equal_to(expected_list)
