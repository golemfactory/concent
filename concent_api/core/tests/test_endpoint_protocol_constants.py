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
    SUBTASK_VERIFICATION_TIME = 3  # seconds
)
class ProtocolConstantsTest(ConcentIntegrationTestCase):

    def test_(self):
        """
        Tests if call to `provider-constants` endpoint returns protocol constants from settings.
        """

        protocol_constants_settings = {
            'CONCENT_MESSAGING_TIME':       settings.CONCENT_MESSAGING_TIME,
            'FORCE_ACCEPTANCE_TIME':        settings.FORCE_ACCEPTANCE_TIME,
            'SUBTASK_VERIFICATION_TIME':    settings.SUBTASK_VERIFICATION_TIME,
            'TOKEN_EXPIRATION_TIME':        settings.TOKEN_EXPIRATION_TIME,
        }

        response = self.client.get(
            reverse('core:protocol_constants'),
        )

        for setting_name, setting_value in protocol_constants_settings.items():
            self.assertIn(setting_name.lower(),                              response.json())
            self.assertIn('name',                                            response.json()[setting_name.lower()])
            self.assertIn('value',                                           response.json()[setting_name.lower()])
            self.assertEqual(response.json()[setting_name.lower()]['name'],  setting_name)
            self.assertEqual(response.json()[setting_name.lower()]['value'], setting_value)
