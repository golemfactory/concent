from django.test                    import override_settings
from django.test                    import TestCase
from django.urls                    import reverse

from golem_messages.shortcuts       import dump
from golem_messages                 import message

from common.testing_helpers  import generate_ecc_key_pair


(CONCENT_PRIVATE_KEY,   CONCENT_PUBLIC_KEY)   = generate_ecc_key_pair()
(PROVIDER_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY)  = generate_ecc_key_pair()


@override_settings(
    CONCENT_PRIVATE_KEY    = CONCENT_PRIVATE_KEY,
    CONCENT_PUBLIC_KEY     = CONCENT_PUBLIC_KEY,
    CONCENT_MESSAGING_TIME = 10,  # seconds
)
class ApiViewsIntegrationTest(TestCase):
    def setUp(self):
        self.dummy_message_to_concent = message.Ping()
        self.serialized_dummy_message_to_concent = dump(self.dummy_message_to_concent, PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

    def test_any_message_to_concent_report_empty_content_type_returns_400_error(self):
        """
        Tests if any golem message to Concent will return HTTP 400 error
        if content_type is missing in header.
        """

        response = self.client.post(
            reverse('core:send'),
            data                           = self.serialized_dummy_message_to_concent,
            content_type                   = '',
        )

        self.assertEqual(response.status_code,  400)
        self.assertIn('error', response.json().keys())
