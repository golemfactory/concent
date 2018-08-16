from unittest import TestCase

from signing_service.utils import is_private_key_valid
from signing_service.utils import is_public_key_valid


class SigningServiceIsPublicKeyValidTestCase(TestCase):

    def test_that_is_public_key_valid_should_return_true_for_correct_public_key_length(self):
        public_key = b'x' * 64

        self.assertTrue(is_public_key_valid(public_key))

    def test_that_is_public_key_valid_public_should_return_false_for_too_short_public_key_length(self):
        public_key = b'x' * 63

        self.assertFalse(is_public_key_valid(public_key))

    def test_that_is_public_key_valid_should_return_false_for_too_long_public_key_length(self):
        public_key = b'x' * 65

        self.assertFalse(is_public_key_valid(public_key))


class SigningServiceIsPrivateKeyValidTestCase(TestCase):

    def test_that_is_private_key_valid_should_return_true_for_correct_private_key_length(self):
        private_key = 'a' * 64

        self.assertTrue(is_private_key_valid(private_key))

    def test_that_is_private_key_valid_should_return_false_for_too_short_private_key_length(self):
        private_key = 'a' * 63

        self.assertFalse(is_private_key_valid(private_key))

    def test_that_is_private_key_valid_return_false_for_too_long_private_key_length(self):
        private_key = 'a' * 65

        self.assertFalse(is_private_key_valid(private_key))

    def test_that_is_private_key_valid_return_false_for_invalid_characters(self):
        private_key = '-' * 64

        self.assertFalse(is_private_key_valid(private_key))
