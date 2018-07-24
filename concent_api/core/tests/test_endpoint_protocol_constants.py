from django.conf            import settings
from django.test            import override_settings
from django.urls            import reverse

from core.tests.utils       import ConcentIntegrationTestCase
from common.testing_helpers  import generate_ecc_key_pair


(CONCENT_PRIVATE_KEY, CONCENT_PUBLIC_KEY) = generate_ecc_key_pair()


@override_settings(
    CONCENT_PRIVATE_KEY=CONCENT_PRIVATE_KEY,
    CONCENT_PUBLIC_KEY=CONCENT_PUBLIC_KEY,
    CONCENT_MESSAGING_TIME=1,  # seconds
    FORCE_ACCEPTANCE_TIME=2,  # seconds
    MINIMUM_UPLOAD_RATE=4,  # bits per second
    DOWNLOAD_LEADIN_TIME=6,  # seconds
    PAYMENT_DUE_TIME=5,  # seconds
)
class ProtocolConstantsTest(ConcentIntegrationTestCase):

    def test_protocol_constants_should_return_values_from_settings(self):
        """
        Tests if call to `provider-constants` endpoint returns protocol constants from settings.
        """

        protocol_constants_settings = {
            'CONCENT_MESSAGING_TIME': settings.CONCENT_MESSAGING_TIME,
            'FORCE_ACCEPTANCE_TIME': settings.FORCE_ACCEPTANCE_TIME,
            'MINIMUM_UPLOAD_RATE': settings.MINIMUM_UPLOAD_RATE,
            'DOWNLOAD_LEADIN_TIME': settings.DOWNLOAD_LEADIN_TIME,
            'PAYMENT_DUE_TIME': settings.PAYMENT_DUE_TIME,
        }

        expected_protocol_constants = {name.lower(): value for name, value in protocol_constants_settings.items()}

        response = self.client.get(
            reverse('core:protocol_constants'),
        )

        self.assertEqual(response.json(), expected_protocol_constants)
