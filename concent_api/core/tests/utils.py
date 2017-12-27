from base64                 import b64encode

from django.conf            import settings
from django.test            import TestCase

from golem_messages         import dump
from golem_messages         import message
import dateutil.parser

from utils.testing_helpers  import generate_ecc_key_pair


class ConcentIntegrationTestCase(TestCase):

    def setUp(self):
        super().setUp()
        self.PROVIDER_PRIVATE_KEY, self.PROVIDER_PUBLIC_KEY = generate_ecc_key_pair()
        self.REQUESTOR_PRIVATE_KEY, self.REQUESTOR_PUBLIC_KEY = generate_ecc_key_pair()

    def _get_encoded_key(self, key):
        """ Returns given key encoded. """
        return b64encode(key).decode('ascii')

    def _get_encoded_provider_public_key(self):
        """ Returns provider public key encoded. """
        return self._get_encoded_key(self.PROVIDER_PUBLIC_KEY)

    def _get_encoded_requestor_public_key(self):
        """ Returns provider public key encoded. """
        return self._get_encoded_key(self.REQUESTOR_PUBLIC_KEY)

    def _get_serialized_force_get_task_result(self, task_to_compute, timestamp, requestor_private_key=None):
        """ Returns MessageForceGetTaskResult serialized. """
        force_report_computed_task = message.ForceGetTaskResult(
            timestamp               = self._parse_iso_date_to_timestamp(timestamp),
            message_task_to_compute = task_to_compute,
        )
        return dump(
            force_report_computed_task,
            requestor_private_key or self.REQUESTOR_PRIVATE_KEY,
            settings.CONCENT_PUBLIC_KEY
        )

    def _get_serialized_task_to_compute(self, timestamp, deadline, task_id=1, provider_private_key=None,
                                        requestor_public_key=None):
        """ Returns MessageTaskToCompute serialized. """
        task_to_compute = message.MessageTaskToCompute(
            timestamp               = self._parse_iso_date_to_timestamp(timestamp),
            task_id                 = task_id,
            deadline                = self._parse_iso_date_to_timestamp(deadline),
        )
        return dump(
            task_to_compute,
            provider_private_key or self.PROVIDER_PRIVATE_KEY,
            requestor_public_key or self.REQUESTOR_PUBLIC_KEY
        )

    def _parse_iso_date_to_timestamp(self, date_string):
        return int(dateutil.parser.parse(date_string).timestamp())
