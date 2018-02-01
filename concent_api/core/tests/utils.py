from base64                 import b64encode

from django.conf            import settings
from django.test            import TestCase

from freezegun              import freeze_time

from golem_messages         import dump
from golem_messages         import message
import dateutil.parser

from utils.testing_helpers  import generate_ecc_key_pair


class ConcentIntegrationTestCase(TestCase):

    def setUp(self):
        super().setUp()
        (self.PROVIDER_PRIVATE_KEY,  self.PROVIDER_PUBLIC_KEY)    = generate_ecc_key_pair()
        (self.REQUESTOR_PRIVATE_KEY, self.REQUESTOR_PUBLIC_KEY)   = generate_ecc_key_pair()

    def _get_encoded_key(self, key):  # pylint: disable=no-self-use
        """ Returns given key encoded. """
        return b64encode(key).decode('ascii')

    def _get_encoded_provider_public_key(self):
        """ Returns provider public key encoded. """
        return self._get_encoded_key(self.PROVIDER_PUBLIC_KEY)

    def _get_encoded_requestor_public_key(self):
        """ Returns provider public key encoded. """
        return self._get_encoded_key(self.REQUESTOR_PUBLIC_KEY)

    def _get_serialized_force_get_task_result(self, report_computed_task, timestamp, requestor_private_key=None):
        """ Returns MessageForceGetTaskResult serialized. """
        with freeze_time(timestamp):
            force_get_task_result = message.concents.ForceGetTaskResult(
                report_computed_task    = report_computed_task,
            )
        return dump(
            force_get_task_result,
            requestor_private_key or self.REQUESTOR_PRIVATE_KEY,
            settings.CONCENT_PUBLIC_KEY
        )

    def _get_deserialized_report_computed_task(self, task_to_compute, size=None, checksum=None):  # pylint: disable=no-self-use
        """ Returns ReportComputedTask deserialized. """
        report_computed_task = message.ReportComputedTask(
            task_to_compute = task_to_compute,
            size            = size,
            checksum        = checksum
        )
        return report_computed_task

    def _get_deserialized_task_to_compute(self, timestamp, deadline, task_id='1'):
        """ Returns TaskToCompute deserialized. """
        compute_task_def                = message.ComputeTaskDef()
        compute_task_def['task_id']     = task_id
        compute_task_def['deadline']    = self._parse_iso_date_to_timestamp(deadline)
        with freeze_time(timestamp):
            task_to_compute = message.TaskToCompute(
                compute_task_def = compute_task_def,
            )
        return task_to_compute

    def _parse_iso_date_to_timestamp(self, date_string):  # pylint: disable=no-self-use
        return int(dateutil.parser.parse(date_string).timestamp())
