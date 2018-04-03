from django.conf            import settings
from django.test            import override_settings
from django.urls            import reverse

from core.tests.utils       import ConcentIntegrationTestCase
from utils.testing_helpers  import generate_ecc_key_pair


(CONCENT_PRIVATE_KEY, CONCENT_PUBLIC_KEY) = generate_ecc_key_pair()


@override_settings(
    CONCENT_PRIVATE_KEY       = CONCENT_PRIVATE_KEY,
    CONCENT_PUBLIC_KEY        = CONCENT_PUBLIC_KEY,
    CONCENT_MESSAGING_TIME    = 1,  # seconds
    FORCE_ACCEPTANCE_TIME     = 2,  # seconds
    MAXIMUM_DOWNLOAD_TIME     = 4,  # seconds
    SUBTASK_VERIFICATION_TIME = 3  # seconds
)
class ProtocolConstantsTest(ConcentIntegrationTestCase):

    def test_protocol_constants_should_return_values_from_settings(self):
        """
        Tests if call to `provider-constants` endpoint returns protocol constants from settings.
        """

        protocol_constants_settings = {
            'CONCENT_MESSAGING_TIME':       settings.CONCENT_MESSAGING_TIME,
            'FORCE_ACCEPTANCE_TIME':        settings.FORCE_ACCEPTANCE_TIME,
            'MAXIMUM_DOWNLOAD_TIME':        settings.MAXIMUM_DOWNLOAD_TIME,
            'SUBTASK_VERIFICATION_TIME':    settings.SUBTASK_VERIFICATION_TIME,
        }

        expected_protocol_constants = {name.lower(): value for name, value in protocol_constants_settings.items()}

        response = self.client.get(
            reverse('core:protocol_constants'),
        )

        self.assertEqual(response.json(), expected_protocol_constants)
