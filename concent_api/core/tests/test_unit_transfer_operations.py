from django.test                    import TestCase

from golem_messages                 import message
from core.transfer_operations       import sign_message
from utils.testing_helpers          import generate_ecc_key_pair

(CONCENT_PRIVATE_KEY, CONCENT_PUBLIC_KEY) = generate_ecc_key_pair()


class AddSignatureToMessage(TestCase):

    def setUp(self):
        self.ping_message = message.Ping()

    def test_add_signature_with_correct_keys_pair(self):

        self.assertEqual(self.ping_message.sig, None)

        ping_message = sign_message(self.ping_message, CONCENT_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        self.assertIsNot(ping_message.sig, None)
        self.assertIsInstance(ping_message.sig, bytes)

    def test_empty_arguments_to_add_signature(self):

        with self.assertRaises(AssertionError):
            sign_message(self.ping_message, CONCENT_PRIVATE_KEY, None)

        with self.assertRaises(AssertionError):
            sign_message(self.ping_message, CONCENT_PUBLIC_KEY, None)

        with self.assertRaises(AssertionError):
            sign_message(CONCENT_PRIVATE_KEY, CONCENT_PUBLIC_KEY, None)

        with self.assertRaises(AssertionError):
            sign_message(None, None, None)

    def test_wrong_keys_to_add_signature(self):

        with self.assertRaises(AssertionError):
            sign_message(self.ping_message, CONCENT_PRIVATE_KEY, CONCENT_PRIVATE_KEY)

        with self.assertRaises(AssertionError):
            sign_message(self.ping_message, CONCENT_PUBLIC_KEY, CONCENT_PUBLIC_KEY)
