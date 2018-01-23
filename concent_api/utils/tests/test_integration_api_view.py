from base64 import b64encode

from django.test                    import override_settings
from django.test                    import TestCase
from django.urls                    import reverse
from freezegun                      import freeze_time
import dateutil.parser

from golem_messages.shortcuts       import dump
from golem_messages.shortcuts       import load
from golem_messages                 import message

from utils.testing_helpers  import generate_ecc_key_pair


(CONCENT_PRIVATE_KEY,   CONCENT_PUBLIC_KEY)   = generate_ecc_key_pair()
(PROVIDER_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY)  = generate_ecc_key_pair()
(REQUESTOR_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY) = generate_ecc_key_pair()


@override_settings(
    CONCENT_PRIVATE_KEY    = CONCENT_PRIVATE_KEY,
    CONCENT_PUBLIC_KEY     = CONCENT_PUBLIC_KEY,
    CONCENT_MESSAGING_TIME = 10,  # seconds
)
class ApiViewsIntegrationTest(TestCase):

    def test_provider_forces_computed_task_report_missing_key_returns_400_error(self):
        """
        Tests if on provider ForceReportComputedTask message Concent will return HTTP 400 error
        if no key was provided in header.

        Expected message exchange:
        Provider -> Concent:    ForceReportComputedTask
        Concent  -> Provider:  HTTP 400 error.
        """

        # STEP 1: Provider forces computed task report via Concent

        task_to_compute = message.TaskToCompute(
            timestamp   = int(dateutil.parser.parse("2017-12-01 10:00:00").timestamp()),
        )

        task_to_compute.compute_task_def = message.ComputeTaskDef()
        task_to_compute.compute_task_def['task_id']     = 1
        task_to_compute.compute_task_def['deadline']    = int(dateutil.parser.parse("2017-12-01 11:00:00").timestamp())

        serialized_task_to_compute      = dump(task_to_compute,             PROVIDER_PRIVATE_KEY,   REQUESTOR_PUBLIC_KEY)
        deserialized_task_to_compute    = load(serialized_task_to_compute,  REQUESTOR_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY, check_time = False)

        force_report_computed_task = message.ForceReportComputedTask(
            timestamp               = int(dateutil.parser.parse("2017-12-01 10:59:00").timestamp()),
        )
        force_report_computed_task.task_to_compute = deserialized_task_to_compute

        serialized_force_report_computed_task = dump(force_report_computed_task, PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 10:59:00"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                           = serialized_force_report_computed_task,
                content_type                   = 'application/octet-stream',
            )

        self.assertEqual(response_1.status_code,  400)
        self.assertIn('error', response_1.json().keys())

    def test_provider_forces_computed_task_report_bad_key_returns_400_error(self):
        """
        Tests if on provider ForceReportComputedTask message Concent will return HTTP 400 error
        if bad key was provided in header.

        Expected message exchange:
        Provider -> Concent:    ForceReportComputedTask
        Concent  -> Provider:  HTTP 400 error.
        """

        # STEP 1: Provider forces computed task report via Concent

        task_to_compute = message.TaskToCompute(
            timestamp   = int(dateutil.parser.parse("2017-12-01 10:00:00").timestamp()),
        )

        task_to_compute.compute_task_def = message.ComputeTaskDef()
        task_to_compute.compute_task_def['task_id'] = 1
        task_to_compute.compute_task_def['deadline'] = int(dateutil.parser.parse("2017-12-01 11:00:00").timestamp())

        serialized_task_to_compute      = dump(task_to_compute,             PROVIDER_PRIVATE_KEY,   REQUESTOR_PUBLIC_KEY)
        deserialized_task_to_compute    = load(serialized_task_to_compute,  REQUESTOR_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY, check_time = False)

        force_report_computed_task = message.ForceReportComputedTask(
            timestamp               = int(dateutil.parser.parse("2017-12-01 10:59:00").timestamp()),
        )
        force_report_computed_task.task_to_compute = deserialized_task_to_compute
        serialized_force_report_computed_task = dump(force_report_computed_task, PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 10:59:00"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                           = serialized_force_report_computed_task,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = 'bad__key' * 11,
            )

        self.assertEqual(response_1.status_code,  400)
        self.assertIn('error', response_1.json().keys())

    def test_provider_forces_computed_task_report_truncated_key_returns_400_error(self):
        """
        Tests if on provider ForceReportComputedTask message Concent will return HTTP 400 error
        if truncated key was provided in header.

        Expected message exchange:
        Provider -> Concent:   ForceReportComputedTask
        Concent  -> Provider:  HTTP 400 error.
        """

        # STEP 1: Provider forces computed task report via Concent

        task_to_compute = message.TaskToCompute(
            timestamp = int(dateutil.parser.parse("2017-12-01 10:00:00").timestamp()),
        )

        task_to_compute.compute_task_def = message.ComputeTaskDef()
        task_to_compute.compute_task_def['task_id']     = 1
        task_to_compute.compute_task_def['deadline']    = int(dateutil.parser.parse("2017-12-01 11:00:00").timestamp())

        serialized_task_to_compute      = dump(task_to_compute,             PROVIDER_PRIVATE_KEY,   REQUESTOR_PUBLIC_KEY)
        deserialized_task_to_compute    = load(serialized_task_to_compute,  REQUESTOR_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY, check_time = False)

        force_report_computed_task = message.ForceReportComputedTask(
            timestamp               = int(dateutil.parser.parse("2017-12-01 10:59:00").timestamp()),
        )

        force_report_computed_task.task_to_compute = deserialized_task_to_compute

        serialized_force_report_computed_task = dump(force_report_computed_task, PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 10:59:00"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                           = serialized_force_report_computed_task,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY)[:32].decode('ascii'),
            )

        self.assertEqual(response_1.status_code, 400)
        self.assertIn('error', response_1.json().keys())

    def test_provider_forces_computed_task_report_empty_key_returns_400_error(self):
        """
        Tests if on provider ForceReportComputedTask message Concent will return HTTP 400 error
        if empty key was provided in header.

        Expected message exchange:
        Provider -> Concent:   ForceReportComputedTask
        Concent  -> Provider:  HTTP 400 error.
        """

        # STEP 1: Provider forces computed task report via Concent

        task_to_compute = message.TaskToCompute(
            timestamp = int(dateutil.parser.parse("2017-12-01 10:00:00").timestamp()),
        )

        task_to_compute.compute_task_def = message.ComputeTaskDef()
        task_to_compute.compute_task_def['task_id']     = 1
        task_to_compute.compute_task_def['deadline']    = int(dateutil.parser.parse("2017-12-01 11:00:00").timestamp())

        serialized_task_to_compute      = dump(task_to_compute,             PROVIDER_PRIVATE_KEY,   REQUESTOR_PUBLIC_KEY)
        deserialized_task_to_compute    = load(serialized_task_to_compute,  REQUESTOR_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY, check_time = False)

        force_report_computed_task = message.ForceReportComputedTask(
            timestamp               = int(dateutil.parser.parse("2017-12-01 10:59:00").timestamp()),
        )
        force_report_computed_task.task_to_compute = deserialized_task_to_compute

        serialized_force_report_computed_task = dump(force_report_computed_task, PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 10:59:00"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                           = serialized_force_report_computed_task,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = '',
            )

        self.assertEqual(response_1.status_code, 400)
        self.assertIn('error', response_1.json().keys())
