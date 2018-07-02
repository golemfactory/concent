from unittest import TestCase

from mock import mock
from django.test import override_settings
from numpy.core.records import ndarray

from core.constants import VerificationResult
from verifier.exceptions import VerificationMismatch
from verifier.utils import are_image_sizes_and_color_channels_equal
from verifier.utils import compare_all_rendered_images_with_user_results_files
from verifier.utils import compare_minimum_ssim_with_results
from verifier.utils import render_images_by_frames
from verifier.utils import parse_result_files_with_frames
from verifier.utils import upload_blender_output_file
from verifier.utils import ensure_enough_result_files_provided
from verifier.utils import ensure_frames_have_related_files_to_compare


class VerifierVerificationIntegrationTest(TestCase):

    def setUp(self):
        super().setUp()
        self.frames = [1, 2]
        self.result_files_list = ['result_0001.png', 'result_0002.png']
        self.output_format = 'PNG'
        self.parsed_files_to_compare = {
            1: ['/tmp/result_0001.png'],
            2: ['/tmp/result_0002.png'],
        }
        self.scene_file = 'scene-Helicopter-27-internal.blend'
        self.subtask_id = '1234-5678-9101-1213'
        self.correct_parsed_all_files = {
            1: [
                '/tmp/result_0001.png',
                '/tmp/out_scene-Helicopter-27-internal.blend_0001.png'
            ],
            2: [
                '/tmp/result_0002.png',
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
                verification_deadline=None
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
            logging_warning_mock.assert_called_once_with('There is more result files than frames to render')

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
