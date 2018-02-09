from base64 import b64encode
import datetime

from django.test                    import override_settings
from django.test                    import TestCase
from django.urls                    import reverse
from django.utils                   import timezone
from freezegun                      import freeze_time
import dateutil.parser

from golem_messages.shortcuts       import dump
from golem_messages.shortcuts       import load
from golem_messages                 import message

from core.models            import Message
from core.models            import ReceiveOutOfBandStatus
from core.models            import ReceiveStatus
from utils.testing_helpers  import generate_ecc_key_pair


(CONCENT_PRIVATE_KEY,   CONCENT_PUBLIC_KEY)   = generate_ecc_key_pair()
(PROVIDER_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY)  = generate_ecc_key_pair()
(REQUESTOR_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY) = generate_ecc_key_pair()


@override_settings(
    CONCENT_PRIVATE_KEY    = CONCENT_PRIVATE_KEY,
    CONCENT_PUBLIC_KEY     = CONCENT_PUBLIC_KEY,
    CONCENT_MESSAGING_TIME = 10,  # seconds
)
class ReportComputedTaskIntegrationTest(TestCase):
    def test_provider_forces_computed_task_report_and_concent_immediately_sends_rejection_due_to_exceeded_deadline(self):
        # Expected message exchange:
        # Provider -> Concent:     MessageForceReportComputedTask
        # Concent  -> Provider:    MessageRejectReportComputedTask

        # STEP 1: Provider forces computed task report via Concent. Concent rejects computed task immediately when deadline is exceeded

        compute_task_def = message.ComputeTaskDef()
        compute_task_def['task_id']     = '1'
        compute_task_def['deadline']    = int(dateutil.parser.parse("2017-12-01 11:00:00").timestamp())
        with freeze_time("2017-12-01 10:00:00"):
            task_to_compute = message.TaskToCompute(
                compute_task_def = compute_task_def
            )

        serialized_task_to_compute      = dump(task_to_compute,             PROVIDER_PRIVATE_KEY,   REQUESTOR_PUBLIC_KEY)
        deserialized_task_to_compute    = load(serialized_task_to_compute,  REQUESTOR_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY, check_time = False)

        with freeze_time("2017-12-01 11:01:00"):
            force_report_computed_task = message.ForceReportComputedTask()
        force_report_computed_task.task_to_compute = deserialized_task_to_compute

        serialized_force_report_computed_task = dump(force_report_computed_task, PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 11:01:00"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_report_computed_task,
                content_type                        = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY      = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
                HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response_1.status_code,  200)

        message_from_concent = load(response_1.content, PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY, check_time = False)

        self.assertIsInstance(message_from_concent, message.RejectReportComputedTask)
        self.assertEqual(message_from_concent.timestamp, int(dateutil.parser.parse("2017-12-01 11:01:00").timestamp()))
        self.assertEqual(message_from_concent.reason, message.RejectReportComputedTask.REASON.TaskTimeLimitExceeded)
        self.assertEqual(message_from_concent.task_to_compute, deserialized_task_to_compute)

    def test_provider_forces_computed_task_report_and_requestor_sends_acknowledgement(self):
        # Expected message exchange:
        # Provider  -> Concent:    MessageForceReportComputedTask
        # Concent   -> Requestor:  MessageForceReportComputedTask
        # Requestor -> Concent:    MessageAckReportComputedTask
        # Concent   -> Provider:   MessageAckReportComputedTask

        # STEP 1: Provider forces computed task report via Concent

        compute_task_def = message.ComputeTaskDef()
        compute_task_def['task_id'] = '1'
        compute_task_def['deadline'] = int(dateutil.parser.parse("2017-12-1 11:00:00").timestamp())
        with freeze_time("2017-12-01 10:00:00"):
            task_to_compute = message.TaskToCompute(
                compute_task_def = compute_task_def
            )

        serialized_task_to_compute      = dump(task_to_compute,             PROVIDER_PRIVATE_KEY,   REQUESTOR_PUBLIC_KEY)
        deserialized_task_to_compute    = load(serialized_task_to_compute,  REQUESTOR_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY, check_time = False)

        with freeze_time("2017-12-01 10:59:00"):
            force_report_computed_task = message.ForceReportComputedTask()
        force_report_computed_task.task_to_compute = deserialized_task_to_compute

        serialized_force_report_computed_task = dump(force_report_computed_task, PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 10:59:00"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_report_computed_task,
                content_type                        = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY      = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
                HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
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

        force_report_computed_task_from_view = load(
            response_2.content,
            REQUESTOR_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY,
            check_time = False,
        )

        self.assertEqual(response_2.status_code,  200)
        self.assertEqual(force_report_computed_task_from_view.timestamp, force_report_computed_task.timestamp)

        # STEP 3: Requestor accepts computed task via Concent

        with freeze_time("2017-12-01 11:00:05"):
            ack_report_computed_task = message.AckReportComputedTask()
        ack_report_computed_task.task_to_compute = deserialized_task_to_compute

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

        ack_report_computed_task_from_view = load(
            response_4.content,
            PROVIDER_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY,
            check_time = False,
        )

        self.assertEqual(response_4.status_code,  200)
        self.assertEqual(ack_report_computed_task_from_view.timestamp, ack_report_computed_task.timestamp)

    def test_provider_forces_computed_task_report_and_requestor_sends_rejection_due_to_failed_computation(self):
        # Expected message exchange:
        # Provider  -> Concent:    MessageForceReportComputedTask
        # Concent   -> Requestor:  MessageForceReportComputedTask
        # Requestor -> Concent:    MessageRejectReportComputedTask (failed computation)
        # Concent   -> Provider:   MessageRejectReportComputedTask

        # STEP 1: Provider forces computed task report via Concent

        compute_task_def = message.ComputeTaskDef()
        compute_task_def['task_id']     = '1'
        compute_task_def['deadline']    = int(dateutil.parser.parse("2017-12-01 11:00:00").timestamp())
        with freeze_time("2017-12-01 10:00:00"):
            task_to_compute = message.TaskToCompute(
                compute_task_def = compute_task_def
            )

        serialized_task_to_compute      = dump(task_to_compute,             PROVIDER_PRIVATE_KEY,   REQUESTOR_PUBLIC_KEY)
        deserialized_task_to_compute    = load(serialized_task_to_compute,  REQUESTOR_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY, check_time = False)

        with freeze_time("2017-12-01 10:59:00"):
            force_report_computed_task = message.ForceReportComputedTask()

        force_report_computed_task.task_to_compute = deserialized_task_to_compute
        serialized_force_report_computed_task = dump(force_report_computed_task, PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 10:59:00"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_report_computed_task,
                content_type                        = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY      = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
                HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response_1.status_code,  202)
        self.assertEqual(len(response_1.content), 0)

        # STEP 2: Concent forces computed task report on the requestor

        with freeze_time("2017-12-01 11:00:05"):
            response_2 = self.client.post(
                reverse('core:receive'),
                data         = '',
                content_type = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY   = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        force_report_computed_task_from_view = load(
            response_2.content,
            REQUESTOR_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY,
            check_time = False,
        )

        self.assertEqual(response_2.status_code,  200)
        self.assertEqual(force_report_computed_task_from_view.timestamp, force_report_computed_task.timestamp)
        self.assertEqual(force_report_computed_task_from_view.task_to_compute.timestamp, force_report_computed_task.task_to_compute.timestamp)

        # STEP 3: Requestor rejects computed task due to CannotComputeTask or TaskFailure

        with freeze_time("2017-12-01 10:30:00"):
            cannot_compute_task = message.CannotComputeTask()
        cannot_compute_task.task_to_compute = message.TaskToCompute()
        cannot_compute_task.task_to_compute.compute_task_def = message.ComputeTaskDef()
        cannot_compute_task.task_to_compute.compute_task_def['task_id'] = '1'
        cannot_compute_task.reason = message.CannotComputeTask.REASON.WrongKey

        serialized_cannot_compute_task      = dump(cannot_compute_task,             PROVIDER_PRIVATE_KEY,   REQUESTOR_PUBLIC_KEY)
        deserialized_cannot_compute_task    = load(serialized_cannot_compute_task,  REQUESTOR_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY, check_time=False)

        with freeze_time("2017-12-01 11:00:05"):
            reject_report_computed_task = message.RejectReportComputedTask()
        reject_report_computed_task.cannot_compute_task = deserialized_cannot_compute_task

        serialized_reject_report_computed_task = dump(reject_report_computed_task, REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 11:00:05"):
            response_3 = self.client.post(
                reverse('core:send'),
                data                            = serialized_reject_report_computed_task,
                content_type                    = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY  = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response_3.status_code,  202)
        self.assertEqual(len(response_3.content), 0)

        # STEP 4: Concent passes computed task rejection to the provider

        with freeze_time("2017-12-01 11:00:15"):
            response_4 = self.client.post(
                reverse('core:receive'),
                data         = '',
                content_type = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY      = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            )

        reject_report_computed_task_from_view = load(
            response_4.content,
            PROVIDER_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY,
            check_time = False,
        )

        self.assertEqual(response_4.status_code,  200)
        self.assertEqual(reject_report_computed_task_from_view.timestamp, reject_report_computed_task.timestamp)
        self.assertEqual(reject_report_computed_task_from_view.cannot_compute_task.timestamp, reject_report_computed_task.cannot_compute_task.timestamp)
        self.assertEqual(reject_report_computed_task_from_view.cannot_compute_task.task_to_compute.timestamp, reject_report_computed_task.cannot_compute_task.task_to_compute.timestamp)

    def test_provider_forces_computed_task_report_and_requestor_sends_rejection_due_to_exceeded_deadline(self):
        # Expected message exchange:
        # Provider  -> Concent:    MessageForceReportComputedTask
        # Concent   -> Requestor:  MessageForceReportComputedTask
        # Requestor -> Concent:    MessageRejectReportComputedTask (deadline exceeded)
        # Concent   -> Provider:   MessageAckReportComputedTask
        # Concent   -> Requestor:  MessageVerdictReportComputedTask

        # STEP 1: Provider forces computed task report via Concent

        compute_task_def = message.ComputeTaskDef()
        compute_task_def['task_id']     = '1'
        compute_task_def['deadline']    = int(dateutil.parser.parse("2017-12-01 11:00:00").timestamp())
        with freeze_time("2017-12-01 10:00:00"):
            task_to_compute = message.TaskToCompute(
                compute_task_def = compute_task_def
            )

        serialized_task_to_compute      = dump(task_to_compute,             PROVIDER_PRIVATE_KEY,   REQUESTOR_PUBLIC_KEY)
        deserialized_task_to_compute    = load(serialized_task_to_compute,  REQUESTOR_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY, check_time = False)

        with freeze_time("2017-12-01 10:59:00"):
            force_report_computed_task = message.ForceReportComputedTask()

        force_report_computed_task.task_to_compute = deserialized_task_to_compute

        serialized_force_report_computed_task = dump(force_report_computed_task, PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 10:59:00"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_report_computed_task,
                content_type                        = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY      = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
                HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
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

        force_report_computed_task_from_view = load(
            response_2.content,
            REQUESTOR_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY,
            check_time = False,
        )

        self.assertEqual(response_2.status_code,  200)
        self.assertEqual(force_report_computed_task_from_view.timestamp, force_report_computed_task.timestamp)

        # STEP 3: Requestor rejects computed task claiming that the deadline has been exceeded

        with freeze_time("2017-12-01 10:30:00"):
            cannot_compute_task = message.CannotComputeTask()
        cannot_compute_task.task_to_compute = message.TaskToCompute()
        cannot_compute_task.task_to_compute.compute_task_def = message.ComputeTaskDef()
        cannot_compute_task.task_to_compute.compute_task_def['task_id'] = '1'

        cannot_compute_task.reason = message.CannotComputeTask.REASON.WrongCTD

        serialized_cannot_compute_task      = dump(cannot_compute_task,             PROVIDER_PRIVATE_KEY,   REQUESTOR_PUBLIC_KEY)
        deserialized_cannot_compute_task    = load(serialized_cannot_compute_task,  REQUESTOR_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY, check_time=False)

        with freeze_time("2017-12-01 11:00:05"):
            reject_report_computed_task = message.RejectReportComputedTask()
        reject_report_computed_task.reason              = message.RejectReportComputedTask.REASON.TaskTimeLimitExceeded
        reject_report_computed_task.cannot_compute_task = deserialized_cannot_compute_task

        serialized_reject_report_computed_task = dump(reject_report_computed_task, REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 11:00:05"):
            response_3 = self.client.post(
                reverse('core:send'),
                data                           = serialized_reject_report_computed_task,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response_3.status_code,                    202)
        self.assertEqual(len(response_3.content),                   0)
        self.assertEqual(ReceiveStatus.objects.last().message.type, message.RejectReportComputedTask.TYPE)

        # STEP 4: Concent overrides computed task rejection and sends acceptance message to the provider

        with freeze_time("2017-12-01 11:00:15"):
            response_4 = self.client.post(
                reverse('core:receive'),
                data         = '',
                content_type = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY      = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response_4.status_code,  200)

        serialized_message_from_concent_to_provider = response_4.content
        message_from_concent_to_provider            = load(
            serialized_message_from_concent_to_provider,
            PROVIDER_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY,
            check_time=False
        )

        self.assertIsInstance(message_from_concent_to_provider, message.AckReportComputedTask)
        self.assertGreaterEqual(message_from_concent_to_provider.timestamp, int(dateutil.parser.parse("2017-12-01 11:00:05").timestamp()))
        self.assertLessEqual(   message_from_concent_to_provider.timestamp, int(dateutil.parser.parse("2017-12-01 11:00:15").timestamp()))
        self.assertEqual(message_from_concent_to_provider.task_to_compute, deserialized_task_to_compute)

        # STEP 5: Requestor receives computed task report verdict out of band due to an overridden decision

        with freeze_time("2017-12-01 11:00:15"):
            response_5 = self.client.post(
                reverse('core:receive_out_of_band'),
                data         = '',
                content_type = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response_5.status_code, 200)

        message_from_concent_to_requestor = load(
            response_5.content,
            REQUESTOR_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY,
            check_time=False
        )
        self.assertIsInstance(message_from_concent_to_requestor, message.VerdictReportComputedTask)
        self.assertGreaterEqual(message_from_concent_to_requestor.timestamp, int(dateutil.parser.parse("2017-12-01 11:00:05").timestamp()))
        self.assertLessEqual(   message_from_concent_to_requestor.timestamp, int(dateutil.parser.parse("2017-12-01 11:00:15").timestamp()))
        self.assertEqual(message_from_concent_to_requestor.ack_report_computed_task, message_from_concent_to_provider)

    def test_provider_forces_computed_task_report_and_requestor_does_not_respond(self):
        # Expected message exchange:
        # Provider  -> Concent:    MessageForceReportComputedTask
        # Concent   -> Requestor:  MessageForceReportComputedTask
        # Requestor -> Concent:    no response
        # Concent   -> Provider:   MessageAckReportComputedTask
        # Concent   -> Requestor:  MessageVerdictReportComputedTask

        # STEP 1: Provider forces computed task report via Concent

        compute_task_def = message.ComputeTaskDef()
        compute_task_def['task_id']     = '1'
        compute_task_def['deadline']    = int(dateutil.parser.parse("2017-12-01 11:00:00").timestamp())
        with freeze_time("2017-12-01 10:00:00"):
            task_to_compute = message.TaskToCompute(
                compute_task_def = compute_task_def
            )

        serialized_task_to_compute      = dump(task_to_compute,             PROVIDER_PRIVATE_KEY,   REQUESTOR_PUBLIC_KEY)
        deserialized_task_to_compute    = load(serialized_task_to_compute,  REQUESTOR_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY, check_time = False)

        with freeze_time("2017-12-01 10:59:00"):
            force_report_computed_task = message.ForceReportComputedTask()
        force_report_computed_task.task_to_compute = deserialized_task_to_compute

        serialized_force_report_computed_task = dump(force_report_computed_task, PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 10:59:00"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_report_computed_task,
                content_type                        = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY      = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
                HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
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
        force_report_computed_task_from_view = load(
            response_2.content,
            REQUESTOR_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY,
            check_time = False,
        )

        self.assertEqual(response_2.status_code,  200)
        self.assertEqual(force_report_computed_task_from_view.timestamp, force_report_computed_task.timestamp)
        self.assertEqual(force_report_computed_task_from_view.task_to_compute.timestamp, force_report_computed_task.task_to_compute.timestamp)

        # STEP 3: Concent accepts computed task due to lack of response from the requestor

        with freeze_time("2017-12-01 11:00:15"):
            response_3 = self.client.post(
                reverse('core:receive'),
                data         = '',
                content_type = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response_3.status_code,  200)

        message_from_concent_to_provider = load(response_3.content, PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY, check_time=False)

        self.assertIsInstance(message_from_concent_to_provider, message.AckReportComputedTask)
        self.assertGreaterEqual(message_from_concent_to_provider.timestamp, int(dateutil.parser.parse("2017-12-01 11:00:05").timestamp()))
        self.assertLessEqual(   message_from_concent_to_provider.timestamp, int(dateutil.parser.parse("2017-12-01 11:00:15").timestamp()))
        self.assertEqual(message_from_concent_to_provider.task_to_compute, deserialized_task_to_compute)

        # STEP 4: Requestor receives task computation report verdict out of band due to lack of response

        with freeze_time("2017-12-01 11:00:15"):
            response_4 = self.client.post(
                reverse('core:receive_out_of_band'),
                data         = '',
                content_type = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response_4.status_code, 200)

        message_from_concent_to_requestor = load(response_4.content, REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY, check_time=False)

        self.assertIsInstance(message_from_concent_to_requestor, message.VerdictReportComputedTask)
        self.assertGreaterEqual(message_from_concent_to_requestor.timestamp, int(dateutil.parser.parse("2017-12-01 11:00:05").timestamp()))
        self.assertLessEqual(   message_from_concent_to_requestor.timestamp, int(dateutil.parser.parse("2017-12-01 11:00:15").timestamp()))
        self.assertEqual(message_from_concent_to_requestor.ack_report_computed_task, message_from_concent_to_provider)

    def test_provider_forces_computed_task_report_twice_and_concent_returns_400_error(self):
        """
        Tests if on provider ForceReportComputedTask message Concent will return HTTP 400 error
        if ForceReportComputedTask was already sent by this provider.

        Expected message exchange:
        Provider -> Concent:    ForceReportComputedTask
        Concent   -> Provider:  HTTP 400 error.
        """

        # STEP 1: Provider forces computed task report via Concent

        with freeze_time("2017-12-01 10:00:00"):
            task_to_compute = message.TaskToCompute()

        task_to_compute.compute_task_def = message.ComputeTaskDef()
        task_to_compute.compute_task_def['task_id']     = '1'
        task_to_compute.compute_task_def['deadline']    = int(dateutil.parser.parse("2017-12-01 11:00:00").timestamp())

        serialized_task_to_compute      = dump(task_to_compute,             PROVIDER_PRIVATE_KEY,   REQUESTOR_PUBLIC_KEY)
        deserialized_task_to_compute    = load(serialized_task_to_compute,  REQUESTOR_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY, check_time = False)

        with freeze_time("2017-12-01 10:59:00"):
            force_report_computed_task = message.ForceReportComputedTask()
        force_report_computed_task.task_to_compute = deserialized_task_to_compute

        serialized_force_report_computed_task = dump(force_report_computed_task, PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 10:59:00"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_report_computed_task,
                content_type                        = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY      = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
                HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response_1.status_code,  202)
        self.assertEqual(len(response_1.content), 0)

        # STEP 2: Provider forces computed task report via Concent again
        with freeze_time("2017-12-01 10:59:00"):
            response_2 = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_report_computed_task,
                content_type                        = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY      = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
                HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response_2.status_code, 400)
        self.assertIn('error', response_2.json().keys())

    def test_requestor_sends_ack_report_computed_task_but_provider_did_not_ask_for_it(self):
        """
        Tests if on request AckReportComputedTask message Concent will return HTTP 400 error
        if ForceReportComputedTask was not sent by provider.

        Expected message exchange:
        Requestor -> Concent:    AckReportComputedTask
        Concent   -> Requestor:  HTTP 400 error.
        """
        # STEP 1: Requestor accepts computed task via Concent

        with freeze_time("2017-12-01 10:00:00"):
            task_to_compute = message.TaskToCompute()

        task_to_compute.compute_task_def = message.ComputeTaskDef()
        task_to_compute.compute_task_def['task_id']     = '1'
        task_to_compute.compute_task_def['deadline']    = int(dateutil.parser.parse("2017-12-01 11:00:00").timestamp())

        serialized_task_to_compute      = dump(task_to_compute,             REQUESTOR_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY)
        deserialized_task_to_compute    = load(serialized_task_to_compute,  PROVIDER_PRIVATE_KEY,   REQUESTOR_PUBLIC_KEY, check_time = False)

        with freeze_time("2017-12-01 11:00:05"):
            ack_report_computed_task = message.AckReportComputedTask()
        ack_report_computed_task.task_to_compute = deserialized_task_to_compute

        serialized_ack_report_computed_task = dump(ack_report_computed_task, REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:send'),
                data                           = serialized_ack_report_computed_task,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response.status_code,  400)
        self.assertIn('error', response.json().keys())

    def test_requestor_sends_reject_report_computed_task_but_provider_did_not_ask_for_it(self):
        """
        Tests if on request RejectReportComputedTask message Concent will return HTTP 400 error
        if ForceReportComputedTask was not sent by provider.

        Expected message exchange:
        Requestor -> Concent:    RejectReportComputedTask
        Concent   -> Requestor:  HTTP 400 error.
        """
        # STEP 1: Requestor accepts computed task via Concent

        with freeze_time("2017-12-01 10:30:00"):
            cannot_compute_task = message.CannotComputeTask()

        cannot_compute_task.reason = message.CannotComputeTask.REASON.WrongCTD
        cannot_compute_task.task_to_compute = message.TaskToCompute()
        cannot_compute_task.task_to_compute.compute_task_def = message.ComputeTaskDef()
        cannot_compute_task.task_to_compute.compute_task_def['task_id'] = '1'
        serialized_cannot_compute_task      = dump(cannot_compute_task,                 PROVIDER_PRIVATE_KEY,   REQUESTOR_PUBLIC_KEY)
        deserialized_cannot_compute_task    = load(serialized_cannot_compute_task,      REQUESTOR_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY, check_time = False)

        with freeze_time("2017-12-01 11:00:05"):
            reject_report_computed_task = message.RejectReportComputedTask()
        reject_report_computed_task.reason = message.RejectReportComputedTask.REASON.TaskTimeLimitExceeded
        reject_report_computed_task.cannot_compute_task = deserialized_cannot_compute_task
        serialized_reject_report_computed_task = dump(reject_report_computed_task, REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:send'),
                data                           = serialized_reject_report_computed_task,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response.status_code,  400)
        self.assertIn('error', response.json().keys())

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

        with freeze_time("2017-12-01 10:00:00"):
            task_to_compute = message.TaskToCompute()

        task_to_compute.compute_task_def = message.ComputeTaskDef()
        task_to_compute.compute_task_def['task_id']     = '1'
        task_to_compute.compute_task_def['deadline']    = int(dateutil.parser.parse("2017-12-01 11:00:00").timestamp())

        serialized_task_to_compute      = dump(task_to_compute,             PROVIDER_PRIVATE_KEY,   REQUESTOR_PUBLIC_KEY)
        deserialized_task_to_compute    = load(serialized_task_to_compute,  REQUESTOR_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY, check_time = False)

        with freeze_time("2017-12-01 10:59:00"):
            force_report_computed_task = message.ForceReportComputedTask()
        force_report_computed_task.task_to_compute = deserialized_task_to_compute
        serialized_force_report_computed_task = dump(force_report_computed_task, PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 10:59:00"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_report_computed_task,
                content_type                        = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY      = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
                HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
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

        force_report_computed_task_from_view = load(
            response_2.content,
            REQUESTOR_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY,
            check_time = False
        )

        self.assertEqual(response_2.status_code,  200)
        self.assertEqual(force_report_computed_task_from_view.task_to_compute.compute_task_def['task_id'], force_report_computed_task.task_to_compute.compute_task_def['task_id'])
        self.assertEqual(force_report_computed_task_from_view.timestamp, force_report_computed_task.timestamp)

        # STEP 3: Requestor accepts computed task via Concent

        with freeze_time("2017-12-01 10:00:00"):
            task_to_compute = message.TaskToCompute()

        task_to_compute.compute_task_def = message.ComputeTaskDef()
        task_to_compute.compute_task_def['task_id']     = '1'
        task_to_compute.compute_task_def['deadline']    = int(dateutil.parser.parse("2017-12-01 11:00:00").timestamp())

        serialized_task_to_compute      = dump(task_to_compute,             REQUESTOR_PRIVATE_KEY, PROVIDER_PUBLIC_KEY)
        deserialized_task_to_compute    = load(serialized_task_to_compute,  PROVIDER_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY, check_time = False)

        with freeze_time("2017-12-01 11:00:05"):
            ack_report_computed_task = message.AckReportComputedTask()
        ack_report_computed_task.task_to_compute = deserialized_task_to_compute

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

        with freeze_time("2017-12-01 10:30:00"):
            cannot_compute_task = message.CannotComputeTask()

        cannot_compute_task.task_to_compute = message.TaskToCompute()
        cannot_compute_task.task_to_compute.compute_task_def = message.ComputeTaskDef()
        cannot_compute_task.task_to_compute.compute_task_def['task_id'] = '1'
        cannot_compute_task.reason = message.CannotComputeTask.REASON.WrongEnvironment

        serialized_cannot_compute_task      = dump(cannot_compute_task,             PROVIDER_PRIVATE_KEY,   REQUESTOR_PUBLIC_KEY)
        deserialized_cannot_compute_task    = load(serialized_cannot_compute_task,  REQUESTOR_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY, check_time = False)

        with freeze_time("2017-12-01 11:00:05"):
            reject_report_computed_task = message.RejectReportComputedTask()
        reject_report_computed_task.reason = reject_report_computed_task.REASON.TaskTimeLimitExceeded
        reject_report_computed_task.cannot_compute_task = deserialized_cannot_compute_task

        serialized_reject_report_computed_task = dump(reject_report_computed_task, REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 11:00:05"):
            response_4 = self.client.post(
                reverse('core:send'),
                data                           = serialized_reject_report_computed_task,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response_4.status_code,  400)
        self.assertIn('error', response_4.json().keys())

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

        with freeze_time("2017-12-01 10:00:00"):
            task_to_compute = message.TaskToCompute()
        task_to_compute.compute_task_def = message.ComputeTaskDef()
        task_to_compute.compute_task_def['task_id']     = '1'
        task_to_compute.compute_task_def['deadline']    = int(dateutil.parser.parse("2017-12-01 11:00:00").timestamp())

        serialized_task_to_compute = dump(task_to_compute, PROVIDER_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY)
        deserialized_task_to_compute = load(serialized_task_to_compute, REQUESTOR_PRIVATE_KEY, PROVIDER_PUBLIC_KEY, check_time = False)

        with freeze_time("2017-12-01 10:59:00"):
            force_report_computed_task = message.ForceReportComputedTask()
        force_report_computed_task.task_to_compute = deserialized_task_to_compute
        serialized_force_report_computed_task = dump(force_report_computed_task, PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 10:59:00"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_report_computed_task,
                content_type                        = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY      = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
                HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
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
        force_report_computed_task_from_view = load(
            response_2.content,
            REQUESTOR_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY,
            check_time = False
        )

        self.assertEqual(response_2.status_code,  200)
        self.assertEqual(force_report_computed_task_from_view.task_to_compute, force_report_computed_task.task_to_compute)

        # STEP 3: Requestor rejects computed task via Concent

        with freeze_time("2017-12-01 10:30:00"):
            cannot_compute_task = message.CannotComputeTask()
        cannot_compute_task.task_to_compute = message.TaskToCompute()
        cannot_compute_task.task_to_compute.compute_task_def = message.ComputeTaskDef()
        cannot_compute_task.task_to_compute.compute_task_def['task_id'] = '1'
        cannot_compute_task.reason = message.CannotComputeTask.REASON.WrongCTD

        serialized_cannot_compute_task      = dump(cannot_compute_task,             PROVIDER_PRIVATE_KEY,   REQUESTOR_PUBLIC_KEY)
        deserialized_cannot_compute_task    = load(serialized_cannot_compute_task,  REQUESTOR_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY, check_time = False)

        with freeze_time("2017-12-01 11:00:05"):
            reject_report_computed_task = message.RejectReportComputedTask()
        reject_report_computed_task.cannot_compute_task = deserialized_cannot_compute_task
        reject_report_computed_task.reason = reject_report_computed_task.REASON.TaskTimeLimitExceeded

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

        with freeze_time("2017-12-01 10:00:00"):
            task_to_compute = message.TaskToCompute()

        task_to_compute.compute_task_def = message.ComputeTaskDef()
        task_to_compute.compute_task_def['task_id']     = '1'
        task_to_compute.compute_task_def['deadline']    = int(dateutil.parser.parse("2017-12-01 11:00:00").timestamp())

        serialized_task_to_compute      = dump(task_to_compute,             REQUESTOR_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY)
        deserialized_task_to_compute    = load(serialized_task_to_compute,  PROVIDER_PRIVATE_KEY,   REQUESTOR_PUBLIC_KEY, check_time = False)

        with freeze_time("2017-12-01 11:00:05"):
            ack_report_computed_task = message.AckReportComputedTask()
        ack_report_computed_task.task_to_compute = deserialized_task_to_compute

        serialized_ack_report_computed_task = dump(ack_report_computed_task, REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 11:00:05"):
            response_4 = self.client.post(
                reverse('core:send'),
                data                           = serialized_ack_report_computed_task,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response_4.status_code,  400)
        self.assertIn('error', response_4.json().keys())

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

        with freeze_time("2017-12-01 10:00:00"):
            task_to_compute = message.TaskToCompute()

        task_to_compute.compute_task_def = message.ComputeTaskDef()
        task_to_compute.compute_task_def['task_id']     = '1'
        task_to_compute.compute_task_def['deadline']    = int(dateutil.parser.parse("2017-12-01 11:00:00").timestamp())

        serialized_task_to_compute      = dump(task_to_compute,             PROVIDER_PRIVATE_KEY,   REQUESTOR_PUBLIC_KEY)
        deserialized_task_to_compute    = load(serialized_task_to_compute,  REQUESTOR_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY, check_time = False)

        with freeze_time("2017-12-01 10:59:00"):
            force_report_computed_task = message.ForceReportComputedTask()
        force_report_computed_task.task_to_compute = deserialized_task_to_compute
        serialized_force_report_computed_task = dump(force_report_computed_task, PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 10:59:00"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_report_computed_task,
                content_type                        = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY      = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
                HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
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

        force_report_computed_task_from_view = load(
            response_2.content,
            REQUESTOR_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY,
            check_time = False
        )
        self.assertEqual(response_2.status_code,  200)
        self.assertEqual(force_report_computed_task_from_view.timestamp, force_report_computed_task.timestamp)
        self.assertEqual(force_report_computed_task_from_view.task_to_compute.timestamp, force_report_computed_task.task_to_compute.timestamp)

        # STEP 3: Requestor accepts computed task via Concent after deadline

        with freeze_time("2017-12-01 10:00:00"):
            task_to_compute = message.TaskToCompute()

        task_to_compute.compute_task_def = message.ComputeTaskDef()
        task_to_compute.compute_task_def['task_id']     = '1'
        task_to_compute.compute_task_def['deadline']    = int(dateutil.parser.parse("2017-12-01 11:00:00").timestamp())

        serialized_task_to_compute      = dump(task_to_compute,             REQUESTOR_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY)
        deserialized_task_to_compute    = load(serialized_task_to_compute,  PROVIDER_PRIVATE_KEY,   REQUESTOR_PUBLIC_KEY, check_time = False)

        with freeze_time("2017-12-01 11:00:15"):
            ack_report_computed_task = message.AckReportComputedTask()
        ack_report_computed_task.task_to_compute = deserialized_task_to_compute

        serialized_ack_report_computed_task = dump(ack_report_computed_task, REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 11:00:15"):
            response_3 = self.client.post(
                reverse('core:send'),
                data                           = serialized_ack_report_computed_task,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response_3.status_code,  400)
        self.assertIn('error', response_3.json().keys())

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

        with freeze_time("2017-12-01 10:00:00"):
            task_to_compute = message.TaskToCompute()

        task_to_compute.compute_task_def = message.ComputeTaskDef()
        task_to_compute.compute_task_def['task_id']     = '1'
        task_to_compute.compute_task_def['deadline']    = int(dateutil.parser.parse("2017-12-01 11:00:00").timestamp())

        serialized_task_to_compute      = dump(task_to_compute,             PROVIDER_PRIVATE_KEY,   REQUESTOR_PUBLIC_KEY)
        deserialized_task_to_compute    = load(serialized_task_to_compute,  REQUESTOR_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY, check_time = False)

        with freeze_time("2017-12-01 10:59:00"):
            force_report_computed_task = message.ForceReportComputedTask()
        force_report_computed_task.task_to_compute = deserialized_task_to_compute

        serialized_force_report_computed_task = dump(force_report_computed_task, PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 10:59:00"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_report_computed_task,
                content_type                        = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY      = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
                HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
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

        force_report_computed_task_from_view = load(
            response_2.content,
            REQUESTOR_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY,
            check_time = False
        )
        self.assertEqual(response_2.status_code,  200)
        self.assertEqual(force_report_computed_task_from_view.timestamp, force_report_computed_task.timestamp)

        # STEP 3: Requestor rejects computed task via Concent after deadline

        with freeze_time("2017-12-01 10:30:00"):
            cannot_compute_task = message.CannotComputeTask()
        cannot_compute_task.task_to_compute                             = message.TaskToCompute()
        cannot_compute_task.task_to_compute.compute_task_def            = message.ComputeTaskDef()
        cannot_compute_task.task_to_compute.compute_task_def['task_id'] = '1'
        cannot_compute_task.reason                                      = message.CannotComputeTask.REASON.WrongKey

        serialized_cannot_compute_task      = dump(cannot_compute_task,             PROVIDER_PRIVATE_KEY,   REQUESTOR_PUBLIC_KEY)
        deserialized_cannot_compute_task    = load(serialized_cannot_compute_task,  REQUESTOR_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY, check_time = False)

        with freeze_time("2017-12-01 11:00:15"):
            reject_report_computed_task = message.RejectReportComputedTask()
        reject_report_computed_task.cannot_compute_task = deserialized_cannot_compute_task
        reject_report_computed_task.reason              = message.RejectReportComputedTask.REASON.TaskTimeLimitExceeded
        serialized_reject_report_computed_task = dump(reject_report_computed_task, REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 11:00:15"):
            response_3 = self.client.post(
                reverse('core:send'),
                data                                = serialized_reject_report_computed_task,
                content_type                        = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY      = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
                HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response_3.status_code,  400)
        self.assertIn('error', response_3.json().keys())

    def test_provider_forces_computed_task_report_missing_key_returns_400_error(self):
        """
        Tests if on provider ForceReportComputedTask message Concent will return HTTP 400 error
        if no key was provided in header.

        Expected message exchange:
        Provider -> Concent:    ForceReportComputedTask
        Concent  -> Provider:  HTTP 400 error.
        """

        # STEP 1: Provider forces computed task report via Concent

        with freeze_time("2017-12-01 10:00:00"):
            task_to_compute = message.TaskToCompute()

        task_to_compute.compute_task_def = message.ComputeTaskDef()
        task_to_compute.compute_task_def['task_id']     = '1'
        task_to_compute.compute_task_def['deadline']    = int(dateutil.parser.parse("2017-12-01 11:00:00").timestamp())

        serialized_task_to_compute      = dump(task_to_compute,             PROVIDER_PRIVATE_KEY,   REQUESTOR_PUBLIC_KEY)
        deserialized_task_to_compute    = load(serialized_task_to_compute,  REQUESTOR_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY, check_time = False)

        with freeze_time("2017-12-01 10:59:00"):
            force_report_computed_task = message.ForceReportComputedTask()
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

        with freeze_time("2017-12-01 10:00:00"):
            task_to_compute = message.TaskToCompute()

        task_to_compute.compute_task_def = message.ComputeTaskDef()
        task_to_compute.compute_task_def['task_id'] = '1'
        task_to_compute.compute_task_def['deadline'] = int(dateutil.parser.parse("2017-12-01 11:00:00").timestamp())

        serialized_task_to_compute      = dump(task_to_compute,             PROVIDER_PRIVATE_KEY,   REQUESTOR_PUBLIC_KEY)
        deserialized_task_to_compute    = load(serialized_task_to_compute,  REQUESTOR_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY, check_time = False)

        with freeze_time("2017-12-01 10:59:00"):
            force_report_computed_task = message.ForceReportComputedTask()
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

        with freeze_time("2017-12-01 10:00:00"):
            task_to_compute = message.TaskToCompute()

        task_to_compute.compute_task_def = message.ComputeTaskDef()
        task_to_compute.compute_task_def['task_id']     = '1'
        task_to_compute.compute_task_def['deadline']    = int(dateutil.parser.parse("2017-12-01 11:00:00").timestamp())

        serialized_task_to_compute      = dump(task_to_compute,             PROVIDER_PRIVATE_KEY,   REQUESTOR_PUBLIC_KEY)
        deserialized_task_to_compute    = load(serialized_task_to_compute,  REQUESTOR_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY, check_time = False)

        with freeze_time("2017-12-01 10:59:00"):
            force_report_computed_task = message.ForceReportComputedTask()

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

        with freeze_time("2017-12-01 10:00:00"):
            task_to_compute = message.TaskToCompute()

        task_to_compute.compute_task_def = message.ComputeTaskDef()
        task_to_compute.compute_task_def['task_id']     = '1'
        task_to_compute.compute_task_def['deadline']    = int(dateutil.parser.parse("2017-12-01 11:00:00").timestamp())

        serialized_task_to_compute      = dump(task_to_compute,             PROVIDER_PRIVATE_KEY,   REQUESTOR_PUBLIC_KEY)
        deserialized_task_to_compute    = load(serialized_task_to_compute,  REQUESTOR_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY, check_time = False)

        with freeze_time("2017-12-01 10:59:00"):
            force_report_computed_task = message.ForceReportComputedTask()
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

    def test_requestor_sends_ack_report_computed_task_with_message_cannot_compute_task(self):
        """
        Tests if on request AckReportComputedTask message Concent will return HTTP 400 error
        if message contains CannotComputeTask instead of TaskToCompute.

        Expected message exchange:
        Requestor -> Concent:    AckReportComputedTask
        Concent   -> Requestor:  HTTP 400 error.
        """
        # STEP 1: Requestor accepts computed task via Concent

        with freeze_time("2017-12-01 10:00:00"):
            cannot_compute_task = message.CannotComputeTask()
        cannot_compute_task.task_to_compute = message.TaskToCompute()
        cannot_compute_task.task_to_compute.compute_task_def = message.ComputeTaskDef()
        cannot_compute_task.task_to_compute.compute_task_def['task_id']     = '1'
        cannot_compute_task.task_to_compute.compute_task_def['deadline']    = int(dateutil.parser.parse("2017-12-01 11:00:00").timestamp())

        serialized_cannot_compute_task      = dump(cannot_compute_task,             REQUESTOR_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY)
        deserialized_cannot_compute_task    = load(serialized_cannot_compute_task,  PROVIDER_PRIVATE_KEY,   REQUESTOR_PUBLIC_KEY, check_time = False)

        with freeze_time("2017-12-01 11:00:05"):
            ack_report_computed_task = message.AckReportComputedTask()
        ack_report_computed_task.task_to_compute = deserialized_cannot_compute_task

        serialized_ack_report_computed_task = dump(ack_report_computed_task, REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:send'),
                data                           = serialized_ack_report_computed_task,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response.status_code,  400)
        self.assertIn('error', response.json().keys())

    def test_requestor_sends_reject_report_computed_task_with_message_task_to_compute(self):
        """
        Tests if on request RejectReportComputedTask message Concent will return HTTP 400 error
        if message contains TaskToCompute instead of CannotComputeTask .

        Expected message exchange:
        Requestor -> Concent:    RejectReportComputedTask
        Concent   -> Requestor:  HTTP 400 error.
        """
        # STEP 1: Requestor accepts computed task via Concent

        with freeze_time("2017-12-01 10:30:00"):
            task_to_compute = message.TaskToCompute()

        task_to_compute.compute_task_def = message.ComputeTaskDef()
        task_to_compute.compute_task_def['task_id'] = '1'
        serialized_task_to_compute      = dump(task_to_compute,             PROVIDER_PRIVATE_KEY,   REQUESTOR_PUBLIC_KEY)
        deserialized_task_to_compute    = load(serialized_task_to_compute,  REQUESTOR_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY, check_time = False)

        with freeze_time("2017-12-01 11:00:05"):
            reject_report_computed_task = message.RejectReportComputedTask()
        reject_report_computed_task.reason = message.RejectReportComputedTask.REASON.TaskTimeLimitExceeded
        reject_report_computed_task.task_to_compute = deserialized_task_to_compute
        serialized_reject_report_computed_task = dump(reject_report_computed_task, REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:send'),
                data                           = serialized_reject_report_computed_task,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response.status_code,  400)
        self.assertIn('error', response.json().keys())

    def test_provider_sends_force_report_computed_task_with_a_cut_message(self):
        """
        Tests if on request ForceReportComputedTask message Concent will return HTTP 400 error
        if message is malformed.

        Expected message exchange:
        Provider  -> Concent:   ForceReportComputedTask
        Concent   -> Provider:  HTTP 400 error.
        """

        # STEP 1: Provider forces computed task report via Concent

        with freeze_time("2017-12-01 10:00:00"):
            task_to_compute = message.TaskToCompute()

        task_to_compute.compute_task_def = message.ComputeTaskDef()
        task_to_compute.compute_task_def['task_id']     = '1'
        task_to_compute.compute_task_def['deadline']    = int(dateutil.parser.parse("2017-12-01 11:00:00").timestamp())

        serialized_task_to_compute      = dump(task_to_compute,             PROVIDER_PRIVATE_KEY,   REQUESTOR_PUBLIC_KEY)
        deserialized_task_to_compute    = load(serialized_task_to_compute,  REQUESTOR_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY, check_time = False)

        with freeze_time("2017-12-01 10:59:00"):
            force_report_computed_task = message.ForceReportComputedTask()
        force_report_computed_task.task_to_compute = deserialized_task_to_compute

        serialized_force_report_computed_task = dump(force_report_computed_task, PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 10:59:00"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_report_computed_task[:50],
                content_type                        = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY      = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
                HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response_1.status_code,  400)
        self.assertIn('error', response_1.json().keys())

    def test_provider_sends_force_report_computed_task_with_malformed_message(self):
        """
        Tests if on request ForceReportComputedTask message Concent will return HTTP 400 error
        if message is malformed.

        Expected message exchange:
        Provider  -> Concent:   ForceReportComputedTask
        Concent   -> Provider:  HTTP 400 error.
        """

        # STEP 1: Provider forces computed task report via Concent

        with freeze_time("2017-12-01 10:00:00"):
            task_to_compute = message.TaskToCompute()

        task_to_compute.compute_task_def = message.ComputeTaskDef()
        task_to_compute.compute_task_def['task_id'] = '1'
        task_to_compute.compute_task_def['deadline'] = int(dateutil.parser.parse("2017-12-01 11:00:00").timestamp())

        serialized_task_to_compute      = dump(task_to_compute,             PROVIDER_PRIVATE_KEY,   REQUESTOR_PUBLIC_KEY)
        deserialized_task_to_compute    = load(serialized_task_to_compute,  REQUESTOR_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY, check_time = False)

        with freeze_time("2017-12-01 10:59:00"):
            force_report_computed_task = message.ForceReportComputedTask()
        force_report_computed_task.task_to_compute = deserialized_task_to_compute
        serialized_force_report_computed_task = dump(force_report_computed_task, PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY)
        serialized_force_report_computed_task = serialized_force_report_computed_task[:120] + b'\x00' + serialized_force_report_computed_task[120:]

        with freeze_time("2017-12-01 10:59:00"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_report_computed_task,
                content_type                        = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY      = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
                HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response_1.status_code,  400)
        self.assertIn('error', response_1.json().keys())

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

        with freeze_time("2017-12-01 10:00:00"):
            task_to_compute = message.TaskToCompute()

        task_to_compute.compute_task_def = message.ComputeTaskDef()
        task_to_compute.compute_task_def['task_id'] = '1'
        task_to_compute.compute_task_def['deadline'] = int(dateutil.parser.parse("2017-12-01 11:00:00").timestamp())
        serialized_task_to_compute      = dump(task_to_compute,             PROVIDER_PRIVATE_KEY,   REQUESTOR_PUBLIC_KEY)
        deserialized_task_to_compute    = load(serialized_task_to_compute,  REQUESTOR_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY, check_time = False)

        with freeze_time("2017-12-01 10:59:00"):
            force_report_computed_task = message.ForceReportComputedTask()
        force_report_computed_task.task_to_compute = deserialized_task_to_compute
        serialized_force_report_computed_task = dump(force_report_computed_task, PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 10:59:00"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_report_computed_task,
                content_type                        = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY      = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
                HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
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

        force_report_computed_task_from_view = load(
            response_2.content,
            REQUESTOR_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY,
            check_time = False,
        )

        self.assertEqual(response_2.status_code,  200)
        self.assertEqual(force_report_computed_task_from_view.timestamp, force_report_computed_task.timestamp)
        self.assertEqual(force_report_computed_task_from_view.task_to_compute.timestamp, force_report_computed_task.task_to_compute.timestamp)

        # STEP 3: Requestor accepts computed task via Concent

        with freeze_time("2017-12-01 11:00:05"):
            ack_report_computed_task = message.AckReportComputedTask()
        ack_report_computed_task.task_to_compute = deserialized_task_to_compute
        serialized_ack_report_computed_task = dump(ack_report_computed_task, REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 11:00:05"):
            response_3 = self.client.post(
                reverse('core:send'),
                data                                = serialized_ack_report_computed_task,
                content_type                        = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY      = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
                HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response_3.status_code,  202)
        self.assertEqual(len(response_3.content), 0)

        # STEP 4: Concent passes computed task acceptance to the provider

        with freeze_time("2017-12-01 11:00:30"):
            response_4 = self.client.post(
                reverse('core:receive'),
                data         = '',
                content_type = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY      = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            )

        ack_report_computed_task_from_view = load(
            response_4.content,
            PROVIDER_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY,
            check_time = False
        )

        self.assertEqual(response_4.status_code,  200)
        self.assertEqual(ack_report_computed_task_from_view.timestamp, ack_report_computed_task.timestamp)
        self.assertEqual(ack_report_computed_task_from_view.task_to_compute.timestamp, ack_report_computed_task.task_to_compute.timestamp)

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

        with freeze_time("2017-12-01 10:00:00"):
            task_to_compute = message.TaskToCompute()

        task_to_compute.compute_task_def = message.ComputeTaskDef()
        task_to_compute.compute_task_def['task_id'] = '1'
        task_to_compute.compute_task_def['deadline'] = int(dateutil.parser.parse("2017-12-01 11:00:00").timestamp())

        serialized_task_to_compute      = dump(task_to_compute,             PROVIDER_PRIVATE_KEY,   REQUESTOR_PUBLIC_KEY)
        deserialized_task_to_compute    = load(serialized_task_to_compute,  REQUESTOR_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY, check_time = False)

        with freeze_time("2017-12-01 10:59:00"):
            force_report_computed_task = message.ForceReportComputedTask()

        force_report_computed_task.task_to_compute = deserialized_task_to_compute
        serialized_force_report_computed_task = dump(force_report_computed_task, PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 10:59:00"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_report_computed_task,
                content_type                        = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY      = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
                HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
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
        force_report_computed_task_from_view = load(
            response_2.content,
            REQUESTOR_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY,
            check_time = False
        )

        self.assertEqual(response_2.status_code,  200)
        self.assertIsInstance(force_report_computed_task_from_view, message.ForceReportComputedTask)
        self.assertEqual(force_report_computed_task_from_view.timestamp, force_report_computed_task.timestamp)
        self.assertEqual(force_report_computed_task_from_view.task_to_compute.timestamp, force_report_computed_task.task_to_compute.timestamp)

        # STEP 3: Requestor accepts computed task via Concent

        with freeze_time("2017-12-01 11:00:05"):
            ack_report_computed_task = message.AckReportComputedTask()
        ack_report_computed_task.task_to_compute = deserialized_task_to_compute
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
        ack_report_computed_task_from_view = load(
            response_4.content,
            PROVIDER_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY,
            check_time = False
        )

        self.assertEqual(response_4.status_code,  200)
        self.assertEqual(ack_report_computed_task_from_view.timestamp, ack_report_computed_task.timestamp)
        self.assertEqual(ack_report_computed_task_from_view.task_to_compute.timestamp, ack_report_computed_task.task_to_compute.timestamp)

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

    def test_if_reject_report_computed_task_after_deadline_is_in_database_concent_should_return_it(self):
        """
        Tests if on request to receive endpoint if there is RejectReportComputedTask message in database
        Concent will return it even if it is after deadline.

        """

        compute_task_def = message.ComputeTaskDef()
        compute_task_def['task_id'] = 1
        compute_task_def['deadline'] = int(dateutil.parser.parse("2017-11-17 9:59:00").timestamp())
        task_to_compute = message.TaskToCompute(
            timestamp = int(dateutil.parser.parse("2017-11-17 10:00:00").timestamp()),
            compute_task_def = compute_task_def,
        )
        cannot_compute_task = message.CannotComputeTask(
            task_to_compute = task_to_compute
        )

        reject_report_computed_task = message.RejectReportComputedTask(
            cannot_compute_task = cannot_compute_task
        )
        force_report_computed_task = message.ForceReportComputedTask(
            task_to_compute=task_to_compute
        )

        new_message_force = Message(
            type        = message.ForceReportComputedTask.TYPE,
            timestamp   = datetime.datetime.now(timezone.utc),
            data        = force_report_computed_task.serialize(),
            task_id     = 1,
        )
        new_message_force.full_clean()
        new_message_force.save()
        new_message_force_status = ReceiveStatus(
            message   = new_message_force,
            timestamp = new_message_force.timestamp,
            delivered = False
        )
        new_message_force_status.full_clean()
        new_message_force_status.save()

        new_message_reject = Message(
            type        = message.RejectReportComputedTask.TYPE,
            timestamp   = datetime.datetime.now(timezone.utc),
            data        = reject_report_computed_task.serialize(),
            task_id     = 1,
        )
        new_message_reject.full_clean()
        new_message_reject.save()
        new_message_reject_status = ReceiveStatus(
            message   = new_message_reject,
            timestamp = new_message_reject.timestamp,
            delivered = False
        )
        new_message_reject_status.full_clean()
        new_message_reject_status.save()

        with freeze_time("2017-12-01 12:00:00"):
            response = self.client.post(
                reverse('core:receive'),
                data         = '',
                content_type = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            )

        reject_report_computed_task_from_view = load(
            response.content,
            PROVIDER_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY,
            check_time = False
        )

        self.assertEqual(response.status_code,  200)
        self.assertEqual(reject_report_computed_task_from_view, reject_report_computed_task)

    def test_if_there_is_undelivered_message_in_future_in_database_concent_should_return_it(self):
        """
        Tests if on request to receive_out_of_band endpoint if there is message in database
        Concent will return it even if it has timestamp in future.

        """

        compute_task_def = message.ComputeTaskDef()
        compute_task_def['task_id'] = 1
        compute_task_def['deadline'] = int(dateutil.parser.parse("2017-11-17 9:59:00").timestamp())
        task_to_compute = message.TaskToCompute(
            timestamp = int(dateutil.parser.parse("2017-11-17 10:00:00").timestamp()),
            compute_task_def = compute_task_def,
        )

        ack_report_computed_task = message.AckReportComputedTask(
            task_to_compute = task_to_compute
        )
        force_report_computed_task = message.ForceReportComputedTask(
            task_to_compute=task_to_compute
        )

        new_message_force = Message(
            type        = message.ForceReportComputedTask.TYPE,
            timestamp   = datetime.datetime.now(timezone.utc),
            data        = force_report_computed_task.serialize(),
            task_id     = 1,
        )
        new_message_force.full_clean()
        new_message_force.save()
        new_message_force_status = ReceiveStatus(
            message   = new_message_force,
            timestamp = new_message_force.timestamp,
            delivered = False
        )
        new_message_force_status.full_clean()
        new_message_force_status.save()

        new_message_ack = Message(
            type        = message.AckReportComputedTask.TYPE,
            timestamp   = datetime.datetime.now(timezone.utc),
            data        = ack_report_computed_task.serialize(),
            task_id     = 1,
        )
        new_message_ack.full_clean()
        new_message_ack.save()
        new_message_reject_status = ReceiveStatus(
            message   = new_message_ack,
            timestamp = new_message_ack.timestamp,
            delivered = False
        )
        new_message_reject_status.full_clean()
        new_message_reject_status.save()

        with freeze_time("2017-12-01 09:00:00"):
            response = self.client.post(
                reverse('core:receive_out_of_band'),
                data         = '',
                content_type = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            )

        message_verdict = load(
            response.content,
            PROVIDER_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY,
            check_time = False
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(message_verdict, message.VerdictReportComputedTask)
        self.assertGreaterEqual(message_verdict.timestamp, int(dateutil.parser.parse("2017-12-01 09:00:00").timestamp()))
        self.assertLessEqual(message_verdict.timestamp, int(dateutil.parser.parse("2017-12-01 09:00:15").timestamp()))

    def test_if_there_is_undelivered_message_with_not_handled_type_database_concent_should_return_it_from_receive_out_of_band(self):
        """
        Tests if on request to receive_out_of_band endpoint if there is message in database
        Concent will return it even if it is not handled.

        """

        compute_task_def = message.ComputeTaskDef()
        compute_task_def['task_id'] = 1
        compute_task_def['deadline'] = int(dateutil.parser.parse("2017-11-17 9:59:00").timestamp())
        task_to_compute = message.TaskToCompute(
            timestamp = int(dateutil.parser.parse("2017-11-17 10:00:00").timestamp()),
            compute_task_def = compute_task_def,
        )

        ack_report_computed_task = message.AckReportComputedTask(
            task_to_compute = task_to_compute
        )
        force_report_computed_task = message.ForceReportComputedTask(
            task_to_compute=task_to_compute
        )

        new_message_force = Message(
            type        = message.ForceReportComputedTask.TYPE,
            timestamp   = datetime.datetime.now(timezone.utc),
            data        = force_report_computed_task.serialize(),
            task_id     = 1,
        )
        new_message_force.full_clean()
        new_message_force.save()
        new_message_force_status = ReceiveStatus(
            message   = new_message_force,
            timestamp = new_message_force.timestamp,
            delivered = False
        )
        new_message_force_status.full_clean()
        new_message_force_status.save()

        new_message_ack = Message(
            type        = message.AckReportComputedTask.TYPE,
            timestamp   = datetime.datetime.now(timezone.utc),
            data        = ack_report_computed_task.serialize(),
            task_id     = 1,
        )
        new_message_ack.full_clean()
        new_message_ack.save()
        new_message_reject_status = ReceiveOutOfBandStatus(
            message   = new_message_ack,
            timestamp = new_message_ack.timestamp,
            delivered = False
        )
        new_message_reject_status.full_clean()
        new_message_reject_status.save()

        with freeze_time("2017-12-01 10:00:05"):
            response = self.client.post(
                reverse('core:receive_out_of_band'),
                data         = '',
                content_type = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            )

        ack_report_computed_task_from_view = load(
            response.content,
            PROVIDER_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY,
            check_time = False
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(ack_report_computed_task_from_view, message.AckReportComputedTask)
        self.assertEqual(ack_report_computed_task_from_view, ack_report_computed_task)
