from base64 import b64encode

from django.test                    import override_settings
from django.test                    import TestCase
from django.urls                    import reverse

from golem_messages.cryptography    import ecdsa_verify
from golem_messages.shortcuts       import dump
from golem_messages                 import message

from utils.constants                import ErrorCode
from utils.testing_helpers          import generate_ecc_key_pair


(CONCENT_PRIVATE_KEY,   CONCENT_PUBLIC_KEY)   = generate_ecc_key_pair()
(PROVIDER_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY)  = generate_ecc_key_pair()
(REQUESTOR_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY) = generate_ecc_key_pair()


@override_settings(
    CONCENT_PRIVATE_KEY    = CONCENT_PRIVATE_KEY,
    CONCENT_PUBLIC_KEY     = CONCENT_PUBLIC_KEY,
    CONCENT_MESSAGING_TIME = 10,  # seconds
)
class ApiViewsIntegrationTest(TestCase):
    def setUp(self):
        self.dummy_message_to_concent = message.Ping()
        self.serialized_dummy_message_to_concent = dump(self.dummy_message_to_concent, PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

    def test_any_message_to_concent_report_missing_key_returns_400_error(self):
        """
        Tests if any golem message to Concent will return HTTP 400 error
        if no key was provided in header.
        """

        response = self.client.post(
            reverse('core:send'),
            data            = self.serialized_dummy_message_to_concent,
            content_type    = 'application/octet-stream',
        )

        self.assertEqual(response.status_code,  400)
        self.assertIn('error',                          response.json())
        self.assertIn('error_code',                     response.json())
        self.assertEqual(response.json()['error_code'], ErrorCode.HEADER_CLIENT_PUBLIC_KEY_MISSING.value)

    def test_any_message_to_concent_report_bad_key_returns_400_error(self):
        """
        Tests if any golem message to Concent will return HTTP 400 error
        if bad key was provided in header.
        """

        response = self.client.post(
            reverse('core:send'),
            data                           = self.serialized_dummy_message_to_concent,
            content_type                   = 'application/octet-stream',
            HTTP_CONCENT_CLIENT_PUBLIC_KEY = 'bad__key' * 11,
        )

        self.assertEqual(response.status_code,  400)
        self.assertIn('error',                          response.json())
        self.assertIn('error_code',                     response.json())
        self.assertEqual(response.json()['error_code'], ErrorCode.HEADER_CLIENT_PUBLIC_KEY_NOT_BASE64_ENCODED_VALUE.value)

    def test_any_message_to_concent_report_truncated_key_returns_400_error(self):
        """
        Tests if any golem message to Concent will return HTTP 400 error
        if truncated key was provided in header.
        """

        response = self.client.post(
            reverse('core:send'),
            data                           = self.serialized_dummy_message_to_concent,
            content_type                   = 'application/octet-stream',
            HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY)[:32].decode('ascii'),
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('error',                          response.json())
        self.assertIn('error_code',                     response.json())
        self.assertEqual(response.json()['error_code'], ErrorCode.HEADER_CLIENT_PUBLIC_KEY_WRONG_LENGTH.value)

    def test_any_message_to_concent_report_empty_key_returns_400_error(self):
        """
        Tests if any golem message to Concent will return HTTP 400 error
        if empty key was provided in header.
        """

        response = self.client.post(
            reverse('core:send'),
            data                           = self.serialized_dummy_message_to_concent,
            content_type                   = 'application/octet-stream',
            HTTP_CONCENT_CLIENT_PUBLIC_KEY = '',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('error',                          response.json())
        self.assertIn('error_code',                     response.json())
        self.assertEqual(response.json()['error_code'], ErrorCode.HEADER_CLIENT_PUBLIC_KEY_MISSING.value)

    def test_any_message_to_concent_report_empty_content_type_returns_400_error(self):
        """
        Tests if any golem message to Concent will return HTTP 400 error
        if content_type is missing in header.
        """

        response = self.client.post(
            reverse('core:send'),
            data                           = self.serialized_dummy_message_to_concent,
            content_type                   = '',
            HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
        )

        self.assertEqual(response.status_code,  400)
        self.assertIn('error',                          response.json())
        self.assertIn('error_code',                     response.json())
        self.assertEqual(response.json()['error_code'], ErrorCode.HEADER_CONTENT_TYPE_MISSING.value)

    def test_any_message_to_concent_report_wrong_signature_returns_400_error(self):
        """
        Tests if a golem message to Concent signed with a wrong key returns HTTP 400 error.
        """

        assert ecdsa_verify(PROVIDER_PUBLIC_KEY, self.dummy_message_to_concent.sig, self.dummy_message_to_concent.get_short_hash())
        response = self.client.post(
            reverse('core:send'),
            data                           = self.serialized_dummy_message_to_concent,
            content_type                   = 'application/octet-stream',
            HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('error',                          response.json())
        self.assertIn('error_code',                     response.json())
        self.assertEqual(response.json()['error_code'], ErrorCode.MESSAGE_FAILED_TO_DECODE.value)
