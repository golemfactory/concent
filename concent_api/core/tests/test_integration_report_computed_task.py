from base64                 import b64encode

from django.test            import override_settings
from django.test            import TestCase
from django.urls            import reverse
from freezegun              import freeze_time
from golem_messages         import dump
from golem_messages         import load
from golem_messages         import message
import dateutil.parser

from utils.testing_helpers  import generate_ecc_key_pair


(CONCENT_PRIVATE_KEY,   CONCENT_PUBLIC_KEY)   = generate_ecc_key_pair()
(PROVIDER_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY)  = generate_ecc_key_pair()
(REQUESTOR_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY) = generate_ecc_key_pair()


@override_settings(                             # pylint: disable=unused-variable
    CONCENT_PRIVATE_KEY = CONCENT_PRIVATE_KEY,  # pylint: disable=unused-variable
    CONCENT_PUBLIC_KEY  = CONCENT_PUBLIC_KEY,
    CONCENT_MESSAGING_TIME = 10,  # seconds
)
class ReportComputedTaskIntegrationTest(TestCase):
    def test_provider_forces_computed_task_report_and_concent_immediately_sends_rejection_due_to_exceeded_deadline(self):
        # Expected message exchange:
        # Provider -> Concent:     MessageForceReportComputedTask
        # Concent  -> Provider:    MessageRejectReportComputedTask

        # STEP 1: Provider forces computed task report via Concent. Concent rejects computed task immediately when deadline is exceeded

        task_to_compute = message.MessageTaskToCompute(
            timestamp   = int(dateutil.parser.parse("2017-12-01 10:00:00").timestamp()),
            task_id     = 1,
            deadline    = int(dateutil.parser.parse("2017-12-01 11:00:00").timestamp()),
        )
        serialized_task_to_compute = dump(task_to_compute, PROVIDER_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY)

        force_report_computed_task = message.MessageForceReportComputedTask(
            timestamp               = int(dateutil.parser.parse("2017-12-01 11:01:00").timestamp()),
            message_task_to_compute = serialized_task_to_compute,
        )
        serialized_force_report_computed_task = dump(force_report_computed_task, PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 11:01:00"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                           = serialized_force_report_computed_task,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response_1.status_code,  200)

        message_from_concent = load(response_1.content, PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        self.assertIsInstance(message_from_concent, message.MessageRejectReportComputedTask)
        self.assertEqual(message_from_concent.timestamp, int(dateutil.parser.parse("2017-12-01 11:01:00").timestamp()))
        self.assertEqual(message_from_concent.reason, "deadline-exceeded")
        self.assertEqual(message_from_concent.message_task_to_compute, serialized_task_to_compute)

    def test_provider_forces_computed_task_report_and_requestor_sends_acknowledgement(self):
        # Expected message exchange:
        # Provider  -> Concent:    MessageForceReportComputedTask
        # Concent   -> Requestor:  MessageForceReportComputedTask
        # Requestor -> Concent:    MessageAckReportComputedTask
        # Concent   -> Provider:   MessageAckReportComputedTask

        # STEP 1: Provider forces computed task report via Concent

        task_to_compute = message.MessageTaskToCompute(
            timestamp   = int(dateutil.parser.parse("2017-12-01 10:00:00").timestamp()),
            task_id     = 1,
            deadline    = int(dateutil.parser.parse("2017-12-01 11:00:00").timestamp()),
        )
        serialized_task_to_compute = dump(task_to_compute, PROVIDER_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY)

        force_report_computed_task = message.MessageForceReportComputedTask(
            timestamp               = int(dateutil.parser.parse("2017-12-01 10:59:00").timestamp()),
            message_task_to_compute = serialized_task_to_compute,
        )
        serialized_force_report_computed_task = dump(force_report_computed_task, PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 10:59:00"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                           = serialized_force_report_computed_task,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response_1.status_code,  202)
        self.assertEqual(len(response_1.content), 0)

        # STEP 2: Concent forces computed task report on the requestor

        with freeze_time("2017-12-01 11:00:05"):
            response_2 = self.client.post(
                reverse('core:receive'),
                data         = '',
                content_type = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response_2.status_code,  200)
        self.assertEqual(response_2.content, serialized_force_report_computed_task)

        # STEP 3: Requestor accepts computed task via Concent

        ack_report_computed_task = message.MessageAckReportComputedTask(
            timestamp               = int(dateutil.parser.parse("2017-12-01 11:00:05").timestamp()),
            message_task_to_compute = serialized_task_to_compute,
        )
        serialized_ack_report_computed_task = dump(ack_report_computed_task, REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 11:00:05"):
            response_3 = self.client.post(
                reverse('core:send'),
                data                           = serialized_ack_report_computed_task,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response_3.status_code,  202)
        self.assertEqual(len(response_3.content), 0)

        # STEP 4: Concent passes computed task acceptance to the provider

        with freeze_time("2017-12-01 11:00:15"):
            response_4 = self.client.post(
                reverse('core:receive'),
                data         = '',
                content_type = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response_4.status_code,  200)
        self.assertEqual(response_4.content, serialized_ack_report_computed_task)

    def test_provider_forces_computed_task_report_and_requestor_sends_rejection_due_to_failed_computation(self):
        # Expected message exchange:
        # Provider  -> Concent:    MessageForceReportComputedTask
        # Concent   -> Requestor:  MessageForceReportComputedTask
        # Requestor -> Concent:    MessageRejectReportComputedTask (failed computation)
        # Concent   -> Provider:   MessageRejectReportComputedTask

        # STEP 1: Provider forces computed task report via Concent

        task_to_compute = message.MessageTaskToCompute(
            timestamp   = int(dateutil.parser.parse("2017-12-01 10:00:00").timestamp()),
            task_id     = 1,
            deadline    = int(dateutil.parser.parse("2017-12-01 11:00:00").timestamp()),
        )
        serialized_task_to_compute = dump(task_to_compute, PROVIDER_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY)

        force_report_computed_task = message.MessageForceReportComputedTask(
            timestamp               = int(dateutil.parser.parse("2017-12-01 10:59:00").timestamp()),
            message_task_to_compute = serialized_task_to_compute,
        )
        serialized_force_report_computed_task = dump(force_report_computed_task, PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 10:59:00"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                           = serialized_force_report_computed_task,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response_1.status_code,  202)
        self.assertEqual(len(response_1.content), 0)

        # STEP 2: Concent forces computed task report on the requestor

        with freeze_time("2017-12-01 11:00:05"):
            response_2 = self.client.post(
                reverse('core:receive'),
                data         = '',
                content_type = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response_2.status_code,  200)
        self.assertEqual(response_2.content, serialized_force_report_computed_task)

        # STEP 3: Requestor rejects computed task due to CannotComputeTask or TaskFailure

        cannot_compute_task = message.MessageCannotComputeTask(
            timestamp = int(dateutil.parser.parse("2017-12-01 10:30:00").timestamp()),
            reason    = "cannot-compute-task",
            task_id   = 1,
        )
        serialized_cannot_compute_task = dump(cannot_compute_task, PROVIDER_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY)

        reject_report_computed_task = message.MessageRejectReportComputedTask(
            timestamp                   = int(dateutil.parser.parse("2017-12-01 11:00:05").timestamp()),
            reason                      = "computation-failed",
            message_cannot_compute_task = serialized_cannot_compute_task,
        )
        serialized_reject_report_computed_task = dump(reject_report_computed_task, REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 11:00:05"):
            response_3 = self.client.post(
                reverse('core:send'),
                data                           = serialized_reject_report_computed_task,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response_3.status_code,  202)
        self.assertEqual(len(response_3.content), 0)

        # STEP 4: Concent passes computed task rejection to the provider

        with freeze_time("2017-12-01 11:00:15"):
            response_4 = self.client.post(
                reverse('core:receive'),
                data         = '',
                content_type = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response_4.status_code,  200)
        self.assertEqual(response_4.content, serialized_reject_report_computed_task)

    def test_provider_forces_computed_task_report_and_requestor_sends_rejection_due_to_exceeded_deadline(self):
        # Expected message exchange:
        # Provider  -> Concent:    MessageForceReportComputedTask
        # Concent   -> Requestor:  MessageForceReportComputedTask
        # Requestor -> Concent:    MessageRejectReportComputedTask (deadline exceeded)
        # Concent   -> Provider:   MessageAckReportComputedTask
        # Concent   -> Requestor:  MessageVerdictReportComputedTask

        # STEP 1: Provider forces computed task report via Concent

        task_to_compute = message.MessageTaskToCompute(
            timestamp   = int(dateutil.parser.parse("2017-12-01 10:00:00").timestamp()),
            task_id     = 1,
            deadline    = int(dateutil.parser.parse("2017-12-01 11:00:00").timestamp()),
        )
        serialized_task_to_compute = dump(task_to_compute, PROVIDER_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY)

        force_report_computed_task = message.MessageForceReportComputedTask(
            timestamp               = int(dateutil.parser.parse("2017-12-01 10:59:00").timestamp()),
            message_task_to_compute = serialized_task_to_compute,
        )
        serialized_force_report_computed_task = dump(force_report_computed_task, PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 10:59:00"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                           = serialized_force_report_computed_task,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response_1.status_code,  202)
        self.assertEqual(len(response_1.content), 0)

        # STEP 2: Concent forces computed task report on the requestor

        with freeze_time("2017-12-01 11:00:05"):
            response_2 = self.client.post(
                reverse('core:receive'),
                data         = '',
                content_type = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response_2.status_code,  200)
        self.assertEqual(response_2.content, serialized_force_report_computed_task)

        # STEP 3: Requestor rejects computed task claiming that the deadline has been exceeded

        cannot_compute_task = message.MessageCannotComputeTask(
            timestamp = int(dateutil.parser.parse("2017-12-01 10:30:00").timestamp()),
            reason    = "deadline-exceeded",
            task_id   = 1,
        )
        serialized_cannot_compute_task = dump(cannot_compute_task, PROVIDER_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY)

        reject_report_computed_task = message.MessageRejectReportComputedTask(
            timestamp                   = int(dateutil.parser.parse("2017-12-01 11:00:05").timestamp()),
            reason                      = "deadline-exceeded",
            message_cannot_compute_task = serialized_cannot_compute_task,
        )
        serialized_reject_report_computed_task = dump(reject_report_computed_task, REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 11:00:05"):
            response_3 = self.client.post(
                reverse('core:send'),
                data                           = serialized_reject_report_computed_task,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response_3.status_code,  202)
        self.assertEqual(len(response_3.content), 0)

        # STEP 4: Concent overrides computed task rejection and sends acceptance message to the provider

        with freeze_time("2017-12-01 11:00:15"):
            response_4 = self.client.post(
                reverse('core:receive'),
                data         = '',
                content_type = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response_4.status_code,  200)

        serialized_message_from_concent_to_provider = response_4.content
        message_from_concent_to_provider            = load(serialized_message_from_concent_to_provider, PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        self.assertIsInstance(message_from_concent_to_provider, message.MessageAckReportComputedTask)
        self.assertGreaterEqual(message_from_concent_to_provider.timestamp, int(dateutil.parser.parse("2017-12-01 11:00:05").timestamp()))
        self.assertLessEqual(   message_from_concent_to_provider.timestamp, int(dateutil.parser.parse("2017-12-01 11:00:15").timestamp()))
        self.assertEqual(message_from_concent_to_provider.message_task_to_compute, serialized_task_to_compute)

        # STEP 5: Requestor receives computed task report verdict out of band due to an overridden decision

        with freeze_time("2017-12-01 11:00:15"):
            response_5 = self.client.post(
                reverse('core:receive_out_of_band'),
                data         = '',
                content_type = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response_5.status_code, 200)

        message_from_concent_to_requestor = load(response_5.content, REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        self.assertIsInstance(message_from_concent_to_requestor, message.MessageVerdictReportComputedTask)
        self.assertGreaterEqual(message_from_concent_to_requestor.timestamp, int(dateutil.parser.parse("2017-12-01 11:00:05").timestamp()))
        self.assertLessEqual(   message_from_concent_to_requestor.timestamp, int(dateutil.parser.parse("2017-12-01 11:00:15").timestamp()))
        self.assertEqual(message_from_concent_to_requestor.message_ack_report_computed_task, serialized_message_from_concent_to_provider)

    def test_provider_forces_computed_task_report_and_requestor_does_not_respond(self):
        # Expected message exchange:
        # Provider  -> Concent:    MessageForceReportComputedTask
        # Concent   -> Requestor:  MessageForceReportComputedTask
        # Requestor -> Concent:    no response
        # Concent   -> Provider:   MessageAckReportComputedTask
        # Concent   -> Requestor:  MessageVerdictReportComputedTask

        # STEP 1: Provider forces computed task report via Concent

        task_to_compute = message.MessageTaskToCompute(
            timestamp   = int(dateutil.parser.parse("2017-12-01 10:00:00").timestamp()),
            task_id     = 1,
            deadline    = int(dateutil.parser.parse("2017-12-01 11:00:00").timestamp()),
        )
        serialized_task_to_compute = dump(task_to_compute, PROVIDER_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY)

        force_report_computed_task = message.MessageForceReportComputedTask(
            timestamp               = int(dateutil.parser.parse("2017-12-01 10:59:00").timestamp()),
            message_task_to_compute = serialized_task_to_compute,
        )
        serialized_force_report_computed_task = dump(force_report_computed_task, PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 10:59:00"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                           = serialized_force_report_computed_task,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response_1.status_code,  202)
        self.assertEqual(len(response_1.content), 0)

        # STEP 2: Concent forces computed task report on the requestor

        with freeze_time("2017-12-01 11:00:05"):
            response_2 = self.client.post(
                reverse('core:receive'),
                data         = '',
                content_type = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response_2.status_code,  200)
        self.assertEqual(response_2.content, serialized_force_report_computed_task)

        # STEP 3: Concent accepts computed task due to lack of response from the requestor
        with freeze_time("2017-12-01 11:00:15"):
            response_3 = self.client.post(
                reverse('core:receive'),
                data         = '',
                content_type = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response_3.status_code,  200)

        message_from_concent_to_provider = load(response_3.content, PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY)
        self.assertIsInstance(message_from_concent_to_provider, message.MessageAckReportComputedTask)
        self.assertGreaterEqual(message_from_concent_to_provider.timestamp, int(dateutil.parser.parse("2017-12-01 11:00:05").timestamp()))
        self.assertLessEqual(   message_from_concent_to_provider.timestamp, int(dateutil.parser.parse("2017-12-01 11:00:15").timestamp()))
        self.assertEqual(message_from_concent_to_provider.message_task_to_compute, serialized_task_to_compute)

        # STEP 4: Requestor receives task computation report verdict out of band due to lack of response

        with freeze_time("2017-12-01 11:00:15"):
            response_4 = self.client.post(
                reverse('core:receive_out_of_band'),
                data         = '',
                content_type = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response_4.status_code, 200)

        message_from_concent_to_requestor       = load(
            response_4.content,
            REQUESTOR_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY
        )

        message_ack_from_concent_to_requestor   = load(
            message_from_concent_to_requestor.message_ack_report_computed_task,
            REQUESTOR_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY
        )

        self.assertIsInstance(message_from_concent_to_requestor, message.MessageVerdictReportComputedTask)
        self.assertGreaterEqual(message_from_concent_to_requestor.timestamp, int(dateutil.parser.parse("2017-12-01 11:00:05").timestamp()))
        self.assertLessEqual(   message_from_concent_to_requestor.timestamp, int(dateutil.parser.parse("2017-12-01 11:00:15").timestamp()))
        self.assertEqual(message_ack_from_concent_to_requestor, message_from_concent_to_provider)

    def test_provider_forces_computed_task_report_twice_and_concent_returns_400_error(self):
        """
        Tests if on provider ForceReportComputedTask message Concent will return HTTP 400 error
        if ForceReportComputedTask was already sent by this provider.

        Expected message exchange:
        Provider -> Concent:    ForceReportComputedTask
        Provider -> Concent:    ForceReportComputedTask
        Concent   -> Provider:  HTTP 400 error.
        """

        # STEP 1: Provider forces computed task report via Concent

        task_to_compute = message.MessageTaskToCompute(
            timestamp   = int(dateutil.parser.parse("2017-12-01 10:00:00").timestamp()),
            task_id     = 1,
            deadline    = int(dateutil.parser.parse("2017-12-01 11:00:00").timestamp()),
        )
        serialized_task_to_compute = dump(task_to_compute, PROVIDER_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY)

        force_report_computed_task = message.MessageForceReportComputedTask(
            timestamp               = int(dateutil.parser.parse("2017-12-01 10:59:00").timestamp()),
            message_task_to_compute = serialized_task_to_compute,
        )
        serialized_force_report_computed_task = dump(force_report_computed_task, PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 10:59:00"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                           = serialized_force_report_computed_task,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response_1.status_code,  202)
        self.assertEqual(len(response_1.content), 0)

        # STEP 2: Provider forces computed task report via Concent again
        with freeze_time("2017-12-01 10:59:00"):
            response_2 = self.client.post(
                reverse('core:send'),
                data                           = serialized_force_report_computed_task,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response_2.status_code, 400)
        self.assertEqual(response_2.json(), {"error": "MessageForceReportComputedTask is already being processed for this task."})

    def test_requestor_sends_ack_report_computed_task_but_provider_did_not_ask_for_it(self):
        """
        Tests if on request AckReportComputedTask message Concent will return HTTP 400 error
        if ForceReportComputedTask was not sent by provider.

        Expected message exchange:
        Requestor -> Concent:    AckReportComputedTask
        Concent   -> Requestor:  HTTP 400 error.
        """
        # STEP 1: Requestor accepts computed task via Concent

        task_to_compute = message.MessageTaskToCompute(
            timestamp   = int(dateutil.parser.parse("2017-12-01 10:00:00").timestamp()),
            task_id     = 1,
            deadline    = int(dateutil.parser.parse("2017-12-01 11:00:00").timestamp()),
        )
        serialized_task_to_compute = dump(task_to_compute, REQUESTOR_PRIVATE_KEY, PROVIDER_PUBLIC_KEY)

        ack_report_computed_task = message.MessageAckReportComputedTask(
            timestamp               = int(dateutil.parser.parse("2017-12-01 11:00:05").timestamp()),
            message_task_to_compute = serialized_task_to_compute,
        )
        serialized_ack_report_computed_task = dump(ack_report_computed_task, REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:send'),
                data                           = serialized_ack_report_computed_task,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response.status_code,  400)
        self.assertEqual(response.json(), {"error": "\'ForceReportComputedTask\' for this task has not been initiated yet. Can\'t accept your \'AckReportComputedTask\'."})

    def test_requestor_sends_reject_report_computed_task_but_provider_did_not_ask_for_it(self):
        """
        Tests if on request RejectReportComputedTask message Concent will return HTTP 400 error
        if ForceReportComputedTask was not sent by provider.

        Expected message exchange:
        Requestor -> Concent:    RejectReportComputedTask
        Concent   -> Requestor:  HTTP 400 error.
        """
        # STEP 1: Requestor accepts computed task via Concent

        cannot_compute_task = message.MessageCannotComputeTask(
            timestamp = int(dateutil.parser.parse("2017-12-01 10:30:00").timestamp()),
            reason    = "deadline-exceeded",
            task_id   = 1,
        )
        serialized_cannot_compute_task = dump(cannot_compute_task, PROVIDER_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY)

        reject_report_computed_task = message.MessageRejectReportComputedTask(
            timestamp                   = int(dateutil.parser.parse("2017-12-01 11:00:05").timestamp()),
            reason                      = "deadline-exceeded",
            message_cannot_compute_task = serialized_cannot_compute_task,
        )
        serialized_reject_report_computed_task = dump(reject_report_computed_task, REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:send'),
                data                           = serialized_reject_report_computed_task,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response.status_code,  400)
        self.assertEqual(response.json(), {"error": "\'ForceReportComputedTask\' for this task has not been initiated yet. Can\'t accept your \'RejectReportComputedTask\'."})

    def test_requestor_sends_ack_report_computed_task_and_then_sends_reject_report_computed_task(self):
        """
        Tests if on request RejectReportComputedTask message Concent will return HTTP 400 error
        if AckReportComputedTask was already sent by requestor.

        Expected message exchange:
        Provider  -> Concent:    ForceReportComputedTask
        Requestor -> Concent:    AckReportComputedTask
        Requestor -> Concent:    RejectReportComputedTask
        Concent   -> Requestor:  HTTP 400 error.
        """

        # STEP 1: Provider forces computed task report via Concent

        task_to_compute = message.MessageTaskToCompute(
            timestamp   = int(dateutil.parser.parse("2017-12-01 10:00:00").timestamp()),
            task_id     = 1,
            deadline    = int(dateutil.parser.parse("2017-12-01 11:00:00").timestamp()),
        )
        serialized_task_to_compute = dump(task_to_compute, PROVIDER_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY)

        force_report_computed_task = message.MessageForceReportComputedTask(
            timestamp               = int(dateutil.parser.parse("2017-12-01 10:59:00").timestamp()),
            message_task_to_compute = serialized_task_to_compute,
        )
        serialized_force_report_computed_task = dump(force_report_computed_task, PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 10:59:00"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                           = serialized_force_report_computed_task,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response_1.status_code,  202)
        self.assertEqual(len(response_1.content), 0)

        # STEP 2: Concent forces computed task report on the requestor

        with freeze_time("2017-12-01 11:00:05"):
            response_2 = self.client.post(
                reverse('core:receive'),
                data         = '',
                content_type = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response_2.status_code,  200)
        self.assertEqual(response_2.content, serialized_force_report_computed_task)

        # STEP 3: Requestor accepts computed task via Concent

        task_to_compute = message.MessageTaskToCompute(
            timestamp   = int(dateutil.parser.parse("2017-12-01 10:00:00").timestamp()),
            task_id     = 1,
            deadline    = int(dateutil.parser.parse("2017-12-01 11:00:00").timestamp()),
        )
        serialized_task_to_compute = dump(task_to_compute, REQUESTOR_PRIVATE_KEY, PROVIDER_PUBLIC_KEY)

        ack_report_computed_task = message.MessageAckReportComputedTask(
            timestamp               = int(dateutil.parser.parse("2017-12-01 11:00:05").timestamp()),
            message_task_to_compute = serialized_task_to_compute,
        )
        serialized_ack_report_computed_task = dump(ack_report_computed_task, REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 11:00:05"):
            response_3 = self.client.post(
                reverse('core:send'),
                data                           = serialized_ack_report_computed_task,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response_3.status_code,  202)

        # STEP 4: Requestor rejects computed task via Concent

        cannot_compute_task = message.MessageCannotComputeTask(
            timestamp = int(dateutil.parser.parse("2017-12-01 10:30:00").timestamp()),
            reason    = "some-reason",
            task_id   = 1,
        )
        serialized_cannot_compute_task = dump(cannot_compute_task, PROVIDER_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY)

        reject_report_computed_task = message.MessageRejectReportComputedTask(
            timestamp                   = int(dateutil.parser.parse("2017-12-01 11:00:05").timestamp()),
            reason                      = "some-reason",
            message_cannot_compute_task = serialized_cannot_compute_task,
        )
        serialized_reject_report_computed_task = dump(reject_report_computed_task, REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 11:00:05"):
            response_4 = self.client.post(
                reverse('core:send'),
                data                           = serialized_reject_report_computed_task,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response_4.status_code,  400)
        self.assertEqual(response_4.json(), {'error': 'Received RejectReportComputedTask but AckReportComputedTask or another RejectReportComputedTask for this task has already been submitted.'})

    def test_requestor_sends_reject_report_computed_task_and_then_sends_ack_report_computed_task(self):
        """
        Tests if on request AckReportComputedTask message Concent will return HTTP 400 error
        if RejectReportComputedTask was already sent by requestor.

        Expected message exchange:
        Provider  -> Concent:    ForceReportComputedTask
        Requestor -> Concent:    RejectReportComputedTask
        Requestor -> Concent:    AckReportComputedTask
        Concent   -> Requestor:  HTTP 400 error.
        """

        # STEP 1: Provider forces computed task report via Concent

        task_to_compute = message.MessageTaskToCompute(
            timestamp   = int(dateutil.parser.parse("2017-12-01 10:00:00").timestamp()),
            task_id     = 1,
            deadline    = int(dateutil.parser.parse("2017-12-01 11:00:00").timestamp()),
        )
        serialized_task_to_compute = dump(task_to_compute, PROVIDER_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY)

        force_report_computed_task = message.MessageForceReportComputedTask(
            timestamp               = int(dateutil.parser.parse("2017-12-01 10:59:00").timestamp()),
            message_task_to_compute = serialized_task_to_compute,
        )
        serialized_force_report_computed_task = dump(force_report_computed_task, PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 10:59:00"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                           = serialized_force_report_computed_task,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response_1.status_code,  202)
        self.assertEqual(len(response_1.content), 0)

        # STEP 2: Concent forces computed task report on the requestor

        with freeze_time("2017-12-01 11:00:05"):
            response_2 = self.client.post(
                reverse('core:receive'),
                data         = '',
                content_type = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response_2.status_code,  200)
        self.assertEqual(response_2.content, serialized_force_report_computed_task)

        # STEP 3: Requestor rejects computed task via Concent

        cannot_compute_task = message.MessageCannotComputeTask(
            timestamp = int(dateutil.parser.parse("2017-12-01 10:30:00").timestamp()),
            reason    = "deadline-exceeded",
            task_id   = 1,
        )
        serialized_cannot_compute_task = dump(cannot_compute_task, PROVIDER_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY)

        reject_report_computed_task = message.MessageRejectReportComputedTask(
            timestamp                   = int(dateutil.parser.parse("2017-12-01 11:00:05").timestamp()),
            reason                      = "deadline-exceeded",
            message_cannot_compute_task = serialized_cannot_compute_task,
        )
        serialized_reject_report_computed_task = dump(reject_report_computed_task, REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 11:00:05"):
            response_3 = self.client.post(
                reverse('core:send'),
                data                           = serialized_reject_report_computed_task,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response_3.status_code,  202)

        # STEP 4: Requestor accepts computed task via Concent

        task_to_compute = message.MessageTaskToCompute(
            timestamp   = int(dateutil.parser.parse("2017-12-01 10:00:00").timestamp()),
            task_id     = 1,
            deadline    = int(dateutil.parser.parse("2017-12-01 11:00:00").timestamp()),
        )
        serialized_task_to_compute = dump(task_to_compute, REQUESTOR_PRIVATE_KEY, PROVIDER_PUBLIC_KEY)

        ack_report_computed_task = message.MessageAckReportComputedTask(
            timestamp               = int(dateutil.parser.parse("2017-12-01 11:00:05").timestamp()),
            message_task_to_compute = serialized_task_to_compute,
        )
        serialized_ack_report_computed_task = dump(ack_report_computed_task, REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 11:00:05"):
            response_4 = self.client.post(
                reverse('core:send'),
                data                           = serialized_ack_report_computed_task,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response_4.status_code,  400)
        self.assertEqual(response_4.json(), {'error': 'Received AckReportComputedTask but RejectReportComputedTask. or another AckReportComputedTask for this task has already been submitted.'})

    def test_requestor_sends_ack_report_computed_task_after_deadline_passed(self):
        """
        Tests if on request AckReportComputedTask message Concent will return HTTP 400 error
        if deadline has passed.

        Expected message exchange:
        Provider  -> Concent:    ForceReportComputedTask
        Requestor -> Concent:    AckReportComputedTask
        Concent   -> Requestor:  HTTP 400 error.
        """

        # STEP 1: Provider forces computed task report via Concent

        task_to_compute = message.MessageTaskToCompute(
            timestamp   = int(dateutil.parser.parse("2017-12-01 10:00:00").timestamp()),
            task_id     = 1,
            deadline    = int(dateutil.parser.parse("2017-12-01 11:00:00").timestamp()),
        )
        serialized_task_to_compute = dump(task_to_compute, PROVIDER_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY)

        force_report_computed_task = message.MessageForceReportComputedTask(
            timestamp               = int(dateutil.parser.parse("2017-12-01 10:59:00").timestamp()),
            message_task_to_compute = serialized_task_to_compute,
        )
        serialized_force_report_computed_task = dump(force_report_computed_task, PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 10:59:00"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                           = serialized_force_report_computed_task,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response_1.status_code,  202)
        self.assertEqual(len(response_1.content), 0)

        # STEP 2: Concent forces computed task report on the requestor

        with freeze_time("2017-12-01 11:00:05"):
            response_2 = self.client.post(
                reverse('core:receive'),
                data         = '',
                content_type = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response_2.status_code,  200)
        self.assertEqual(response_2.content, serialized_force_report_computed_task)

        # STEP 3: Requestor accepts computed task via Concent after deadline

        task_to_compute = message.MessageTaskToCompute(
            timestamp   = int(dateutil.parser.parse("2017-12-01 10:00:00").timestamp()),
            task_id     = 1,
            deadline    = int(dateutil.parser.parse("2017-12-01 11:00:00").timestamp()),
        )
        serialized_task_to_compute = dump(task_to_compute, REQUESTOR_PRIVATE_KEY, PROVIDER_PUBLIC_KEY)

        ack_report_computed_task = message.MessageAckReportComputedTask(
            timestamp               = int(dateutil.parser.parse("2017-12-01 11:00:15").timestamp()),
            message_task_to_compute = serialized_task_to_compute,
        )
        serialized_ack_report_computed_task = dump(ack_report_computed_task, REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 11:00:15"):
            response_3 = self.client.post(
                reverse('core:send'),
                data                           = serialized_ack_report_computed_task,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response_3.status_code,  400)
        self.assertEqual(response_3.json(), {"error": "Time to acknowledge this task is already over."})

    def test_requestor_sends_reject_report_computed_task_after_deadline_passed(self):
        """
        Tests if on request RejectReportComputedTask message Concent will return HTTP 400 error
        if deadline has passed.

        Expected message exchange:
        Provider  -> Concent:    ForceReportComputedTask
        Requestor -> Concent:    RejectReportComputedTask
        Concent   -> Requestor:  HTTP 400 error.
        """

        # STEP 1: Provider forces computed task report via Concent

        task_to_compute = message.MessageTaskToCompute(
            timestamp   = int(dateutil.parser.parse("2017-12-01 10:00:00").timestamp()),
            task_id     = 1,
            deadline    = int(dateutil.parser.parse("2017-12-01 11:00:00").timestamp()),
        )
        serialized_task_to_compute = dump(task_to_compute, PROVIDER_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY)

        force_report_computed_task = message.MessageForceReportComputedTask(
            timestamp               = int(dateutil.parser.parse("2017-12-01 10:59:00").timestamp()),
            message_task_to_compute = serialized_task_to_compute,
        )
        serialized_force_report_computed_task = dump(force_report_computed_task, PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 10:59:00"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                           = serialized_force_report_computed_task,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response_1.status_code,  202)
        self.assertEqual(len(response_1.content), 0)

        # STEP 2: Concent forces computed task report on the requestor

        with freeze_time("2017-12-01 11:00:05"):
            response_2 = self.client.post(
                reverse('core:receive'),
                data         = '',
                content_type = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response_2.status_code,  200)
        self.assertEqual(response_2.content, serialized_force_report_computed_task)

        # STEP 3: Requestor rejects computed task via Concent after deadline

        cannot_compute_task = message.MessageCannotComputeTask(
            timestamp = int(dateutil.parser.parse("2017-12-01 10:30:00").timestamp()),
            reason    = "some-reason",
            task_id   = 1,
        )
        serialized_cannot_compute_task = dump(cannot_compute_task, PROVIDER_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY)

        reject_report_computed_task = message.MessageRejectReportComputedTask(
            timestamp                   = int(dateutil.parser.parse("2017-12-01 11:00:15").timestamp()),
            reason                      = "some-reason",
            message_cannot_compute_task = serialized_cannot_compute_task,
        )
        serialized_reject_report_computed_task = dump(reject_report_computed_task, REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 11:00:15"):
            response_3 = self.client.post(
                reverse('core:send'),
                data                           = serialized_reject_report_computed_task,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response_3.status_code,  400)
        self.assertEqual(response_3.json(), {"error": "Time to acknowledge this task is already over."})

    def test_provider_forces_computed_task_report_missing_key_returns_400_error(self):
        """
        Tests if on provider ForceReportComputedTask message Concent will return HTTP 400 error
        if no key was provided in header.

        Expected message exchange:
        Provider -> Concent:    ForceReportComputedTask
        Concent  -> Provider:  HTTP 400 error.
        """

        # STEP 1: Provider forces computed task report via Concent

        task_to_compute = message.MessageTaskToCompute(
            timestamp   = int(dateutil.parser.parse("2017-12-01 10:00:00").timestamp()),
            task_id     = 1,
            deadline    = int(dateutil.parser.parse("2017-12-01 11:00:00").timestamp()),
        )
        serialized_task_to_compute = dump(task_to_compute, PROVIDER_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY)

        force_report_computed_task = message.MessageForceReportComputedTask(
            timestamp               = int(dateutil.parser.parse("2017-12-01 10:59:00").timestamp()),
            message_task_to_compute = serialized_task_to_compute,
        )
        serialized_force_report_computed_task = dump(force_report_computed_task, PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 10:59:00"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                           = serialized_force_report_computed_task,
                content_type                   = 'application/octet-stream',
            )

        self.assertEqual(response_1.status_code,  400)
        self.assertEqual(response_1.json(), {"error": "Concent-Client-Public-Key HTTP header is missing on the request."})

    def test_provider_forces_computed_task_report_bad_key_returns_400_error(self):
        """
        Tests if on provider ForceReportComputedTask message Concent will return HTTP 400 error
        if bad key was provided in header.

        Expected message exchange:
        Provider -> Concent:    ForceReportComputedTask
        Concent  -> Provider:  HTTP 400 error.
        """

        # STEP 1: Provider forces computed task report via Concent

        task_to_compute = message.MessageTaskToCompute(
            timestamp   = int(dateutil.parser.parse("2017-12-01 10:00:00").timestamp()),
            task_id     = 1,
            deadline    = int(dateutil.parser.parse("2017-12-01 11:00:00").timestamp()),
        )
        serialized_task_to_compute = dump(task_to_compute, PROVIDER_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY)

        force_report_computed_task = message.MessageForceReportComputedTask(
            timestamp               = int(dateutil.parser.parse("2017-12-01 10:59:00").timestamp()),
            message_task_to_compute = serialized_task_to_compute,
        )
        serialized_force_report_computed_task = dump(force_report_computed_task, PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 10:59:00"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                           = serialized_force_report_computed_task,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = 'bad__key' * 11,
            )

        self.assertEqual(response_1.status_code,  400)
        self.assertEqual(response_1.json(), {"error": "The value in the Concent-Client-Public-Key HTTP is not a valid base64-encoded value."})

    def test_provider_forces_computed_task_report_truncated_key_returns_400_error(self):
        """
        Tests if on provider ForceReportComputedTask message Concent will return HTTP 400 error
        if truncated key was provided in header.

        Expected message exchange:
        Provider -> Concent:   ForceReportComputedTask
        Concent  -> Provider:  HTTP 400 error.
        """

        # STEP 1: Provider forces computed task report via Concent

        task_to_compute = message.MessageTaskToCompute(
            timestamp = int(dateutil.parser.parse("2017-12-01 10:00:00").timestamp()),
            task_id   = 1,
            deadline  = int(dateutil.parser.parse("2017-12-01 11:00:00").timestamp()),
        )
        serialized_task_to_compute = dump(task_to_compute, PROVIDER_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY)

        force_report_computed_task = message.MessageForceReportComputedTask(
            timestamp               = int(dateutil.parser.parse("2017-12-01 10:59:00").timestamp()),
            message_task_to_compute = serialized_task_to_compute,
        )
        serialized_force_report_computed_task = dump(force_report_computed_task, PROVIDER_PRIVATE_KEY,
                                                     CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 10:59:00"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                           = serialized_force_report_computed_task,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY)[:32].decode('ascii'),
            )

        self.assertEqual(response_1.status_code, 400)
        self.assertEqual(response_1.json(), {"error": "The length in the Concent-Client-Public-Key HTTP is wrong."})

    def test_provider_forces_computed_task_report_empty_key_returns_400_error(self):
        """
        Tests if on provider ForceReportComputedTask message Concent will return HTTP 400 error
        if empty key was provided in header.

        Expected message exchange:
        Provider -> Concent:   ForceReportComputedTask
        Concent  -> Provider:  HTTP 400 error.
        """

        # STEP 1: Provider forces computed task report via Concent

        task_to_compute = message.MessageTaskToCompute(
            timestamp = int(dateutil.parser.parse("2017-12-01 10:00:00").timestamp()),
            task_id   = 1,
            deadline  = int(dateutil.parser.parse("2017-12-01 11:00:00").timestamp()),
        )
        serialized_task_to_compute = dump(task_to_compute, PROVIDER_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY)

        force_report_computed_task = message.MessageForceReportComputedTask(
            timestamp               = int(dateutil.parser.parse("2017-12-01 10:59:00").timestamp()),
            message_task_to_compute = serialized_task_to_compute,
        )
        serialized_force_report_computed_task = dump(force_report_computed_task, PROVIDER_PRIVATE_KEY,
                                                     CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 10:59:00"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                           = serialized_force_report_computed_task,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = '',
            )

        self.assertEqual(response_1.status_code, 400)
        self.assertEqual(response_1.json(), {"error": "Concent-Client-Public-Key HTTP header is missing on the request."})

    def test_requestor_sends_ack_report_computed_task_with_message_cannot_compute_task(self):
        """
        Tests if on request AckReportComputedTask message Concent will return HTTP 400 error
        if message contains CannotComputeTask instead of TaskToCompute.

        Expected message exchange:
        Requestor -> Concent:    AckReportComputedTask
        Concent   -> Requestor:  HTTP 400 error.
        """
        # STEP 1: Requestor accepts computed task via Concent

        cannot_compute_task = message.MessageCannotComputeTask(
            timestamp   = int(dateutil.parser.parse("2017-12-01 10:00:00").timestamp()),
            task_id     = 1,
            deadline    = int(dateutil.parser.parse("2017-12-01 11:00:00").timestamp()),
        )
        serialized_cannot_compute_task = dump(cannot_compute_task, REQUESTOR_PRIVATE_KEY, PROVIDER_PUBLIC_KEY)

        ack_report_computed_task = message.MessageAckReportComputedTask(
            timestamp               = int(dateutil.parser.parse("2017-12-01 11:00:05").timestamp()),
            message_task_to_compute = serialized_cannot_compute_task,
        )
        serialized_ack_report_computed_task = dump(ack_report_computed_task, REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:send'),
                data                           = serialized_ack_report_computed_task,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response.status_code,  400)
        self.assertEqual(response.json(), {"error": "Expected MessageTaskToCompute."})

    def test_requestor_sends_reject_report_computed_task_with_message_task_to_compute(self):
        """
        Tests if on request RejectReportComputedTask message Concent will return HTTP 400 error
        if message contains TaskToCompute instead of CannotComputeTask .

        Expected message exchange:
        Requestor -> Concent:    RejectReportComputedTask
        Concent   -> Requestor:  HTTP 400 error.
        """
        # STEP 1: Requestor accepts computed task via Concent

        task_to_compute = message.MessageTaskToCompute(
            timestamp = int(dateutil.parser.parse("2017-12-01 10:30:00").timestamp()),
            task_id   = 1,
        )
        serialized_task_to_compute = dump(task_to_compute, PROVIDER_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY)

        reject_report_computed_task = message.MessageRejectReportComputedTask(
            timestamp                   = int(dateutil.parser.parse("2017-12-01 11:00:05").timestamp()),
            reason                      = "deadline-exceeded",
            message_cannot_compute_task = serialized_task_to_compute,
        )
        serialized_reject_report_computed_task = dump(reject_report_computed_task, REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:send'),
                data                           = serialized_reject_report_computed_task,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response.status_code,  400)
        self.assertEqual(response.json(), {"error": "Expected MessageCannotComputeTask or MessageTaskFailure."})

    def test_provider_sends_force_report_computed_task_with_cutted_message(self):
        """
        Tests if on request ForceReportComputedTask message Concent will return HTTP 400 error
        if message is malformed.

        Expected message exchange:
        Provider  -> Concent:    ForceReportComputedTask
        Concent   -> Provider:  HTTP 400 error.
        """

        # STEP 1: Provider forces computed task report via Concent

        task_to_compute = message.MessageTaskToCompute(
            timestamp   = int(dateutil.parser.parse("2017-12-01 10:00:00").timestamp()),
            task_id     = 1,
            deadline    = int(dateutil.parser.parse("2017-12-01 11:00:00").timestamp()),
        )
        serialized_task_to_compute = dump(task_to_compute, PROVIDER_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY)

        force_report_computed_task = message.MessageForceReportComputedTask(
            timestamp               = int(dateutil.parser.parse("2017-12-01 10:59:00").timestamp()),
            message_task_to_compute = serialized_task_to_compute,
        )
        serialized_force_report_computed_task = dump(force_report_computed_task, PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 10:59:00"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                           = serialized_force_report_computed_task[:50],
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response_1.status_code,  400)
        self.assertEqual(response_1.json(), {'error': 'Wrong type of message or public key'})

    def test_provider_sends_force_report_computed_task_with_malformed_message(self):
        """
        Tests if on request ForceReportComputedTask message Concent will return HTTP 400 error
        if message is malformed.

        Expected message exchange:
        Provider  -> Concent:    ForceReportComputedTask
        Concent   -> Provider:  HTTP 400 error.
        """

        # STEP 1: Provider forces computed task report via Concent

        task_to_compute = message.MessageTaskToCompute(
            timestamp   = int(dateutil.parser.parse("2017-12-01 10:00:00").timestamp()),
            task_id     = 1,
            deadline    = int(dateutil.parser.parse("2017-12-01 11:00:00").timestamp()),
        )
        serialized_task_to_compute = dump(task_to_compute, PROVIDER_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY)

        force_report_computed_task = message.MessageForceReportComputedTask(
            timestamp               = int(dateutil.parser.parse("2017-12-01 10:59:00").timestamp()),
            message_task_to_compute = serialized_task_to_compute,
        )
        serialized_force_report_computed_task = dump(force_report_computed_task, PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY)
        serialized_force_report_computed_task = serialized_force_report_computed_task[:120] + b'\x00' + serialized_force_report_computed_task[120:]

        with freeze_time("2017-12-01 10:59:00"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                           = serialized_force_report_computed_task,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response_1.status_code,  400)
        self.assertEqual(response_1.json(), {'error': 'Wrong type of message or public key'})

    def test_provider_forces_computed_task_report_and_tries_to_receive_after_deadline(self):
        """
        Tests if on request ForceReportComputedTask message Concent will return HTTP 204 response
        if Provider tries to receive MessageAckReportComputedTask after deadline.

        # Expected message exchange:
        # Provider  -> Concent:    MessageForceReportComputedTask
        # Concent   -> Requestor:  MessageForceReportComputedTask
        # Requestor -> Concent:    MessageAckReportComputedTask
        # Concent   -> Provider:   MessageAckReportComputedTask
        """

        # STEP 1: Provider forces computed task report via Concent

        task_to_compute = message.MessageTaskToCompute(
            timestamp   = int(dateutil.parser.parse("2017-12-01 10:00:00").timestamp()),
            task_id     = 1,
            deadline    = int(dateutil.parser.parse("2017-12-01 11:00:00").timestamp()),
        )
        serialized_task_to_compute = dump(task_to_compute, PROVIDER_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY)

        force_report_computed_task = message.MessageForceReportComputedTask(
            timestamp               = int(dateutil.parser.parse("2017-12-01 10:59:00").timestamp()),
            message_task_to_compute = serialized_task_to_compute,
        )
        serialized_force_report_computed_task = dump(force_report_computed_task, PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 10:59:00"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                           = serialized_force_report_computed_task,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response_1.status_code,  202)
        self.assertEqual(len(response_1.content), 0)

        # STEP 2: Concent forces computed task report on the requestor

        with freeze_time("2017-12-01 11:00:05"):
            response_2 = self.client.post(
                reverse('core:receive'),
                data         = '',
                content_type = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response_2.status_code,  200)
        self.assertEqual(response_2.content, serialized_force_report_computed_task)

        # STEP 3: Requestor accepts computed task via Concent

        ack_report_computed_task = message.MessageAckReportComputedTask(
            timestamp               = int(dateutil.parser.parse("2017-12-01 11:00:05").timestamp()),
            message_task_to_compute = serialized_task_to_compute,
        )
        serialized_ack_report_computed_task = dump(ack_report_computed_task, REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 11:00:05"):
            response_3 = self.client.post(
                reverse('core:send'),
                data                           = serialized_ack_report_computed_task,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response_3.status_code,  202)
        self.assertEqual(len(response_3.content), 0)

        # STEP 4: Concent passes computed task acceptance to the provider

        with freeze_time("2017-12-01 11:00:30"):
            response_4 = self.client.post(
                reverse('core:receive'),
                data         = '',
                content_type = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response_4.status_code,  204)
        self.assertEqual(len(response_4.content), 0)

    def test_provider_forces_computed_task_report_and_tries_to_receive_twice(self):
        """
        Tests if on request ForceReportComputedTask message Concent will return HTTP 204 response
        if Provider tries to receive MessageAckReportComputedTask twice.

        # Expected message exchange:
        # Provider  -> Concent:    MessageForceReportComputedTask
        # Concent   -> Requestor:  MessageForceReportComputedTask
        # Requestor -> Concent:    MessageAckReportComputedTask
        # Concent   -> Provider:   MessageAckReportComputedTask
        # Concent   -> Provider:   MessageAckReportComputedTask
        """

        # STEP 1: Provider forces computed task report via Concent

        task_to_compute = message.MessageTaskToCompute(
            timestamp   = int(dateutil.parser.parse("2017-12-01 10:00:00").timestamp()),
            task_id     = 1,
            deadline    = int(dateutil.parser.parse("2017-12-01 11:00:00").timestamp()),
        )
        serialized_task_to_compute = dump(task_to_compute, PROVIDER_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY)

        force_report_computed_task = message.MessageForceReportComputedTask(
            timestamp               = int(dateutil.parser.parse("2017-12-01 10:59:00").timestamp()),
            message_task_to_compute = serialized_task_to_compute,
        )
        serialized_force_report_computed_task = dump(force_report_computed_task, PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 10:59:00"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                           = serialized_force_report_computed_task,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response_1.status_code,  202)
        self.assertEqual(len(response_1.content), 0)

        # STEP 2: Concent forces computed task report on the requestor

        with freeze_time("2017-12-01 11:00:05"):
            response_2 = self.client.post(
                reverse('core:receive'),
                data         = '',
                content_type = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response_2.status_code,  200)
        self.assertEqual(response_2.content, serialized_force_report_computed_task)

        # STEP 3: Requestor accepts computed task via Concent

        ack_report_computed_task = message.MessageAckReportComputedTask(
            timestamp               = int(dateutil.parser.parse("2017-12-01 11:00:05").timestamp()),
            message_task_to_compute = serialized_task_to_compute,
        )
        serialized_ack_report_computed_task = dump(ack_report_computed_task, REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 11:00:05"):
            response_3 = self.client.post(
                reverse('core:send'),
                data                           = serialized_ack_report_computed_task,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response_3.status_code,  202)
        self.assertEqual(len(response_3.content), 0)

        # STEP 4: Concent passes computed task acceptance to the provider

        with freeze_time("2017-12-01 11:00:15"):
            response_4 = self.client.post(
                reverse('core:receive'),
                data         = '',
                content_type = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response_4.status_code,  200)
        self.assertEqual(response_4.content, serialized_ack_report_computed_task)

        # STEP 5: Concent passes computed task acceptance to the provider again

        with freeze_time("2017-12-01 12:00:00"):
            response_5 = self.client.post(
                reverse('core:receive'),
                data         = '',
                content_type = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response_5.status_code,  204)
        self.assertEqual(len(response_5.content), 0)
