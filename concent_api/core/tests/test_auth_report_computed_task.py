from base64                 import b64encode

from django.test            import override_settings
from django.urls            import reverse
from freezegun              import freeze_time
from golem_messages         import dump
from golem_messages         import load
from golem_messages         import message
import dateutil.parser

from core.tests.utils       import ConcentIntegrationTestCase
from core.models            import MessageAuth
from core.models            import Subtask
from utils.testing_helpers  import generate_ecc_key_pair


(CONCENT_PRIVATE_KEY, CONCENT_PUBLIC_KEY)                         = generate_ecc_key_pair()
(PROVIDER_PRIVATE_KEY, PROVIDER_PUBLIC_KEY)                       = generate_ecc_key_pair()
(REQUESTOR_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY)                     = generate_ecc_key_pair()
(DIFFERENT_PROVIDER_PRIVATE_KEY, DIFFERENT_PROVIDER_PUBLIC_KEY)   = generate_ecc_key_pair()
(DIFFERENT_REQUESTOR_PRIVATE_KEY, DIFFERENT_REQUESTOR_PUBLIC_KEY) = generate_ecc_key_pair()


@override_settings(
    CONCENT_PRIVATE_KEY = CONCENT_PRIVATE_KEY,
    CONCENT_PUBLIC_KEY  = CONCENT_PUBLIC_KEY,
    CONCENT_MESSAGING_TIME = 10,  # seconds
)
class AuthReportComputedTaskIntegrationTest(ConcentIntegrationTestCase):

    def setUp(self):
        self.compute_task_def               = message.ComputeTaskDef()
        self.compute_task_def['task_id']    = '1'
        self.compute_task_def['subtask_id'] = '8'
        self.compute_task_def['deadline']   = int(dateutil.parser.parse("2017-12-01 11:00:00").timestamp())
        with freeze_time("2017-12-01 10:00:00"):
            self.task_to_compute = message.TaskToCompute(
                compute_task_def = self.compute_task_def
            )

        # sign task_to_compute message with PROVIDER sig
        self.serialized_task_to_compute   = dump(self.task_to_compute, PROVIDER_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY)
        self.deserialized_task_to_compute = load(self.serialized_task_to_compute, REQUESTOR_PRIVATE_KEY, PROVIDER_PUBLIC_KEY, check_time = False)

        with freeze_time("2017-12-01 10:59:00"):
            self.report_computed_task = message.tasks.ReportComputedTask(
                task_to_compute = self.deserialized_task_to_compute
            )
        with freeze_time("2017-12-01 10:59:00"):
            self.force_report_computed_task = message.ForceReportComputedTask()
        self.force_report_computed_task.report_computed_task = self.report_computed_task

        self.serialized_force_report_computed_task = dump(self.force_report_computed_task, PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

    def test_provider_forces_computed_task_report_and_requestor_sends_acknowledgement_should_work_only_with_correct_keys(self):
        """
        Tests if message exchange which results in AckReportComputedTask
        will work only if correct keys are provided, and each stored message store data about used keys in database.

        Expected message exchange:
        Provider                -> Concent:                     ForceReportComputedTask
        Concent                 -> WrongRequestor/Provider:     HTTP 204
        Concent                 -> Requestor:                   ForceReportComputedTask
        WrongRequestor/Provider -> Concent:                     HTTP 400
        Requestor               -> Concent:                     AckReportComputedTask
        Concent                 -> WrongProvider/Requestor:     HTTP 400
        Concent                 -> Provider:                    AckReportComputedTask

        """

        # STEP 1: Provider forces computed task report via Concent

        with freeze_time("2017-12-01 10:59:00"):
            response = self.client.post(
                reverse('core:send'),
                data                                = self.serialized_force_report_computed_task,
                content_type                        = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY      = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
                HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response.status_code,        202)
        self.assertEqual(len(response.content),       0)
        self.assertEqual(MessageAuth.objects.count(), 1)

        message_auth = MessageAuth.objects.last()
        self.assertEqual(message_auth.message.type,               message.ForceReportComputedTask.TYPE)
        self.assertEqual(message_auth.provider_public_key_bytes,  PROVIDER_PUBLIC_KEY)
        self.assertEqual(message_auth.requestor_public_key_bytes, REQUESTOR_PUBLIC_KEY)

        self._test_subtask_state(
            task_id                  = '1',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.FORCING_REPORT,
            provider_key             = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            requestor_key            = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            expected_nested_messages = {'task_to_compute', 'report_computed_task'},
            next_deadline            = self._parse_iso_date_to_timestamp("2017-12-01 11:00:10"),
        )
        self._test_last_stored_messages(
            expected_messages = [
                message.concents.ForceReportComputedTask,  # TODO: Remove in final step
                message.TaskToCompute,
                message.ReportComputedTask,
            ],
            task_id         = '1',
            subtask_id      = '8',
            timestamp       = "2017-12-01 10:59:00"
        )

        # STEP 2: Concent do not forces computed task report on the requestor with different or mixed key

        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = '',
                content_type                   = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(DIFFERENT_REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(len(response.content),       0)
        self.assertEqual(MessageAuth.objects.count(), 1)

        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = '',
                content_type                   = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(len(response.content),       0)
        self.assertEqual(MessageAuth.objects.count(), 1)

        # STEP 3: Concent forces computed task report on the requestor with correct key

        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = '',
                content_type                   = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        force_report_computed_task_from_view = load(
            response.content,
            REQUESTOR_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY,
            check_time = False,
        )

        self.assertEqual(response.status_code,                                                                  200)
        self.assertEqual(force_report_computed_task_from_view.timestamp,                                        self._parse_iso_date_to_timestamp("2017-12-01 11:00:05"))
        self.assertEqual(force_report_computed_task_from_view.report_computed_task.task_to_compute.timestamp,   self.force_report_computed_task.report_computed_task.task_to_compute.timestamp)
        self.assertEqual(force_report_computed_task_from_view.report_computed_task.task_to_compute,             self.force_report_computed_task.report_computed_task.task_to_compute)
        self.assertEqual(MessageAuth.objects.count(),                                                           2)

        # STEP 4: Requestor do not accepts computed task via Concent with different or mixed key

        with freeze_time("2017-12-01 11:00:05"):
            ack_report_computed_task = message.AckReportComputedTask(
                task_to_compute = self.deserialized_task_to_compute,
            )
        serialized_ack_report_computed_task = dump(ack_report_computed_task, REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:send'),
                data                           = serialized_ack_report_computed_task,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(DIFFERENT_REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response.status_code,        400)
        self.assertEqual(MessageAuth.objects.count(), 2)

        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:send'),
                data                           = serialized_ack_report_computed_task,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response.status_code,        400)
        self.assertEqual(MessageAuth.objects.count(), 2)

        # STEP 5: Requestor accepts computed task via Concent with correct key

        with freeze_time("2017-12-01 11:00:05"):
            ack_report_computed_task = message.AckReportComputedTask(
                task_to_compute = self.deserialized_task_to_compute,
            )
        serialized_ack_report_computed_task = dump(ack_report_computed_task, REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:send'),
                data                           = serialized_ack_report_computed_task,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response.status_code,        202)
        self.assertEqual(MessageAuth.objects.count(), 3)

        message_auth = MessageAuth.objects.last()
        self.assertEqual(message_auth.message.type,               message.AckReportComputedTask.TYPE)
        self.assertEqual(message_auth.provider_public_key_bytes,  PROVIDER_PUBLIC_KEY)
        self.assertEqual(message_auth.requestor_public_key_bytes, REQUESTOR_PUBLIC_KEY)

        self._test_subtask_state(
            task_id                  = '1',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.REPORTED,
            provider_key             = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            requestor_key            = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            expected_nested_messages = {'task_to_compute', 'report_computed_task', 'ack_report_computed_task'},
        )
        self._test_last_stored_messages(
            expected_messages= [
                message.concents.AckReportComputedTask,  # TODO: Remove in final step
                message.concents.AckReportComputedTask,
            ],
            task_id         = '1',
            subtask_id      = '8',
            timestamp       = "2017-12-01 11:00:05"
        )

        # STEP 6: Concent do not passes computed task acceptance to the provider with different or mixed key

        with freeze_time("2017-12-01 11:00:15"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = '',
                content_type                   = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(DIFFERENT_PROVIDER_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(len(response.content),       0)
        self.assertEqual(MessageAuth.objects.count(), 3)

        with freeze_time("2017-12-01 11:00:15"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = '',
                content_type                   = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(len(response.content),       0)
        self.assertEqual(MessageAuth.objects.count(), 3)

        # STEP 7: Concent passes computed task acceptance to the provider with correct key

        with freeze_time("2017-12-01 11:00:15"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = '',
                content_type                   = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            )

        ack_report_computed_task_from_view = load(
            response.content,
            PROVIDER_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY,
            check_time = False,
        )

        self.assertEqual(response.status_code,                         200)
        self.assertEqual(ack_report_computed_task_from_view.timestamp, self._parse_iso_date_to_timestamp("2017-12-01 11:00:15"))
        self.assertEqual(MessageAuth.objects.count(),                  4)

        self._assert_client_count_is_equal(2)

    def test_provider_forces_computed_task_report_and_requestor_sends_rejection_due_to_failed_computation_should_work_only_with_correct_keys(self):
        """
        Tests if message exchange which results in RejectReportComputedTask due to exceeded deadline
        will work only if correct keys are provided, and each stored message store data about used keys in database.

        Expected message exchange:
        Provider                -> Concent:                     ForceReportComputedTask
        Concent                 -> WrongRequestor/Provider:     HTTP 204
        Concent                 -> Requestor:                   ForceReportComputedTask
        WrongRequestor/Provider -> Concent:                     HTTP 400
        Requestor               -> Concent:                     RejectReportComputedTask (failed computation)
        Concent                 -> WrongProvider/Requestor:     HTTP 204
        Concent                 -> Provider:                    RejectReportComputedTask
        """

        # STEP 1: Provider forces computed task report via Concent

        compute_task_def = message.ComputeTaskDef()
        compute_task_def['task_id']    = '1'
        compute_task_def['subtask_id'] = '8'
        compute_task_def['deadline']   = int(dateutil.parser.parse("2017-12-01 11:00:00").timestamp())
        with freeze_time("2017-12-01 10:00:00"):
            task_to_compute = message.TaskToCompute(
                compute_task_def = compute_task_def
            )

        # sign task_to_compute message with PROVIDER sig

        serialized_task_to_compute   = dump(task_to_compute,             PROVIDER_PRIVATE_KEY,   REQUESTOR_PUBLIC_KEY)
        deserialized_task_to_compute = load(serialized_task_to_compute,  REQUESTOR_PRIVATE_KEY,  PROVIDER_PUBLIC_KEY, check_time = False)

        with freeze_time("2017-12-01 10:59:00"):
            report_computed_task = message.tasks.ReportComputedTask(
                task_to_compute = deserialized_task_to_compute
            )

        with freeze_time("2017-12-01 10:59:00"):
            force_report_computed_task = message.ForceReportComputedTask()

        force_report_computed_task.report_computed_task = report_computed_task
        serialized_force_report_computed_task           = dump(force_report_computed_task, PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 10:59:00"):
            response = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_report_computed_task,
                content_type                        = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY      = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
                HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response.status_code,        202)
        self.assertEqual(len(response.content),       0)
        self.assertEqual(MessageAuth.objects.count(), 1)

        message_auth = MessageAuth.objects.last()
        self.assertEqual(message_auth.message.type,               message.ForceReportComputedTask.TYPE)
        self.assertEqual(message_auth.provider_public_key_bytes,  PROVIDER_PUBLIC_KEY)
        self.assertEqual(message_auth.requestor_public_key_bytes, REQUESTOR_PUBLIC_KEY)

        self._test_subtask_state(
            task_id                  = '1',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.FORCING_REPORT,
            provider_key             = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            requestor_key            = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            expected_nested_messages = {'task_to_compute', 'report_computed_task'},
            next_deadline            = self._parse_iso_date_to_timestamp("2017-12-01 11:00:10"),
        )
        self._test_last_stored_messages(
            expected_messages = [
                message.concents.ForceReportComputedTask,  # TODO: Remove in final step
                message.TaskToCompute,
                message.ReportComputedTask,
            ],
            task_id         = '1',
            subtask_id      = '8',
            timestamp       = "2017-12-01 10:59:00"
        )

        # STEP 2: Concent do not forces computed task report on the requestor with different or mixed key

        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = '',
                content_type                   = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(DIFFERENT_REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(len(response.content),       0)
        self.assertEqual(MessageAuth.objects.count(), 1)

        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = '',
                content_type                   = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(len(response.content),       0)
        self.assertEqual(MessageAuth.objects.count(), 1)

        # STEP 3: Concent forces computed task report on the requestor with correct key

        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = '',
                content_type                   = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        force_report_computed_task_from_view = load(
            response.content,
            REQUESTOR_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY,
            check_time = False,
        )

        self.assertEqual(response.status_code,                                                                  200)
        self.assertEqual(force_report_computed_task_from_view.timestamp,                                        self._parse_iso_date_to_timestamp("2017-12-01 11:00:05"))
        self.assertEqual(force_report_computed_task_from_view.report_computed_task.task_to_compute.timestamp,   force_report_computed_task.report_computed_task.task_to_compute.timestamp)
        self.assertEqual(force_report_computed_task_from_view.report_computed_task.task_to_compute,             force_report_computed_task.report_computed_task.task_to_compute)
        self.assertEqual(MessageAuth.objects.count(),                                                           2)

        # STEP 4: Requestor do not rejects computed task due to CannotComputeTask or TaskFailure with different or mixed key

        with freeze_time("2017-12-01 10:30:00"):
            cannot_compute_task = message.CannotComputeTask()
        cannot_compute_task.task_to_compute                  = message.TaskToCompute()
        cannot_compute_task.task_to_compute.compute_task_def = compute_task_def
        cannot_compute_task.reason                           = message.CannotComputeTask.REASON.WrongKey

        serialized_cannot_compute_task   = dump(cannot_compute_task,            PROVIDER_PRIVATE_KEY,  REQUESTOR_PUBLIC_KEY)
        deserialized_cannot_compute_task = load(serialized_cannot_compute_task, REQUESTOR_PRIVATE_KEY, PROVIDER_PUBLIC_KEY, check_time = False)

        with freeze_time("2017-12-01 11:00:05"):
            reject_report_computed_task = message.RejectReportComputedTask()
        reject_report_computed_task.cannot_compute_task = deserialized_cannot_compute_task

        serialized_reject_report_computed_task = dump(reject_report_computed_task, REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:send'),
                data                           = serialized_reject_report_computed_task,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(DIFFERENT_REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response.status_code,        400)
        self.assertEqual(MessageAuth.objects.count(), 2)

        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:send'),
                data                           = serialized_reject_report_computed_task,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response.status_code,        400)
        self.assertEqual(MessageAuth.objects.count(), 2)

        self._test_subtask_state(
            task_id                  = '1',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.FORCING_REPORT,
            provider_key             = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            requestor_key            = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            expected_nested_messages = {'task_to_compute', 'report_computed_task'},
            next_deadline            = self._parse_iso_date_to_timestamp("2017-12-01 11:00:10"),
        )

        # STEP 5: Requestor rejects computed task due to CannotComputeTask or TaskFailure with correct key

        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:send'),
                data                           = serialized_reject_report_computed_task,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response.status_code,        202)
        self.assertEqual(len(response.content),       0)
        self.assertEqual(MessageAuth.objects.count(), 3)

        self._test_subtask_state(
            task_id                  = '1',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.FAILED,
            provider_key             = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            requestor_key            = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            expected_nested_messages = {'task_to_compute', 'report_computed_task', 'reject_report_computed_task'},
        )
        self._test_last_stored_messages(
            expected_messages= [
                message.concents.RejectReportComputedTask,  # TODO: Remove in final step
                message.concents.RejectReportComputedTask,
            ],
            task_id         = '1',
            subtask_id      = '8',
            timestamp       = "2017-12-01 11:00:05"
        )

        # STEP 6: Concent do not passes computed task rejection to the provider with different or mixed key

        with freeze_time("2017-12-01 11:00:15"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = '',
                content_type                   = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(DIFFERENT_PROVIDER_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(MessageAuth.objects.count(), 3)

        with freeze_time("2017-12-01 11:00:15"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = '',
                content_type                   = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response.status_code, 204)
        self.assertEqual(MessageAuth.objects.count(), 3)

        # STEP 7: Concent passes computed task rejection to the provider with correct key

        with freeze_time("2017-12-01 11:00:15"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = '',
                content_type                   = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            )

        force_report_computed_task_response = load(
            response.content,
            PROVIDER_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY,
            check_time = False,
        )

        self.assertEqual(response.status_code,                                                                                          200)
        self.assertEqual(force_report_computed_task_response.timestamp,                                                                 self._parse_iso_date_to_timestamp("2017-12-01 11:00:15"))
        self.assertEqual(force_report_computed_task_response.reject_report_computed_task.timestamp,                                     self._parse_iso_date_to_timestamp("2017-12-01 11:00:05"))
        self.assertEqual(force_report_computed_task_response.reject_report_computed_task.cannot_compute_task.timestamp,                 reject_report_computed_task.cannot_compute_task.timestamp)
        self.assertEqual(force_report_computed_task_response.reject_report_computed_task.cannot_compute_task.task_to_compute.timestamp, reject_report_computed_task.cannot_compute_task.task_to_compute.timestamp)
        self.assertEqual(MessageAuth.objects.count(),                                                                                   4)

        self._assert_client_count_is_equal(2)

    def test_provider_forces_computed_task_report_and_requestor_sends_rejection_due_to_exceeded_deadline_should_work_only_with_correct_keys(self):
        """
        Tests if message exchange which results in VerdictReportComputedTask due to exceeded deadline
        will work only if correct keys are provided, and each stored message store data about used keys in database.

        Expected message exchange:
        Provider                -> Concent:                     ForceReportComputedTask
        Concent                 -> WrongRequestor/Provider:     HTTP 204
        Concent                 -> Requestor:                   ForceReportComputedTask
        WrongRequestor/Provider -> Concent:                     HTTP 400
        Requestor               -> Concent:                     RejectReportComputedTask (deadline exceeded)
        Concent                 -> WrongProvider/Requestor:     HTTP 204
        Concent                 -> Provider:                    AckReportComputedTask
        Concent                 -> WrongRequestor/Provider:     HTTP 204
        Concent                 -> Requestor:                   VerdictReportComputedTask
        """

        # STEP 1: Provider forces computed task report via Concent

        compute_task_def = message.ComputeTaskDef()
        compute_task_def['task_id']    = '1'
        compute_task_def['subtask_id'] = '8'
        compute_task_def['deadline']   = int(dateutil.parser.parse("2017-12-01 11:00:00").timestamp())
        with freeze_time("2017-12-01 10:00:00"):
            task_to_compute = message.TaskToCompute(
                compute_task_def = compute_task_def
            )

        # sign task_to_compute message with PROVIDER sig

        serialized_task_to_compute   = dump(task_to_compute,            PROVIDER_PRIVATE_KEY,  REQUESTOR_PUBLIC_KEY)
        deserialized_task_to_compute = load(serialized_task_to_compute, REQUESTOR_PRIVATE_KEY, PROVIDER_PUBLIC_KEY, check_time = False)

        with freeze_time("2017-12-01 10:59:00"):
            report_computed_task = message.tasks.ReportComputedTask(
                task_to_compute = deserialized_task_to_compute
            )

        with freeze_time("2017-12-01 10:59:00"):
            force_report_computed_task = message.ForceReportComputedTask()

        force_report_computed_task.report_computed_task = report_computed_task
        serialized_force_report_computed_task           = dump(force_report_computed_task, PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 10:59:00"):
            response = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_report_computed_task,
                content_type                        = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY      = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
                HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response.status_code,        202)
        self.assertEqual(len(response.content),       0)
        self.assertEqual(MessageAuth.objects.count(), 1)

        message_auth = MessageAuth.objects.last()
        self.assertEqual(message_auth.message.type,               message.ForceReportComputedTask.TYPE)
        self.assertEqual(message_auth.provider_public_key_bytes,  PROVIDER_PUBLIC_KEY)
        self.assertEqual(message_auth.requestor_public_key_bytes, REQUESTOR_PUBLIC_KEY)

        self._test_subtask_state(
            task_id                  = '1',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.FORCING_REPORT,
            provider_key             = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            requestor_key            = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            expected_nested_messages = {'task_to_compute', 'report_computed_task'},
            next_deadline            = self._parse_iso_date_to_timestamp("2017-12-01 11:00:10"),
        )
        self._test_last_stored_messages(
            expected_messages = [
                message.concents.ForceReportComputedTask,  # TODO: Remove in final step
                message.TaskToCompute,
                message.ReportComputedTask,
            ],
            task_id         = '1',
            subtask_id      = '8',
            timestamp       = "2017-12-01 10:59:00"
        )

        # STEP 2: Concent do not forces computed task report on the requestor with different or mixed key

        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = '',
                content_type                   = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(DIFFERENT_REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(len(response.content),       0)
        self.assertEqual(MessageAuth.objects.count(), 1)

        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = '',
                content_type                   = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(len(response.content),       0)
        self.assertEqual(MessageAuth.objects.count(), 1)

        # STEP 3: Concent forces computed task report on the requestor with correct key

        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = '',
                content_type                   = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        force_report_computed_task_from_view = load(
            response.content,
            REQUESTOR_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY,
            check_time = False,
        )

        self.assertEqual(response.status_code,                                                                  200)
        self.assertEqual(force_report_computed_task_from_view.timestamp,                                        self._parse_iso_date_to_timestamp("2017-12-01 11:00:05"))
        self.assertEqual(force_report_computed_task_from_view.report_computed_task.task_to_compute.timestamp,   force_report_computed_task.report_computed_task.task_to_compute.timestamp)
        self.assertEqual(force_report_computed_task_from_view.report_computed_task.task_to_compute,             force_report_computed_task.report_computed_task.task_to_compute)
        self.assertEqual(MessageAuth.objects.count(),                                                           2)

        # STEP 4: Requestor do not rejects computed task due to CannotComputeTask or TaskFailure with different or mixed key

        with freeze_time("2017-12-01 10:00:00"):
            cannot_compute_task = message.CannotComputeTask()
        cannot_compute_task.task_to_compute                  = message.TaskToCompute()
        cannot_compute_task.task_to_compute.compute_task_def = compute_task_def
        cannot_compute_task.reason                           = message.CannotComputeTask.REASON.WrongCTD

        serialized_cannot_compute_task   = dump(cannot_compute_task,            PROVIDER_PRIVATE_KEY,  REQUESTOR_PUBLIC_KEY)
        deserialized_cannot_compute_task = load(serialized_cannot_compute_task, REQUESTOR_PRIVATE_KEY, PROVIDER_PUBLIC_KEY, check_time = False)

        with freeze_time("2017-12-01 11:00:05"):
            reject_report_computed_task = message.RejectReportComputedTask(
                cannot_compute_task = deserialized_cannot_compute_task,
                reason              = message.RejectReportComputedTask.REASON.TaskTimeLimitExceeded
            )
        serialized_reject_report_computed_task = dump(reject_report_computed_task, REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:send'),
                data                           = serialized_reject_report_computed_task,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(DIFFERENT_REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response.status_code,        400)
        self.assertEqual(MessageAuth.objects.count(), 2)

        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:send'),
                data                           = serialized_reject_report_computed_task,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response.status_code,        400)
        self.assertEqual(MessageAuth.objects.count(), 2)

        self._test_subtask_state(
            task_id                  = '1',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.FORCING_REPORT,
            provider_key             = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            requestor_key            = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            expected_nested_messages = {'task_to_compute', 'report_computed_task'},
            next_deadline            = self._parse_iso_date_to_timestamp("2017-12-01 11:00:10"),
        )

        # STEP 5: Requestor rejects computed task due to CannotComputeTask or TaskFailure with correct key

        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:send'),
                data                           = serialized_reject_report_computed_task,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response.status_code,        202)
        self.assertEqual(len(response.content),       0)
        self.assertEqual(MessageAuth.objects.count(), 3)

        message_auth = MessageAuth.objects.last()
        self.assertEqual(message_auth.message.type,               message.RejectReportComputedTask.TYPE)
        self.assertEqual(message_auth.provider_public_key_bytes,  PROVIDER_PUBLIC_KEY)
        self.assertEqual(message_auth.requestor_public_key_bytes, REQUESTOR_PUBLIC_KEY)

        self._test_subtask_state(
            task_id                  = '1',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.FAILED,
            provider_key             = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            requestor_key            = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            expected_nested_messages = {'task_to_compute', 'report_computed_task', 'reject_report_computed_task'},
        )
        self._test_last_stored_messages(
            expected_messages= [
                message.concents.RejectReportComputedTask,  # TODO: Remove in final step
                message.concents.RejectReportComputedTask,
            ],
            task_id         = '1',
            subtask_id      = '8',
            timestamp       = "2017-12-01 11:00:05"
        )

        # STEP 6: Concent do not overrides computed task rejection and sends acceptance message to the provider with different or mixed key

        with freeze_time("2017-12-01 11:00:15"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = '',
                content_type                   = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(DIFFERENT_PROVIDER_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(len(response.content),       0)
        self.assertEqual(MessageAuth.objects.count(), 3)

        with freeze_time("2017-12-01 11:00:15"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = '',
                content_type                   = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(len(response.content),       0)
        self.assertEqual(MessageAuth.objects.count(), 3)

        # STEP 7: Concent overrides computed task rejection and sends acceptance message to the provider with correct key

        with freeze_time("2017-12-01 11:00:15"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = '',
                content_type                   = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response.status_code,        200)
        self.assertEqual(MessageAuth.objects.count(), 4)

        serialized_message_from_concent_to_provider = response.content
        message_from_concent_to_provider            = load(
            serialized_message_from_concent_to_provider,
            PROVIDER_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY,
            check_time = False
        )

        self.assertIsInstance(message_from_concent_to_provider,                                     message.concents.ForceReportComputedTaskResponse)
        self.assertEqual(message_from_concent_to_provider.timestamp,                                self._parse_iso_date_to_timestamp("2017-12-01 11:00:15"))
        self.assertEqual(message_from_concent_to_provider.ack_report_computed_task.task_to_compute, deserialized_task_to_compute)

        # STEP 8: Requestor do not receives computed task report verdict out of band due to an overridden decision with different or mixed key

        with freeze_time("2017-12-01 11:00:15"):
            response = self.client.post(
                reverse('core:receive_out_of_band'),
                data                           = '',
                content_type                   = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(DIFFERENT_REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(len(response.content),       0)
        self.assertEqual(MessageAuth.objects.count(), 4)

        with freeze_time("2017-12-01 11:00:15"):
            response = self.client.post(
                reverse('core:receive_out_of_band'),
                data                           = '',
                content_type                   = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(len(response.content),       0)
        self.assertEqual(MessageAuth.objects.count(), 4)

        # STEP 9: Requestor receives computed task report verdict out of band due to an overridden decision with correct key

        with freeze_time("2017-12-01 11:00:15"):
            response = self.client.post(
                reverse('core:receive_out_of_band'),
                data                           = '',
                content_type                   = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response.status_code,        200)
        self.assertEqual(MessageAuth.objects.count(), 5)

        message_auth = MessageAuth.objects.last()
        self.assertEqual(message_auth.message.type,               message.VerdictReportComputedTask.TYPE)
        self.assertEqual(message_auth.provider_public_key_bytes,  PROVIDER_PUBLIC_KEY)
        self.assertEqual(message_auth.requestor_public_key_bytes, REQUESTOR_PUBLIC_KEY)

        message_from_concent_to_requestor = load(response.content, REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY, check_time = False)

        self.assertIsInstance(message_from_concent_to_requestor,                     message.VerdictReportComputedTask)
        self.assertGreaterEqual(message_from_concent_to_requestor.timestamp,         int(dateutil.parser.parse("2017-12-01 11:00:05").timestamp()))
        self.assertLessEqual(   message_from_concent_to_requestor.timestamp,         int(dateutil.parser.parse("2017-12-01 11:00:15").timestamp()))
        self.assertEqual(message_from_concent_to_requestor.ack_report_computed_task, message_from_concent_to_provider.ack_report_computed_task)

        self._test_subtask_state(
            task_id                  = '1',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.FAILED,
            provider_key             = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            requestor_key            = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            expected_nested_messages = {'task_to_compute', 'report_computed_task', 'reject_report_computed_task'},
        )

        self._assert_client_count_is_equal(2)

    def test_provider_forces_computed_task_report_and_requestor_does_not_respond_should_work_only_with_correct_keys(self):
        """
        Tests if message exchange which results in VerdictReportComputedTask due to no response from requestor
        will work only if correct keys are provided, and each stored message store data about used keys in database.

        Expected message exchange:
        Provider     -> Concent:                    ForceReportComputedTask
        Concent      -> WrongRequestor/Provider:    HTTP 204
        Concent      -> Requestor:                  ForceReportComputedTask
        Requestor    -> Concent:                    no response
        Concent      -> WrongProvider/Requestor:    HTTP 204
        Concent      -> Provider:                   AckReportComputedTask
        Concent      -> WrongRequestor/Provider:    HTTP 204
        Concent      -> Requestor:                  VerdictReportComputedTask
        """

        # STEP 1: Provider forces computed task report via Concent

        with freeze_time("2017-12-01 10:59:00"):
            response = self.client.post(
                reverse('core:send'),
                data                                = self.serialized_force_report_computed_task,
                content_type                        = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY      = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
                HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response.status_code,        202)
        self.assertEqual(len(response.content),       0)
        self.assertEqual(MessageAuth.objects.count(), 1)

        message_auth = MessageAuth.objects.last()
        self.assertEqual(message_auth.message.type,               message.ForceReportComputedTask.TYPE)
        self.assertEqual(message_auth.provider_public_key_bytes,  PROVIDER_PUBLIC_KEY)
        self.assertEqual(message_auth.requestor_public_key_bytes, REQUESTOR_PUBLIC_KEY)

        self._test_subtask_state(
            task_id                  = '1',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.FORCING_REPORT,
            provider_key             = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            requestor_key            = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            expected_nested_messages = {'task_to_compute', 'report_computed_task'},
            next_deadline            = self._parse_iso_date_to_timestamp("2017-12-01 11:00:10"),
        )
        self._test_last_stored_messages(
            expected_messages = [
                message.concents.ForceReportComputedTask,  # TODO: Remove in final step
                message.TaskToCompute,
                message.ReportComputedTask,
            ],
            task_id         = '1',
            subtask_id      = '8',
            timestamp       = "2017-12-01 10:59:00"
        )

        # STEP 2: Concent do not forces computed task report on the requestor with different or mixed key

        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = '',
                content_type                   = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(DIFFERENT_REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(len(response.content),       0)
        self.assertEqual(MessageAuth.objects.count(), 1)

        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = '',
                content_type                   = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(len(response.content),       0)
        self.assertEqual(MessageAuth.objects.count(), 1)

        # STEP 3: Concent forces computed task report on the requestor with correct key

        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = '',
                content_type                   = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        force_report_computed_task_from_view = load(
            response.content,
            REQUESTOR_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY,
            check_time = False,
        )

        self.assertEqual(response.status_code,                                                                  200)
        self.assertEqual(force_report_computed_task_from_view.timestamp,                                        self._parse_iso_date_to_timestamp("2017-12-01 11:00:05"))
        self.assertEqual(force_report_computed_task_from_view.report_computed_task.task_to_compute.timestamp,   self.force_report_computed_task.report_computed_task.task_to_compute.timestamp)
        self.assertEqual(force_report_computed_task_from_view.report_computed_task.task_to_compute,             self.force_report_computed_task.report_computed_task.task_to_compute)
        self.assertEqual(MessageAuth.objects.count(),                                                           2)

        # STEP 4: Concent do not accepts computed task due to lack of response from the requestor with different or mixed key

        with freeze_time("2017-12-01 11:00:15"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = '',
                content_type                   = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(DIFFERENT_REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(MessageAuth.objects.count(), 2)

        with freeze_time("2017-12-01 11:00:15"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = '',
                content_type                   = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(MessageAuth.objects.count(), 2)

        # STEP 5: Concent accepts computed task due to lack of response from the requestor with correct key

        with freeze_time("2017-12-01 11:00:15"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = '',
                content_type                   = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response.status_code,        200)
        self.assertEqual(MessageAuth.objects.count(), 3)

        message_auth = MessageAuth.objects.last()
        self.assertEqual(message_auth.message.type,               message.concents.ForceReportComputedTaskResponse.TYPE)
        self.assertEqual(message_auth.provider_public_key_bytes,  PROVIDER_PUBLIC_KEY)
        self.assertEqual(message_auth.requestor_public_key_bytes, REQUESTOR_PUBLIC_KEY)

        message_from_concent_to_provider = load(response.content, PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY, check_time=False)
        self.assertIsInstance(message_from_concent_to_provider,                                     message.concents.ForceReportComputedTaskResponse)
        self.assertEqual(message_from_concent_to_provider.timestamp,                                int(dateutil.parser.parse("2017-12-01 11:00:15").timestamp()))
        self.assertEqual(message_from_concent_to_provider.ack_report_computed_task.task_to_compute, self.deserialized_task_to_compute)

        self._test_subtask_state(
            task_id                  = '1',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.FORCING_REPORT,  # TODO: Should be REPORTED
            provider_key             = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            requestor_key            = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            expected_nested_messages = {'task_to_compute', 'report_computed_task'},  # TODO: Add ack_report_computed_task if REPORTED
            next_deadline            = self._parse_iso_date_to_timestamp("2017-12-01 11:00:10"),  # TODO: Should be removed if REPORTED
        )

        # STEP 6: Requestor do not receives task computation report verdict out of band due to lack of response with different or mixed key

        with freeze_time("2017-12-01 11:00:15"):
            response = self.client.post(
                reverse('core:receive_out_of_band'),
                data                           = '',
                content_type                   = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(DIFFERENT_REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(MessageAuth.objects.count(), 3)

        with freeze_time("2017-12-01 11:00:15"):
            response = self.client.post(
                reverse('core:receive_out_of_band'),
                data                           = '',
                content_type                   = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(MessageAuth.objects.count(), 3)

        # STEP 7: Requestor receives task computation report verdict out of band due to lack of response with correct key

        with freeze_time("2017-12-01 11:00:15"):
            response = self.client.post(
                reverse('core:receive_out_of_band'),
                data                           = '',
                content_type                   = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            )

        self.assertEqual(response.status_code,        200)
        self.assertEqual(MessageAuth.objects.count(), 4)

        message_auth = MessageAuth.objects.last()
        self.assertEqual(message_auth.message.type,               message.VerdictReportComputedTask.TYPE)
        self.assertEqual(message_auth.provider_public_key_bytes,  PROVIDER_PUBLIC_KEY)
        self.assertEqual(message_auth.requestor_public_key_bytes, REQUESTOR_PUBLIC_KEY)

        message_from_concent_to_requestor = load(
            response.content,
            REQUESTOR_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY,
            check_time = False
        )

        self.assertIsInstance(message_from_concent_to_requestor,                     message.VerdictReportComputedTask)
        self.assertGreaterEqual(message_from_concent_to_requestor.timestamp,         int(dateutil.parser.parse("2017-12-01 11:00:05").timestamp()))
        self.assertLessEqual(message_from_concent_to_requestor.timestamp,            int(dateutil.parser.parse("2017-12-01 11:00:15").timestamp()))
        self.assertEqual(message_from_concent_to_requestor.ack_report_computed_task, message_from_concent_to_provider.ack_report_computed_task)

        self._test_subtask_state(
            task_id                  = '1',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.FORCING_REPORT,  # TODO: Should be REPORTED
            provider_key             = b64encode(PROVIDER_PUBLIC_KEY).decode('ascii'),
            requestor_key            = b64encode(REQUESTOR_PUBLIC_KEY).decode('ascii'),
            expected_nested_messages = {'task_to_compute', 'report_computed_task'},  # TODO: Add ack_report_computed_task if REPORTED
            next_deadline            = self._parse_iso_date_to_timestamp("2017-12-01 11:00:10"),  # TODO: Should be removed if REPORTED
        )
        self._assert_client_count_is_equal(2)
