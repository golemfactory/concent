from unittest import TestCase

from mock import mock
from numpy.core.records import ndarray

from verifier.utils import are_image_sizes_and_color_channels_equal


class VerifierVerificationIntegrationTest(TestCase):

    def test_that_are_image_sizes_and_color_channels_equal_should_return_false_if_sizes_in_pixels_are_not_equal(self):
        image1 = mock.create_autospec(spec=ndarray, spec_set=True)
        image2 = mock.create_autospec(spec=ndarray, spec_set=True)
        image1.shape = (2000, 3000, 3)
        image2.shape = (3000, 4000, 3)
        result = are_image_sizes_and_color_channels_equal(image1, image2)
        self.assertEqual(result, False)

    def test_that_are_image_sizes_and_color_channels_equal_should_return_false_if_color_channels_are_not_equal(self):
        image1 = mock.create_autospec(spec=ndarray, spec_set=True)
        image2 = mock.create_autospec(spec=ndarray, spec_set=True)
        image1.shape = (2000, 3000, 3)
        image2.shape = (2000, 3000)
        result = are_image_sizes_and_color_channels_equal(image1, image2)
        self.assertEqual(result, False)

    def test_that_are_image_sizes_and_color_channels_equal_should_return_true_if_sizes_in_pixels_are_equal(self):
        image1 = mock.create_autospec(spec=ndarray, spec_set=True)
        image2 = mock.create_autospec(spec=ndarray, spec_set=True)
        image1.shape = (2000, 3000, 3)
        image2.shape = (2000, 3000, 3)
        result = are_image_sizes_and_color_channels_equal(image1, image2)
        self.assertEqual(result, True)
