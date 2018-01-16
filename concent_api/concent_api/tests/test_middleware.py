from base64                 import b64encode

from django.test            import override_settings
from django.test            import TestCase
from django.urls            import reverse
from golem_messages         import dump
from golem_messages         import message
from golem_messages         import __version__

from utils.testing_helpers  import generate_ecc_key_pair


(CONCENT_PRIVATE_KEY,   CONCENT_PUBLIC_KEY)   = generate_ecc_key_pair()
(PROVIDER_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY)  = generate_ecc_key_pair()


@override_settings(
    CONCENT_PRIVATE_KEY    = CONCENT_PRIVATE_KEY,
    CONCENT_PUBLIC_KEY     = CONCENT_PUBLIC_KEY,
)
class GolemMessagesVersionMiddlewareTest(TestCase):

    def test_golem_messages_version_middleware_should_attach_http_header_to_response(self):
        """
        Tests that response from Concent:

        * Contains HTTP header 'Concent-Golem-Messages-Version'.
        * Header contains latest version of golem_messages package.
        """
        ping_message = message.Ping()
        serialized_ping_message = dump(ping_message, PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        response = self.client.post(
            reverse('core:send'),
            data                           = serialized_ping_message,
            content_type                   = 'application/octet-stream',
            HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
        )

        self.assertFalse(500 <= response.status_code < 600)
        self.assertIn('concent-golem-messages-version', response._headers)
        self.assertEqual(
            response._headers['concent-golem-messages-version'][0],
            'Concent-Golem-Messages-Version'
        )
        self.assertEqual(
            response._headers['concent-golem-messages-version'][1],
            __version__
        )
