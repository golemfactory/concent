from base64 import b64encode

from django.test                    import override_settings
from django.urls                    import reverse
from freezegun                      import freeze_time

from golem_messages                 import message
from core.models                    import PendingResponse
from core.models                    import Subtask
from core.tests.utils import ConcentIntegrationTestCase
from core.tests.utils import parse_iso_date_to_timestamp
from common.constants                import ErrorCode
from common.testing_helpers          import generate_ecc_key_pair


(CONCENT_PRIVATE_KEY, CONCENT_PUBLIC_KEY) = generate_ecc_key_pair()


@override_settings(
    CONCENT_PRIVATE_KEY    = CONCENT_PRIVATE_KEY,
    CONCENT_PUBLIC_KEY     = CONCENT_PUBLIC_KEY,
    CONCENT_MESSAGING_TIME = 10,  # seconds
)
class ReportComputedTaskIntegrationTest(ConcentIntegrationTestCase):
    def test_provider_forces_computed_task_report_and_concent_immediately_sends_rejection_due_to_exceeded_deadline(self):
        # Expected message exchange:
        # Provider -> Concent:     MessageForceReportComputedTask
        # Concent  -> Provider:    MessageRejectReportComputedTask

        # STEP 1: Provider forces computed task report via Concent. Concent rejects computed task immediately when deadline is exceeded

        compute_task_def = self._get_deserialized_compute_task_def(
            task_id     = '1',
            deadline    = "2017-12-01 11:00:00"
        )

        task_to_compute = self._get_deserialized_task_to_compute(
            timestamp           = "2017-12-01 10:00:00",
            compute_task_def    = compute_task_def,
        )

        report_computed_task = self._get_deserialized_report_computed_task(
            timestamp = "2017-12-01 11:01:00",
            task_to_compute = task_to_compute,
        )

        serialized_force_report_computed_task = self._get_serialized_force_report_computed_task(
            timestamp = "2017-12-01 11:01:00",
            force_report_computed_task = self._get_deserialized_force_report_computed_task(
                timestamp               = "2017-12-01 11:01:00",
                report_computed_task    = report_computed_task
            ),
            provider_private_key = self.PROVIDER_PRIVATE_KEY
        )

        with freeze_time("2017-12-01 11:01:00"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_report_computed_task,
                content_type                        = 'application/octet-stream',
            )

        self._test_response(
            response_1,
            status          = 200,
            key             = self.PROVIDER_PRIVATE_KEY,
            message_type    = message.concents.ForceReportComputedTaskResponse,
            fields          = {
                'timestamp': parse_iso_date_to_timestamp("2017-12-01 11:01:00"),
                'reason':    message.concents.ForceReportComputedTaskResponse.REASON.SubtaskTimeout,
            }
        )
        self._assert_stored_message_counter_not_increased()

    def test_provider_forces_computed_task_report_and_requestor_sends_acknowledgement(self):
        # Expected message exchange:
        # Provider  -> Concent:    MessageForceReportComputedTask
        # Concent   -> Requestor:  MessageForceReportComputedTask
        # Requestor -> Concent:    MessageAckReportComputedTask
        # Concent   -> Provider:   MessageAckReportComputedTask

        # STEP 1: Provider forces computed task report via Concent

        compute_task_def = self._get_deserialized_compute_task_def(
            task_id     = '1',
            subtask_id  = '8',
            deadline    = "2017-12-01 11:00:00"
        )

        task_to_compute = self._get_deserialized_task_to_compute(
            timestamp           = "2017-12-01 10:00:00",
            compute_task_def    = compute_task_def,
        )

        report_computed_task = self._get_deserialized_report_computed_task(
            timestamp = "2017-12-01 10:59:00",
            task_to_compute = task_to_compute,
        )

        serialized_force_report_computed_task = self._get_serialized_force_report_computed_task(
            timestamp = "2017-12-01 10:59:00",
            force_report_computed_task = self._get_deserialized_force_report_computed_task(
                timestamp               = "2017-12-01 10:59:00",
                report_computed_task    = report_computed_task
            ),
            provider_private_key = self.PROVIDER_PRIVATE_KEY
        )

        with freeze_time("2017-12-01 10:59:00"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_report_computed_task,
                content_type                        = 'application/octet-stream',
            )

        self.assertEqual(response_1.status_code,  202)
        self.assertEqual(len(response_1.content), 0)

        self._assert_stored_message_counter_increased(increased_by = 2)
        self._test_subtask_state(
            task_id                  = '1',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.FORCING_REPORT,
            provider_key             = self._get_encoded_provider_public_key(),
            requestor_key            = self._get_encoded_requestor_public_key(),
            expected_nested_messages = {'task_to_compute', 'report_computed_task'},
            next_deadline=parse_iso_date_to_timestamp("2017-12-01 11:00:10"),
        )
        self._test_last_stored_messages(
            expected_messages = [
                message.TaskToCompute,
                message.ReportComputedTask,
            ],
            task_id         = '1',
            subtask_id      = '8',
        )
        self._test_undelivered_pending_responses(
            subtask_id                         = '8',
            client_public_key                  = self._get_encoded_requestor_public_key(),
            expected_pending_responses_receive = [
                PendingResponse.ResponseType.ForceReportComputedTask,
            ]
        )

        # STEP 2: Concent forces computed task report on the requestor

        with freeze_time("2017-12-01 11:00:05"):
            response_2 = self.client.post(
                reverse('core:receive'),
                data         = self._create_requestor_auth_message(),
                content_type = 'application/octet-stream',
            )

        self._test_response(
            response_2,
            status          = 200,
            key             = self.REQUESTOR_PRIVATE_KEY,
            message_type    = message.concents.ForceReportComputedTask,
            fields          = {
                'timestamp': parse_iso_date_to_timestamp("2017-12-01 11:00:05"),
                'report_computed_task.timestamp': parse_iso_date_to_timestamp("2017-12-01 10:59:00"),
                'report_computed_task.task_to_compute.compute_task_def':    compute_task_def,
            }
        )
        self._assert_stored_message_counter_not_increased()

        # STEP 3: Requestor accepts computed task via Concent
        serialized_ack_report_computed_task = self._get_serialized_ack_report_computed_task(
            timestamp="2017-12-01 11:00:05",
            ack_report_computed_task=self._get_deserialized_ack_report_computed_task(
                timestamp="2017-12-01 11:00:05",
                report_computed_task=report_computed_task,
                task_to_compute=task_to_compute
            ),
            requestor_private_key=self.REQUESTOR_PRIVATE_KEY
        )

        with freeze_time("2017-12-01 11:00:05"):
            response_3 = self.client.post(
                reverse('core:send'),
                data                           = serialized_ack_report_computed_task,
                content_type                   = 'application/octet-stream',
            )
        self._test_report_computed_task_in_database(report_computed_task)
        self.assertEqual(response_3.status_code,  202)
        self.assertEqual(len(response_3.content), 0)
        self._assert_stored_message_counter_increased(increased_by=1)
        self._test_subtask_state(
            task_id                  = '1',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.REPORTED,
            provider_key             = self._get_encoded_provider_public_key(),
            requestor_key            = self._get_encoded_requestor_public_key(),
            expected_nested_messages = {'task_to_compute', 'report_computed_task', 'ack_report_computed_task'},
        )
        self._test_last_stored_messages(
            expected_messages= [
                message.AckReportComputedTask,
            ],
            task_id         = '1',
            subtask_id      = '8',
        )
        self._test_undelivered_pending_responses(
            subtask_id                         = '8',
            client_public_key                  = self._get_encoded_provider_public_key(),
            expected_pending_responses_receive = [
                PendingResponse.ResponseType.ForceReportComputedTaskResponse,
            ]
        )

        # STEP 4: Concent passes computed task acceptance to the provider

        with freeze_time("2017-12-01 11:00:15"):
            response_4 = self.client.post(
                reverse('core:receive'),
                data         = self._create_provider_auth_message(),
                content_type = 'application/octet-stream',
            )

        self._test_response(
            response_4,
            status=200,
            key=self.PROVIDER_PRIVATE_KEY,
            message_type=message.concents.ForceReportComputedTaskResponse,
            fields={
                'reason': message.concents.ForceReportComputedTaskResponse.REASON.AckFromRequestor,
                'timestamp': parse_iso_date_to_timestamp("2017-12-01 11:00:15"),
                'reject_report_computed_task': None,
                'ack_report_computed_task.timestamp': parse_iso_date_to_timestamp("2017-12-01 11:00:05"),
                'ack_report_computed_task.report_computed_task.task_to_compute.compute_task_def': compute_task_def,
            }
        )
        self._assert_stored_message_counter_not_increased()

        self._assert_client_count_is_equal(2)

    def test_provider_forces_computed_task_report_and_requestor_sends_rejection_due_to_failed_computation(self):
        # Expected message exchange:
        # Provider  -> Concent:    MessageForceReportComputedTask
        # Concent   -> Requestor:  MessageForceReportComputedTask
        # Requestor -> Concent:    MessageRejectReportComputedTask (failed computation)
        # Concent   -> Provider:   MessageRejectReportComputedTask

        # STEP 1: Provider forces computed task report via Concent

        compute_task_def = self._get_deserialized_compute_task_def(
            task_id     = '1',
            subtask_id  = '8',
            deadline    = "2017-12-01 11:00:00"
        )

        task_to_compute = self._get_deserialized_task_to_compute(
            timestamp           = "2017-12-01 10:00:00",
            compute_task_def    = compute_task_def,
        )

        report_computed_task = self._get_deserialized_report_computed_task(
            timestamp = "2017-12-01 10:59:00",
            task_to_compute = task_to_compute,
        )

        serialized_force_report_computed_task = self._get_serialized_force_report_computed_task(
            timestamp = "2017-12-01 10:59:00",
            force_report_computed_task = self._get_deserialized_force_report_computed_task(
                timestamp               = "2017-12-01 10:59:00",
                report_computed_task    = report_computed_task
            ),
            provider_private_key = self.PROVIDER_PRIVATE_KEY
        )

        with freeze_time("2017-12-01 10:59:00"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_report_computed_task,
                content_type                        = 'application/octet-stream',
            )

        self.assertEqual(response_1.status_code,  202)
        self.assertEqual(len(response_1.content), 0)
        self._assert_stored_message_counter_increased(increased_by = 2)
        self._test_subtask_state(
            task_id                  = '1',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.FORCING_REPORT,
            provider_key             = self._get_encoded_provider_public_key(),
            requestor_key            = self._get_encoded_requestor_public_key(),
            expected_nested_messages = {'task_to_compute', 'report_computed_task'},
            next_deadline=parse_iso_date_to_timestamp("2017-12-01 11:00:10"),
        )
        self._test_last_stored_messages(
            expected_messages = [
                message.TaskToCompute,
                message.ReportComputedTask,
            ],
            task_id         = '1',
            subtask_id      = '8',
        )
        self._test_undelivered_pending_responses(
            subtask_id                         = '8',
            client_public_key                  = self._get_encoded_requestor_public_key(),
            expected_pending_responses_receive = [
                PendingResponse.ResponseType.ForceReportComputedTask,
            ]
        )

        # STEP 2: Concent forces computed task report on the requestor

        with freeze_time("2017-12-01 11:00:05"):
            response_2 = self.client.post(
                reverse('core:receive'),
                data         = self._create_requestor_auth_message(),
                content_type = 'application/octet-stream',
            )

        self._test_response(
            response_2,
            status          = 200,
            key             = self.REQUESTOR_PRIVATE_KEY,
            message_type    = message.concents.ForceReportComputedTask,
            fields          = {
                'timestamp': parse_iso_date_to_timestamp("2017-12-01 11:00:05"),
                'report_computed_task.task_to_compute.timestamp': parse_iso_date_to_timestamp("2017-12-01 10:00:00"),
                'report_computed_task.task_to_compute.compute_task_def':    compute_task_def,
            }
        )
        self._assert_stored_message_counter_not_increased()

        # STEP 3: Requestor rejects computed task due to CannotComputeTask or TaskFailure

        cannot_compute_task = self._get_deserialized_cannot_compute_task(
            timestamp       = "2017-12-01 10:30:00",
            task_to_compute = task_to_compute,
            reason          = message.tasks.CannotComputeTask.REASON.WrongKey
        )

        reject_report_computed_task = self._get_deserialized_reject_report_computed_task(
            timestamp           = "2017-12-01 11:00:05",
            cannot_compute_task = cannot_compute_task,
            task_to_compute=task_to_compute,
            reason=message.RejectReportComputedTask.REASON.GotMessageCannotComputeTask,
        )

        serialized_reject_report_computed_task = self._get_serialized_reject_report_computed_task(
            timestamp = "2017-12-01 11:00:05",
            reject_report_computed_task = reject_report_computed_task,
            requestor_private_key       = self.REQUESTOR_PRIVATE_KEY,
        )

        with freeze_time("2017-12-01 11:00:05"):
            response_3 = self.client.post(
                reverse('core:send'),
                data                            = serialized_reject_report_computed_task,
                content_type                    = 'application/octet-stream',
            )

        self.assertEqual(response_3.status_code,  202)
        self.assertEqual(len(response_3.content), 0)
        self._assert_stored_message_counter_increased(increased_by = 1)
        self._test_subtask_state(
            task_id                  = '1',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.FAILED,
            provider_key             = self._get_encoded_provider_public_key(),
            requestor_key            = self._get_encoded_requestor_public_key(),
            expected_nested_messages = {'task_to_compute', 'report_computed_task', 'reject_report_computed_task'},
        )
        self._test_last_stored_messages(
            expected_messages= [
                message.RejectReportComputedTask,
            ],
            task_id         = '1',
            subtask_id      = '8',
        )
        self._test_undelivered_pending_responses(
            subtask_id                         = '8',
            client_public_key                  = self._get_encoded_provider_public_key(),
            expected_pending_responses_receive = [
                PendingResponse.ResponseType.ForceReportComputedTaskResponse,
            ]
        )

        # STEP 4: Concent passes computed task rejection to the provider

        with freeze_time("2017-12-01 11:00:15"):
            response_4 = self.client.post(
                reverse('core:receive'),
                data                            = self._create_provider_auth_message(),
                content_type                    = 'application/octet-stream',
            )

        self._test_response(
            response_4,
            status=200,
            key=self.PROVIDER_PRIVATE_KEY,
            message_type=message.concents.ForceReportComputedTaskResponse,
            fields={
                'reason': message.concents.ForceReportComputedTaskResponse.REASON.RejectFromRequestor,
                'timestamp': parse_iso_date_to_timestamp("2017-12-01 11:00:15"),
                'ack_report_computed_task': None,
                'reject_report_computed_task.timestamp': parse_iso_date_to_timestamp("2017-12-01 11:00:05"),
                'reject_report_computed_task.cannot_compute_task.task_to_compute.timestamp': parse_iso_date_to_timestamp(
                    "2017-12-01 10:00:00"),
                'reject_report_computed_task.cannot_compute_task.task_to_compute.compute_task_def': compute_task_def,
            }
        )
        self._assert_stored_message_counter_not_increased()

        self._assert_client_count_is_equal(2)

    def test_provider_forces_computed_task_report_and_requestor_sends_rejection_due_to_exceeded_deadline(self):
        # Expected message exchange:
        # Provider  -> Concent:    MessageForceReportComputedTask
        # Concent   -> Requestor:  MessageForceReportComputedTask
        # Requestor -> Concent:    MessageRejectReportComputedTask (deadline exceeded)
        # Concent   -> Provider:   MessageAckReportComputedTask
        # Concent   -> Requestor:  MessageVerdictReportComputedTask

        # STEP 1: Provider forces computed task report via Concent

        compute_task_def = self._get_deserialized_compute_task_def(
            task_id     = '1',
            subtask_id  = '8',
            deadline    = "2017-12-01 11:00:00"
        )

        task_to_compute = self._get_deserialized_task_to_compute(
            timestamp           = "2017-12-01 10:00:00",
            compute_task_def    = compute_task_def,
        )

        report_computed_task = self._get_deserialized_report_computed_task(
            timestamp = "2017-12-01 10:59:00",
            task_to_compute = task_to_compute,
        )

        serialized_force_report_computed_task = self._get_serialized_force_report_computed_task(
            timestamp = "2017-12-01 10:59:00",
            force_report_computed_task = self._get_deserialized_force_report_computed_task(
                timestamp               = "2017-12-01 10:59:00",
                report_computed_task    = report_computed_task
            ),
            provider_private_key = self.PROVIDER_PRIVATE_KEY
        )

        with freeze_time("2017-12-01 10:59:00"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_report_computed_task,
                content_type                        = 'application/octet-stream',
            )

        self.assertEqual(response_1.status_code,  202)
        self.assertEqual(len(response_1.content), 0)
        self._assert_stored_message_counter_increased(increased_by = 2)
        self._test_subtask_state(
            task_id                  = '1',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.FORCING_REPORT,
            provider_key             = self._get_encoded_provider_public_key(),
            requestor_key            = self._get_encoded_requestor_public_key(),
            expected_nested_messages = {'task_to_compute', 'report_computed_task'},
            next_deadline=parse_iso_date_to_timestamp("2017-12-01 11:00:10"),
        )
        self._test_last_stored_messages(
            expected_messages = [
                message.TaskToCompute,
                message.ReportComputedTask,
            ],
            task_id         = '1',
            subtask_id      = '8',
        )
        self._test_undelivered_pending_responses(
            subtask_id                         = '8',
            client_public_key                  = self._get_encoded_requestor_public_key(),
            expected_pending_responses_receive = [
                PendingResponse.ResponseType.ForceReportComputedTask,
            ]
        )
        self._test_undelivered_pending_responses(
            subtask_id                         = '8',
            client_public_key                  = self._get_encoded_requestor_public_key(),
            expected_pending_responses_receive = [
                PendingResponse.ResponseType.ForceReportComputedTask,
            ]
        )

        # STEP 2: Concent forces computed task report on the requestor

        with freeze_time("2017-12-01 11:00:05"):
            response_2 = self.client.post(
                reverse('core:receive'),
                data         = self._create_requestor_auth_message(),
                content_type = 'application/octet-stream',
            )

        self._test_response(
            response_2,
            status          = 200,
            key             = self.REQUESTOR_PRIVATE_KEY,
            message_type    = message.concents.ForceReportComputedTask,
            fields          = {
                'timestamp': parse_iso_date_to_timestamp("2017-12-01 11:00:05"),
                'report_computed_task.task_to_compute.timestamp': parse_iso_date_to_timestamp("2017-12-01 10:00:00"),
                'report_computed_task.task_to_compute.compute_task_def':    compute_task_def,
            }
        )
        self._assert_stored_message_counter_not_increased()

        # STEP 3: Requestor rejects computed task claiming that the deadline has been exceeded

        reject_report_computed_task = self._get_deserialized_reject_report_computed_task(
            timestamp="2017-12-01 11:00:05",
            reason=message.RejectReportComputedTask.REASON.SubtaskTimeLimitExceeded,
            task_to_compute=task_to_compute,
        )

        serialized_reject_report_computed_task = self._get_serialized_reject_report_computed_task(
            timestamp = "2017-12-01 11:00:05",
            reject_report_computed_task = reject_report_computed_task,
            requestor_private_key       = self.REQUESTOR_PRIVATE_KEY,
        )

        with freeze_time("2017-12-01 11:00:05"):
            response_3 = self.client.post(
                reverse('core:send'),
                data                           = serialized_reject_report_computed_task,
                content_type                   = 'application/octet-stream',
            )

        self.assertEqual(response_3.status_code,                    202)
        self.assertEqual(len(response_3.content),                   0)
        self._assert_stored_message_counter_increased(increased_by = 1)
        self._test_subtask_state(
            task_id                     = '1',
            subtask_id                  = '8',
            subtask_state               = Subtask.SubtaskState.REPORTED,
            provider_key                = self._get_encoded_provider_public_key(),
            requestor_key               = self._get_encoded_requestor_public_key(),
            expected_nested_messages    = {'task_to_compute', 'report_computed_task', 'reject_report_computed_task'},
        )
        self._test_last_stored_messages(
            expected_messages= [
                message.RejectReportComputedTask,
            ],
            task_id         = '1',
            subtask_id      = '8',
        )
        self._test_undelivered_pending_responses(
            subtask_id                         = '8',
            client_public_key                  = self._get_encoded_provider_public_key(),
            client_public_key_out_of_band      = self._get_encoded_requestor_public_key(),
            expected_pending_responses_receive = [
                PendingResponse.ResponseType.ForceReportComputedTaskResponse,
            ],
            expected_pending_responses_receive_out_of_band = [
                PendingResponse.ResponseType.VerdictReportComputedTask,
            ]
        )

        # STEP 4: Concent overrides computed task rejection and sends acceptance message to the provider

        with freeze_time("2017-12-01 11:00:15"):
            response_4 = self.client.post(
                reverse('core:receive'),
                data                            = self._create_provider_auth_message(),
                content_type                    = 'application/octet-stream',
            )

        self._test_response(
            response_4,
            status=200,
            key=self.PROVIDER_PRIVATE_KEY,
            message_type=message.concents.ForceReportComputedTaskResponse,
            fields={
                'reason': message.concents.ForceReportComputedTaskResponse.REASON.ConcentAck,
                'timestamp': parse_iso_date_to_timestamp("2017-12-01 11:00:15"),
                'reject_report_computed_task': None,
                'ack_report_computed_task.timestamp': parse_iso_date_to_timestamp("2017-12-01 11:00:15"),
                'ack_report_computed_task.report_computed_task.task_to_compute.timestamp': parse_iso_date_to_timestamp(
                    "2017-12-01 10:00:00"
                ),
                'ack_report_computed_task.report_computed_task.task_to_compute.compute_task_def': compute_task_def,
            },
            nested_message_verifiable_by={
                'ack_report_computed_task': CONCENT_PUBLIC_KEY,
                'ack_report_computed_task.report_computed_task.task_to_compute': self.REQUESTOR_PUBLIC_KEY
            }
        )
        self._assert_stored_message_counter_not_increased()

        # STEP 5: Requestor receives computed task report verdict out of band due to an overridden decision

        with freeze_time("2017-12-01 11:00:15"):
            response_5 = self.client.post(
                reverse('core:receive_out_of_band'),
                data         = self._create_requestor_auth_message(),
                content_type = 'application/octet-stream',
            )

        self._test_response(
            response_5,
            status          = 200,
            key             = self.REQUESTOR_PRIVATE_KEY,
            message_type    = message.concents.VerdictReportComputedTask,
            fields          = {
                'timestamp': parse_iso_date_to_timestamp("2017-12-01 11:00:15"),
                'ack_report_computed_task.timestamp': parse_iso_date_to_timestamp("2017-12-01 11:00:15"),
                'ack_report_computed_task.report_computed_task.task_to_compute.timestamp': parse_iso_date_to_timestamp("2017-12-01 10:00:00"),
                'ack_report_computed_task.report_computed_task.task_to_compute.compute_task_def':    compute_task_def,
            },
            nested_message_verifiable_by={
                'ack_report_computed_task': CONCENT_PUBLIC_KEY,
                'ack_report_computed_task.report_computed_task.task_to_compute': self.REQUESTOR_PUBLIC_KEY
            }
        )
        self._assert_stored_message_counter_not_increased()

        self._assert_client_count_is_equal(2)

    def test_provider_forces_computed_task_report_and_requestor_does_not_respond(self):
        # Expected message exchange:
        # Provider  -> Concent:    MessageForceReportComputedTask
        # Concent   -> Requestor:  MessageForceReportComputedTask
        # Requestor -> Concent:    no response
        # Concent   -> Provider:   MessageAckReportComputedTask
        # Concent   -> Requestor:  MessageVerdictReportComputedTask

        # STEP 1: Provider forces computed task report via Concent
        compute_task_def = self._get_deserialized_compute_task_def(
            task_id     = '1',
            subtask_id  = '8',
            deadline    = "2017-12-01 11:00:00"
        )

        task_to_compute = self._get_deserialized_task_to_compute(
            timestamp           = "2017-12-01 10:00:00",
            compute_task_def    = compute_task_def,
        )

        report_computed_task = self._get_deserialized_report_computed_task(
            timestamp = "2017-12-01 10:59:00",
            task_to_compute = task_to_compute,
        )

        serialized_force_report_computed_task = self._get_serialized_force_report_computed_task(
            timestamp = "2017-12-01 10:59:00",
            force_report_computed_task = self._get_deserialized_force_report_computed_task(
                timestamp               = "2017-12-01 10:59:00",
                report_computed_task    = report_computed_task
            ),
            provider_private_key = self.PROVIDER_PRIVATE_KEY
        )

        with freeze_time("2017-12-01 10:59:00"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_report_computed_task,
                content_type                        = 'application/octet-stream',
            )

        self.assertEqual(response_1.status_code,  202)
        self.assertEqual(len(response_1.content), 0)

        self._assert_stored_message_counter_increased(increased_by = 2)
        self._test_subtask_state(
            task_id                  = '1',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.FORCING_REPORT,
            provider_key             = self._get_encoded_provider_public_key(),
            requestor_key            = self._get_encoded_requestor_public_key(),
            expected_nested_messages = {'task_to_compute', 'report_computed_task'},
            next_deadline=parse_iso_date_to_timestamp("2017-12-01 11:00:10"),
        )
        self._test_last_stored_messages(
            expected_messages = [
                message.TaskToCompute,
                message.ReportComputedTask,
            ],
            task_id         = '1',
            subtask_id      = '8',
        )
        self._test_undelivered_pending_responses(
            subtask_id                         = '8',
            client_public_key                  = self._get_encoded_requestor_public_key(),
            expected_pending_responses_receive = [
                PendingResponse.ResponseType.ForceReportComputedTask,
            ]
        )

        # STEP 2: Concent forces computed task report on the requestor

        with freeze_time("2017-12-01 11:00:05"):
            response_2 = self.client.post(
                reverse('core:receive'),
                data         = self._create_requestor_auth_message(),
                content_type = 'application/octet-stream',
            )

        self._test_response(
            response_2,
            status          = 200,
            key             = self.REQUESTOR_PRIVATE_KEY,
            message_type    = message.concents.ForceReportComputedTask,
            fields          = {
                'timestamp': parse_iso_date_to_timestamp("2017-12-01 11:00:05"),
                'report_computed_task.task_to_compute.timestamp': parse_iso_date_to_timestamp("2017-12-01 10:00:00"),
                'report_computed_task.task_to_compute.compute_task_def':    compute_task_def,
            }
        )
        self._assert_stored_message_counter_not_increased()

        # STEP 3: Concent accepts computed task due to lack of response from the requestor

        with freeze_time("2017-12-01 11:00:10"):
            response_3 = self.client.post(
                reverse('core:receive'),
                data                            = self._create_provider_auth_message(),
                content_type                    = 'application/octet-stream',
            )

        self._test_response(
            response_3,
            status=200,
            key=self.PROVIDER_PRIVATE_KEY,
            message_type=message.concents.ForceReportComputedTaskResponse,
            fields={
                'reason': message.concents.ForceReportComputedTaskResponse.REASON.ConcentAck,
                'timestamp': parse_iso_date_to_timestamp("2017-12-01 11:00:10"),
                'reject_report_computed_task': None,
                'ack_report_computed_task.timestamp': parse_iso_date_to_timestamp("2017-12-01 11:00:10"),
                'ack_report_computed_task.report_computed_task.task_to_compute.timestamp': parse_iso_date_to_timestamp(
                    "2017-12-01 10:00:00"
                ),
                'ack_report_computed_task.report_computed_task.task_to_compute.compute_task_def': compute_task_def,
            },
            nested_message_verifiable_by={
                'ack_report_computed_task': CONCENT_PUBLIC_KEY,
                'ack_report_computed_task.report_computed_task.task_to_compute': self.REQUESTOR_PUBLIC_KEY
            }
        )
        self._assert_stored_message_counter_not_increased()
        self._test_subtask_state(
            task_id                     = '1',
            subtask_id                  = '8',
            subtask_state               = Subtask.SubtaskState.REPORTED,
            provider_key                = self._get_encoded_provider_public_key(),
            requestor_key               = self._get_encoded_requestor_public_key(),
            expected_nested_messages    = {'task_to_compute', 'report_computed_task'},
            next_deadline               = None,
        )

        # STEP 4: Requestor receives task computation report verdict out of band due to lack of response

        with freeze_time("2017-12-01 11:00:11"):
            response_4 = self.client.post(
                reverse('core:receive_out_of_band'),
                data                            = self._create_requestor_auth_message(),
                content_type                    = 'application/octet-stream',
            )

        self._test_response(
            response_4,
            status          = 200,
            key             = self.REQUESTOR_PRIVATE_KEY,
            message_type    = message.concents.VerdictReportComputedTask,
            fields          = {
                'timestamp': parse_iso_date_to_timestamp("2017-12-01 11:00:11"),
                'ack_report_computed_task.timestamp': parse_iso_date_to_timestamp("2017-12-01 11:00:11"),
                'ack_report_computed_task.report_computed_task.task_to_compute.timestamp': parse_iso_date_to_timestamp("2017-12-01 10:00:00"),
                'ack_report_computed_task.report_computed_task.task_to_compute.compute_task_def':    compute_task_def,
            },
            nested_message_verifiable_by={
                'ack_report_computed_task': CONCENT_PUBLIC_KEY,
                'ack_report_computed_task.report_computed_task.task_to_compute': self.REQUESTOR_PUBLIC_KEY
            }
        )
        self._assert_stored_message_counter_not_increased()

        self._assert_client_count_is_equal(2)

    def test_provider_forces_computed_task_report_twice_and_concent_returns_400_error(self):
        """
        Tests if on provider ForceReportComputedTask message Concent will return HTTP 400 error
        if ForceReportComputedTask was already sent by this provider.

        Expected message exchange:
        Provider -> Concent:    ForceReportComputedTask
        Concent   -> Provider:  HTTP 400 error.
        """

        # STEP 1: Provider forces computed task report via Concent
        compute_task_def = self._get_deserialized_compute_task_def(
            task_id     = '1',
            subtask_id  = '8',
            deadline    = "2017-12-01 11:00:00"
        )

        task_to_compute = self._get_deserialized_task_to_compute(
            timestamp           = "2017-12-01 10:00:00",
            compute_task_def    = compute_task_def,
        )

        report_computed_task = self._get_deserialized_report_computed_task(
            timestamp = "2017-12-01 10:59:00",
            task_to_compute = task_to_compute,
        )

        serialized_force_report_computed_task = self._get_serialized_force_report_computed_task(
            timestamp = "2017-12-01 10:59:00",
            force_report_computed_task = self._get_deserialized_force_report_computed_task(
                timestamp               = "2017-12-01 10:59:00",
                report_computed_task    = report_computed_task
            ),
            provider_private_key = self.PROVIDER_PRIVATE_KEY
        )

        with freeze_time("2017-12-01 10:59:00"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_report_computed_task,
                content_type                        = 'application/octet-stream',
            )

        self.assertEqual(response_1.status_code,  202)
        self.assertEqual(len(response_1.content), 0)
        self._assert_stored_message_counter_increased(increased_by = 2)
        self._test_subtask_state(
            task_id                  = '1',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.FORCING_REPORT,
            provider_key             = self._get_encoded_provider_public_key(),
            requestor_key            = self._get_encoded_requestor_public_key(),
            expected_nested_messages = {'task_to_compute', 'report_computed_task'},
            next_deadline=parse_iso_date_to_timestamp("2017-12-01 11:00:10"),
        )
        self._test_last_stored_messages(
            expected_messages = [
                message.TaskToCompute,
                message.ReportComputedTask,
            ],
            task_id         = '1',
            subtask_id      = '8',
        )
        self._test_undelivered_pending_responses(
            subtask_id                         = '8',
            client_public_key                  = self._get_encoded_requestor_public_key(),
            expected_pending_responses_receive = [
                PendingResponse.ResponseType.ForceReportComputedTask,
            ]
        )

        # STEP 2: Provider forces computed task report via Concent again
        with freeze_time("2017-12-01 10:59:00"):
            response_2 = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_report_computed_task,
                content_type                        = 'application/octet-stream',
            )
        self._test_400_response(
            response_2,
            error_code=ErrorCode.SUBTASK_DUPLICATE_REQUEST,
        )
        self._assert_stored_message_counter_not_increased()

        self._assert_client_count_is_equal(2)

    def test_requestor_sends_ack_report_computed_task_but_provider_did_not_ask_for_it(self):
        """
        Tests if on request AckReportComputedTask message Concent will return HTTP 400 error
        if ForceReportComputedTask was not sent by provider.

        Expected message exchange:
        Requestor -> Concent:    AckReportComputedTask
        Concent   -> Requestor:  HTTP 400 error.
        """
        # STEP 1: Requestor accepts computed task via Concent

        compute_task_def = self._get_deserialized_compute_task_def(
            task_id     = '1',
            deadline    = "2017-12-01 11:00:00"
        )

        task_to_compute = self._get_deserialized_task_to_compute(
            timestamp           = "2017-12-01 10:00:00",
            compute_task_def    = compute_task_def,
        )

        serialized_ack_report_computed_task = self._get_serialized_ack_report_computed_task(
            timestamp = "2017-12-01 11:00:05",
            ack_report_computed_task = self._get_deserialized_ack_report_computed_task(
                timestamp = "2017-12-01 11:00:05",
                subtask_id = '1',
                task_to_compute = task_to_compute
            ),
            requestor_private_key = self.REQUESTOR_PRIVATE_KEY
        )

        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:send'),
                data                           = serialized_ack_report_computed_task,
                content_type                   = 'application/octet-stream',
            )
        self._test_400_response(
            response,
            error_code=ErrorCode.QUEUE_COMMUNICATION_NOT_STARTED,
        )
        self._assert_stored_message_counter_not_increased()

        self._assert_client_count_is_equal(0)

    def test_requestor_sends_reject_report_computed_task_but_provider_did_not_ask_for_it(self):
        """
        Tests if on request RejectReportComputedTask message Concent will return HTTP 400 error
        if ForceReportComputedTask was not sent by provider.

        Expected message exchange:
        Requestor -> Concent:    RejectReportComputedTask
        Concent   -> Requestor:  HTTP 400 error.
        """
        # STEP 1: Requestor accepts computed task via Concent

        compute_task_def = self._get_deserialized_compute_task_def(
            task_id     = '1',
            deadline    = "2017-12-01 11:00:00"
        )

        task_to_compute = self._get_deserialized_task_to_compute(
            timestamp           = "2017-12-01 10:00:00",
            compute_task_def    = compute_task_def,
        )

        reject_report_computed_task = self._get_deserialized_reject_report_computed_task(
            timestamp           = "2017-12-01 11:00:05",
            task_to_compute=task_to_compute,
            reason              = message.RejectReportComputedTask.REASON.SubtaskTimeLimitExceeded,
        )

        serialized_reject_report_computed_task = self._get_serialized_reject_report_computed_task(
            timestamp = "2017-12-01 11:00:05",
            reject_report_computed_task = reject_report_computed_task,
            requestor_private_key       = self.REQUESTOR_PRIVATE_KEY,
        )

        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:send'),
                data                           = serialized_reject_report_computed_task,
                content_type                   = 'application/octet-stream',
            )
        self._test_400_response(
            response,
            error_code=ErrorCode.QUEUE_COMMUNICATION_NOT_STARTED,
        )
        self._assert_stored_message_counter_not_increased()

        self._assert_client_count_is_equal(0)

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

        compute_task_def = self._get_deserialized_compute_task_def(
            task_id     = '1',
            subtask_id  = '8',
            deadline    = "2017-12-01 11:00:00"
        )

        task_to_compute = self._get_deserialized_task_to_compute(
            timestamp           = "2017-12-01 10:00:00",
            compute_task_def    = compute_task_def,
        )

        report_computed_task = self._get_deserialized_report_computed_task(
            timestamp = "2017-12-01 10:59:00",
            task_to_compute = task_to_compute,
        )

        serialized_force_report_computed_task = self._get_serialized_force_report_computed_task(
            timestamp = "2017-12-01 10:59:00",
            force_report_computed_task = self._get_deserialized_force_report_computed_task(
                timestamp               = "2017-12-01 10:59:00",
                report_computed_task    = report_computed_task
            ),
            provider_private_key = self.PROVIDER_PRIVATE_KEY
        )

        with freeze_time("2017-12-01 10:59:00"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_report_computed_task,
                content_type                        = 'application/octet-stream',
            )

        self.assertEqual(response_1.status_code,  202)
        self.assertEqual(len(response_1.content), 0)
        self._assert_stored_message_counter_increased(increased_by = 2)
        self._test_subtask_state(
            task_id                  = '1',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.FORCING_REPORT,
            provider_key             = self._get_encoded_provider_public_key(),
            requestor_key            = self._get_encoded_requestor_public_key(),
            expected_nested_messages = {'task_to_compute', 'report_computed_task'},
            next_deadline=parse_iso_date_to_timestamp("2017-12-01 11:00:10"),
        )
        self._test_last_stored_messages(
            expected_messages = [
                message.TaskToCompute,
                message.ReportComputedTask,
            ],
            task_id         = '1',
            subtask_id      = '8',
        )
        self._test_undelivered_pending_responses(
            subtask_id                         = '8',
            client_public_key                  = self._get_encoded_requestor_public_key(),
            expected_pending_responses_receive = [
                PendingResponse.ResponseType.ForceReportComputedTask,
            ]
        )

        # STEP 2: Concent forces computed task report on the requestor

        with freeze_time("2017-12-01 11:00:05"):
            response_2 = self.client.post(
                reverse('core:receive'),
                data         = self._create_requestor_auth_message(),
                content_type = 'application/octet-stream',
            )

        self._test_response(
            response_2,
            status          = 200,
            key             = self.REQUESTOR_PRIVATE_KEY,
            message_type    = message.concents.ForceReportComputedTask,
            fields          = {
                'timestamp': parse_iso_date_to_timestamp("2017-12-01 11:00:05"),
                'report_computed_task.task_to_compute.timestamp': parse_iso_date_to_timestamp("2017-12-01 10:00:00"),
                'report_computed_task.task_to_compute.compute_task_def':    compute_task_def,
            }
        )
        self._assert_stored_message_counter_not_increased()

        # STEP 3: Requestor accepts computed task via Concent
        serialized_ack_report_computed_task = self._get_serialized_ack_report_computed_task(
            timestamp="2017-12-01 11:00:05",
            ack_report_computed_task=self._get_deserialized_ack_report_computed_task(
                timestamp="2017-12-01 11:00:05",
                report_computed_task=report_computed_task,
                task_to_compute=task_to_compute
            ),
            requestor_private_key=self.REQUESTOR_PRIVATE_KEY
        )

        with freeze_time("2017-12-01 11:00:05"):
            response_3 = self.client.post(
                reverse('core:send'),
                data                           = serialized_ack_report_computed_task,
                content_type                   = 'application/octet-stream',
            )

        self.assertEqual(response_3.status_code,  202)
        self.assertEqual(len(response_3.content), 0)
        self._assert_stored_message_counter_increased(increased_by=1)
        self._test_subtask_state(
            task_id                  = '1',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.REPORTED,
            provider_key             = self._get_encoded_provider_public_key(),
            requestor_key            = self._get_encoded_requestor_public_key(),
            expected_nested_messages = {'task_to_compute', 'report_computed_task', 'ack_report_computed_task'},
        )
        self._test_last_stored_messages(
            expected_messages= [
                message.AckReportComputedTask,
            ],
            task_id         = '1',
            subtask_id      = '8',
        )
        self._test_undelivered_pending_responses(
            subtask_id                         = '8',
            client_public_key                  = self._get_encoded_provider_public_key(),
            expected_pending_responses_receive = [
                PendingResponse.ResponseType.ForceReportComputedTaskResponse,
            ]
        )

        # STEP 4: Requestor rejects computed task via Concent
        reject_report_computed_task = self._get_deserialized_reject_report_computed_task(
            reason=None,
            timestamp           = "2017-12-01 11:00:05",
            task_to_compute=task_to_compute,
        )

        serialized_reject_report_computed_task = self._get_serialized_reject_report_computed_task(
            timestamp = "2017-12-01 11:00:05",
            reject_report_computed_task = reject_report_computed_task,
            requestor_private_key       = self.REQUESTOR_PRIVATE_KEY,
        )

        with freeze_time("2017-12-01 11:00:05"):
            response_4 = self.client.post(
                reverse('core:send'),
                data                           = serialized_reject_report_computed_task,
                content_type                   = 'application/octet-stream',
            )
        self._test_400_response(
            response_4,
            error_code=ErrorCode.QUEUE_WRONG_STATE,
        )
        self._assert_stored_message_counter_not_increased()

        self._assert_client_count_is_equal(2)

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

        compute_task_def = self._get_deserialized_compute_task_def(
            task_id     = '1',
            subtask_id  = '8',
            deadline    = "2017-12-01 11:00:00"
        )

        task_to_compute = self._get_deserialized_task_to_compute(
            timestamp           = "2017-12-01 10:00:00",
            compute_task_def    = compute_task_def,
        )

        report_computed_task = self._get_deserialized_report_computed_task(
            timestamp = "2017-12-01 10:59:00",
            task_to_compute = task_to_compute,
        )

        serialized_force_report_computed_task = self._get_serialized_force_report_computed_task(
            timestamp = "2017-12-01 10:59:00",
            force_report_computed_task = self._get_deserialized_force_report_computed_task(
                timestamp               = "2017-12-01 10:59:00",
                report_computed_task    = report_computed_task
            ),
            provider_private_key = self.PROVIDER_PRIVATE_KEY
        )

        with freeze_time("2017-12-01 10:59:00"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_report_computed_task,
                content_type                        = 'application/octet-stream',
            )

        self.assertEqual(response_1.status_code,  202)
        self.assertEqual(len(response_1.content), 0)
        self._assert_stored_message_counter_increased(increased_by = 2)
        self._test_subtask_state(
            task_id                  = '1',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.FORCING_REPORT,
            provider_key             = self._get_encoded_provider_public_key(),
            requestor_key            = self._get_encoded_requestor_public_key(),
            expected_nested_messages = {'task_to_compute', 'report_computed_task'},
            next_deadline=parse_iso_date_to_timestamp("2017-12-01 11:00:10"),
        )
        self._test_last_stored_messages(
            expected_messages = [
                message.TaskToCompute,
                message.ReportComputedTask,
            ],
            task_id         = '1',
            subtask_id      = '8',
        )
        self._test_undelivered_pending_responses(
            subtask_id                         = '8',
            client_public_key                  = self._get_encoded_requestor_public_key(),
            expected_pending_responses_receive = [
                PendingResponse.ResponseType.ForceReportComputedTask,
            ]
        )

        # STEP 2: Concent forces computed task report on the requestor

        with freeze_time("2017-12-01 11:00:05"):
            response_2 = self.client.post(
                reverse('core:receive'),
                data         = self._create_requestor_auth_message(),
                content_type = 'application/octet-stream',
            )

        self._test_response(
            response_2,
            status          = 200,
            key             = self.REQUESTOR_PRIVATE_KEY,
            message_type    = message.concents.ForceReportComputedTask,
            fields          = {
                'timestamp': parse_iso_date_to_timestamp("2017-12-01 11:00:05"),
                'report_computed_task.task_to_compute.timestamp': parse_iso_date_to_timestamp("2017-12-01 10:00:00"),
                'report_computed_task.task_to_compute.compute_task_def':    compute_task_def,
            }
        )
        self._assert_stored_message_counter_not_increased()

        # STEP 3: Requestor rejects computed task via Concent

        reject_report_computed_task = self._get_deserialized_reject_report_computed_task(
            timestamp="2017-12-01 11:00:05",
            reason=message.RejectReportComputedTask.REASON.SubtaskTimeLimitExceeded,
            task_to_compute=task_to_compute,
        )

        serialized_reject_report_computed_task = self._get_serialized_reject_report_computed_task(
            timestamp = "2017-12-01 11:00:05",
            reject_report_computed_task = reject_report_computed_task,
            requestor_private_key       = self.REQUESTOR_PRIVATE_KEY,
        )

        with freeze_time("2017-12-01 11:00:05"):
            response_3 = self.client.post(
                reverse('core:send'),
                data                           = serialized_reject_report_computed_task,
                content_type                   = 'application/octet-stream',
            )

        self.assertEqual(response_3.status_code,  202)
        self._assert_stored_message_counter_increased(increased_by = 1)
        self._test_subtask_state(
            task_id                  = '1',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.REPORTED,
            provider_key             = self._get_encoded_provider_public_key(),
            requestor_key            = self._get_encoded_requestor_public_key(),
            expected_nested_messages = {'task_to_compute', 'report_computed_task', 'reject_report_computed_task'},
        )
        self._test_last_stored_messages(
            expected_messages= [
                message.RejectReportComputedTask,
            ],
            task_id         = '1',
            subtask_id      = '8',
        )
        self._test_undelivered_pending_responses(
            subtask_id                         = '8',
            client_public_key                  = self._get_encoded_provider_public_key(),
            client_public_key_out_of_band      = self._get_encoded_requestor_public_key(),
            expected_pending_responses_receive = [
                PendingResponse.ResponseType.ForceReportComputedTaskResponse,
            ],
            expected_pending_responses_receive_out_of_band = [
                PendingResponse.ResponseType.VerdictReportComputedTask,
            ]
        )

        # STEP 4: Requestor accepts computed task via Concent

        serialized_ack_report_computed_task = self._get_serialized_ack_report_computed_task(
            timestamp = "2017-12-01 11:00:05",
            ack_report_computed_task = self._get_deserialized_ack_report_computed_task(
                timestamp       = "2017-12-01 11:00:05",
                subtask_id      = '1',
                task_to_compute = task_to_compute
            ),
            requestor_private_key = self.REQUESTOR_PRIVATE_KEY
        )

        with freeze_time("2017-12-01 11:00:05"):
            response_4 = self.client.post(
                reverse('core:send'),
                data                           = serialized_ack_report_computed_task,
                content_type                   = 'application/octet-stream',
            )
        self._test_400_response(
            response_4,
            error_code=ErrorCode.QUEUE_WRONG_STATE,
        )
        self._assert_stored_message_counter_not_increased()

        self._assert_client_count_is_equal(2)

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

        compute_task_def = self._get_deserialized_compute_task_def(
            task_id     = '1',
            subtask_id  = '8',
            deadline    = "2017-12-01 11:00:00"
        )

        task_to_compute = self._get_deserialized_task_to_compute(
            timestamp           = "2017-12-01 10:00:00",
            compute_task_def    = compute_task_def,
        )

        report_computed_task = self._get_deserialized_report_computed_task(
            timestamp = "2017-12-01 10:59:00",
            task_to_compute = task_to_compute,
        )

        serialized_force_report_computed_task = self._get_serialized_force_report_computed_task(
            timestamp = "2017-12-01 10:59:00",
            force_report_computed_task = self._get_deserialized_force_report_computed_task(
                timestamp               = "2017-12-01 10:59:00",
                report_computed_task    = report_computed_task
            ),
            provider_private_key = self.PROVIDER_PRIVATE_KEY
        )

        with freeze_time("2017-12-01 10:59:00"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_report_computed_task,
                content_type                        = 'application/octet-stream',
            )

        self.assertEqual(response_1.status_code,  202)
        self.assertEqual(len(response_1.content), 0)
        self._assert_stored_message_counter_increased(increased_by = 2)
        self._test_subtask_state(
            task_id                  = '1',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.FORCING_REPORT,
            provider_key             = self._get_encoded_provider_public_key(),
            requestor_key            = self._get_encoded_requestor_public_key(),
            expected_nested_messages = {'task_to_compute', 'report_computed_task'},
            next_deadline=parse_iso_date_to_timestamp("2017-12-01 11:00:10"),
        )
        self._test_last_stored_messages(
            expected_messages = [
                message.TaskToCompute,
                message.ReportComputedTask,
            ],
            task_id         = '1',
            subtask_id      = '8',
        )
        self._test_undelivered_pending_responses(
            subtask_id                         = '8',
            client_public_key                  = self._get_encoded_requestor_public_key(),
            expected_pending_responses_receive = [
                PendingResponse.ResponseType.ForceReportComputedTask,
            ]
        )

        # STEP 2: Concent forces computed task report on the requestor

        with freeze_time("2017-12-01 11:00:05"):
            response_2 = self.client.post(
                reverse('core:receive'),
                data         = self._create_requestor_auth_message(),
                content_type = 'application/octet-stream',
            )

        self._test_response(
            response_2,
            status          = 200,
            key             = self.REQUESTOR_PRIVATE_KEY,
            message_type    = message.concents.ForceReportComputedTask,
            fields          = {
                'timestamp': parse_iso_date_to_timestamp("2017-12-01 11:00:05"),
                'report_computed_task.task_to_compute.timestamp': parse_iso_date_to_timestamp("2017-12-01 10:00:00"),
                'report_computed_task.task_to_compute.compute_task_def':    compute_task_def,
            }
        )
        self._assert_stored_message_counter_not_increased()

        # STEP 3: Requestor accepts computed task via Concent after deadline

        serialized_ack_report_computed_task = self._get_serialized_ack_report_computed_task(
            timestamp = "2017-12-01 11:00:15",
            ack_report_computed_task = self._get_deserialized_ack_report_computed_task(
                timestamp       = "2017-12-01 11:00:15",
                subtask_id      = '1',
                task_to_compute = task_to_compute
            ),
            requestor_private_key = self.REQUESTOR_PRIVATE_KEY
        )

        with freeze_time("2017-12-01 11:00:15"):
            response_3 = self.client.post(
                reverse('core:send'),
                data                           = serialized_ack_report_computed_task,
                content_type                   = 'application/octet-stream',
            )
        self._test_400_response(
            response_3,
            error_code=ErrorCode.QUEUE_TIMEOUT,
        )
        self._assert_stored_message_counter_not_increased()

        self._assert_client_count_is_equal(2)

    def test_requestor_sends_wrong_reject_report_computed_task_multiple_time(self):
        """
        Tests if on request RejectReportComputedTask message Concent will return HTTP 400 error

        Expected message exchange:
        Provider  -> Concent:    ForceReportComputedTask
        Requestor -> Concent:    RejectReportComputedTask (CannotComputeTask and TaskFailure at the same time)
        Concent   -> Requestor:  HTTP 400 error.
        Requestor -> Concent:    RejectReportComputedTask (GotMessageCannotComputeTask REASON, but no CannotComputeTask)
        Concent   -> Requestor:  HTTP 400 error.
        Requestor -> Concent:    RejectReportComputedTask (GotMessageTaskFailure REASON, but no TaskFailure)
        Concent   -> Requestor:  HTTP 400 error.
        Requestor -> Concent:    RejectReportComputedTask (SubtaskTimeLimitExceeded REASON, with TaskFailure)
        Concent   -> Requestor:  HTTP 400 error.
        """

        # STEP 1: Provider forces computed task report via Concent

        compute_task_def = self._get_deserialized_compute_task_def(
            task_id     = '1',
            subtask_id  = '8',
            deadline    = "2017-12-01 11:00:00"
        )

        task_to_compute = self._get_deserialized_task_to_compute(
            timestamp           = "2017-12-01 10:00:00",
            compute_task_def    = compute_task_def,
        )

        report_computed_task = self._get_deserialized_report_computed_task(
            timestamp = "2017-12-01 10:59:00",
            task_to_compute = task_to_compute,
        )

        serialized_force_report_computed_task = self._get_serialized_force_report_computed_task(
            timestamp = "2017-12-01 10:59:00",
            force_report_computed_task = self._get_deserialized_force_report_computed_task(
                timestamp               = "2017-12-01 10:59:00",
                report_computed_task    = report_computed_task
            ),
            provider_private_key = self.PROVIDER_PRIVATE_KEY
        )

        with freeze_time("2017-12-01 10:59:00"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_report_computed_task,
                content_type                        = 'application/octet-stream',
            )

        self.assertEqual(response_1.status_code,  202)
        self.assertEqual(len(response_1.content), 0)
        self._assert_stored_message_counter_increased(increased_by = 2)
        self._test_subtask_state(
            task_id                  = '1',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.FORCING_REPORT,
            provider_key             = self._get_encoded_provider_public_key(),
            requestor_key            = self._get_encoded_requestor_public_key(),
            expected_nested_messages = {'task_to_compute', 'report_computed_task'},
            next_deadline=parse_iso_date_to_timestamp("2017-12-01 11:00:10"),
        )
        self._test_last_stored_messages(
            expected_messages = [
                message.TaskToCompute,
                message.ReportComputedTask,
            ],
            task_id         = '1',
            subtask_id      = '8',
        )
        self._test_undelivered_pending_responses(
            subtask_id                         = '8',
            client_public_key                  = self._get_encoded_requestor_public_key(),
            expected_pending_responses_receive = [
                PendingResponse.ResponseType.ForceReportComputedTask,
            ]
        )

        # STEP 2: Concent forces computed task report on the requestor

        with freeze_time("2017-12-01 11:00:05"):
            response_2 = self.client.post(
                reverse('core:receive'),
                data         = self._create_requestor_auth_message(),
                content_type = 'application/octet-stream',
            )

        self._test_response(
            response_2,
            status          = 200,
            key             = self.REQUESTOR_PRIVATE_KEY,
            message_type    = message.concents.ForceReportComputedTask,
            fields          = {
                'timestamp': parse_iso_date_to_timestamp("2017-12-01 11:00:05"),
                'report_computed_task.task_to_compute.timestamp': parse_iso_date_to_timestamp("2017-12-01 10:00:00"),
                'report_computed_task.task_to_compute.compute_task_def':    compute_task_def,
            }
        )
        self._assert_stored_message_counter_not_increased()

        # STEP 3: Requestor rejects computed task via Concent with CannotComputeTask and TaskFailure at the same time

        reject_report_computed_task = self._get_deserialized_reject_report_computed_task(
            timestamp="2017-12-01 11:00:09",
            cannot_compute_task=message.tasks.CannotComputeTask(),
            task_failure=message.tasks.TaskFailure(),
            reason=message.RejectReportComputedTask.REASON.SubtaskTimeLimitExceeded,
            task_to_compute=task_to_compute,
        )

        serialized_reject_report_computed_task = self._get_serialized_reject_report_computed_task(
            timestamp="2017-12-01 11:00:09",
            reject_report_computed_task=reject_report_computed_task,
            requestor_private_key=self.REQUESTOR_PRIVATE_KEY,
        )

        with freeze_time("2017-12-01 11:00:09"):
            response_3 = self.client.post(
                reverse('core:send'),
                data=serialized_reject_report_computed_task,
                content_type='application/octet-stream',
            )
        self._test_400_response(
            response_3,
            error_code=ErrorCode.MESSAGE_INVALID,
        )
        self._assert_stored_message_counter_not_increased()

        self._assert_client_count_is_equal(2)

        # STEP 4: Requestor rejects computed task via Concent with GotMessageCannotComputeTask REASON, but without CannotComputeTask

        reject_report_computed_task = self._get_deserialized_reject_report_computed_task(
            timestamp="2017-12-01 11:00:09",
            reason=message.RejectReportComputedTask.REASON.GotMessageCannotComputeTask,
            task_to_compute=task_to_compute,
        )

        serialized_reject_report_computed_task = self._get_serialized_reject_report_computed_task(
            timestamp="2017-12-01 11:00:09",
            reject_report_computed_task=reject_report_computed_task,
            requestor_private_key=self.REQUESTOR_PRIVATE_KEY,
        )

        with freeze_time("2017-12-01 11:00:09"):
            response_4 = self.client.post(
                reverse('core:send'),
                data=serialized_reject_report_computed_task,
                content_type='application/octet-stream',
            )
        self._test_400_response(
            response_4,
            error_code=ErrorCode.MESSAGE_INVALID,
        )
        self._assert_stored_message_counter_not_increased()

        # STEP 5: Requestor rejects computed task via Concent with GotMessageTaskFailure REASON, but without TaskFailure

        reject_report_computed_task = self._get_deserialized_reject_report_computed_task(
            timestamp="2017-12-01 11:00:09",
            reason=message.RejectReportComputedTask.REASON.GotMessageTaskFailure,
            task_to_compute=task_to_compute,
        )

        serialized_reject_report_computed_task = self._get_serialized_reject_report_computed_task(
            timestamp="2017-12-01 11:00:09",
            reject_report_computed_task=reject_report_computed_task,
            requestor_private_key=self.REQUESTOR_PRIVATE_KEY,
        )

        with freeze_time("2017-12-01 11:00:09"):
            response_5 = self.client.post(
                reverse('core:send'),
                data=serialized_reject_report_computed_task,
                content_type='application/octet-stream',
            )
        self._test_400_response(
            response_5,
            error_code=ErrorCode.MESSAGE_INVALID,
        )
        self._assert_stored_message_counter_not_increased()

        # STEP 6: Requestor rejects computed task via Concent with SubtaskTimeLimitExceeded REASON and TaskFailure message

        reject_report_computed_task = self._get_deserialized_reject_report_computed_task(
            timestamp="2017-12-01 11:00:09",
            reason=message.RejectReportComputedTask.REASON.SubtaskTimeLimitExceeded,
            task_to_compute=task_to_compute,
            task_failure=message.tasks.TaskFailure(),
        )

        serialized_reject_report_computed_task = self._get_serialized_reject_report_computed_task(
            timestamp="2017-12-01 11:00:09",
            reject_report_computed_task=reject_report_computed_task,
            requestor_private_key=self.REQUESTOR_PRIVATE_KEY,
        )

        with freeze_time("2017-12-01 11:00:09"):
            response_6 = self.client.post(
                reverse('core:send'),
                data=serialized_reject_report_computed_task,
                content_type='application/octet-stream',
            )
        self._test_400_response(
            response_6,
            error_code=ErrorCode.MESSAGE_INVALID,
        )
        self._assert_stored_message_counter_not_increased()

    def test_provider_forces_computed_task_report_missing_key_returns_400_error(self):
        """
        Tests if on provider ForceReportComputedTask message Concent will return HTTP 400 error
        if no key was provided in header.

        Expected message exchange:
        Provider -> Concent:    ForceReportComputedTask
        Concent  -> Provider:   HTTP 400 error.
        """

        # STEP 1: Provider forces computed task report via Concent

        compute_task_def = self._get_deserialized_compute_task_def(
            task_id     = '1',
            deadline    = "2017-12-01 11:00:00"
        )

        task_to_compute = self._get_deserialized_task_to_compute(
            timestamp           = "2017-12-01 10:00:00",
            compute_task_def    = compute_task_def,
        )
        del task_to_compute.provider_public_key

        report_computed_task = self._get_deserialized_report_computed_task(
            timestamp = "2017-12-01 10:59:00",
            task_to_compute = task_to_compute,
        )

        serialized_force_report_computed_task = self._get_serialized_force_report_computed_task(
            timestamp = "2017-12-01 10:59:00",
            force_report_computed_task = self._get_deserialized_force_report_computed_task(
                timestamp               = "2017-12-01 10:59:00",
                report_computed_task    = report_computed_task
            ),
            provider_private_key = self.PROVIDER_PRIVATE_KEY
        )

        with freeze_time("2017-12-01 10:59:00"):
            response_1 = self.client.post(
                reverse('core:send'),
                data            = serialized_force_report_computed_task,
                content_type    = 'application/octet-stream',
            )
        self._test_400_response(
            response_1,
            error_code=ErrorCode.MESSAGE_VALUE_WRONG_TYPE,
        )
        self._assert_stored_message_counter_not_increased()

        self._assert_client_count_is_equal(0)

    def test_provider_forces_computed_task_report_bad_key_returns_400_error(self):
        """
        Tests if on provider ForceReportComputedTask message Concent will return HTTP 400 error
        if bad key was provided in header.

        Expected message exchange:
        Provider -> Concent:    ForceReportComputedTask
        Concent  -> Provider:   HTTP 400 error.
        """

        # STEP 1: Provider forces computed task report via Concent

        compute_task_def = self._get_deserialized_compute_task_def(
            task_id     = '1',
            deadline    = "2017-12-01 11:00:00"
        )

        task_to_compute = self._get_deserialized_task_to_compute(
            timestamp           = "2017-12-01 10:00:00",
            compute_task_def    = compute_task_def,
            provider_public_key='bad__key' * 11,
        )

        report_computed_task = self._get_deserialized_report_computed_task(
            timestamp = "2017-12-01 10:59:00",
            task_to_compute = task_to_compute,
        )

        serialized_force_report_computed_task = self._get_serialized_force_report_computed_task(
            timestamp = "2017-12-01 10:59:00",
            force_report_computed_task = self._get_deserialized_force_report_computed_task(
                timestamp               = "2017-12-01 10:59:00",
                report_computed_task    = report_computed_task
            ),
            provider_private_key = self.PROVIDER_PRIVATE_KEY
        )

        with freeze_time("2017-12-01 10:59:00"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                           = serialized_force_report_computed_task,
                content_type                   = 'application/octet-stream',
            )
        self._test_400_response(
            response_1,
            error_code=ErrorCode.MESSAGE_VALUE_WRONG_TYPE,
        )
        self._assert_stored_message_counter_not_increased()

        self._assert_client_count_is_equal(0)

    def test_provider_forces_computed_task_report_truncated_key_returns_400_error(self):
        """
        Tests if on provider ForceReportComputedTask message Concent will return HTTP 400 error
        if truncated key was provided in header.

        Expected message exchange:
        Provider -> Concent:   ForceReportComputedTask
        Concent  -> Provider:  HTTP 400 error.
        """

        # STEP 1: Provider forces computed task report via Concent

        compute_task_def = self._get_deserialized_compute_task_def(
            task_id     = '1',
            deadline    = "2017-12-01 11:00:00"
        )

        task_to_compute = self._get_deserialized_task_to_compute(
            timestamp           = "2017-12-01 10:00:00",
            compute_task_def    = compute_task_def,
            provider_public_key = b64encode(self.PROVIDER_PUBLIC_KEY)[:32].decode('ascii'),
        )

        report_computed_task = self._get_deserialized_report_computed_task(
            timestamp = "2017-12-01 10:59:00",
            task_to_compute = task_to_compute,
        )

        serialized_force_report_computed_task = self._get_serialized_force_report_computed_task(
            timestamp = "2017-12-01 10:59:00",
            force_report_computed_task = self._get_deserialized_force_report_computed_task(
                timestamp               = "2017-12-01 10:59:00",
                report_computed_task    = report_computed_task
            ),
            provider_private_key = self.PROVIDER_PRIVATE_KEY
        )

        with freeze_time("2017-12-01 10:59:00"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                           = serialized_force_report_computed_task,
                content_type                   = 'application/octet-stream',
            )
        self._test_400_response(
            response_1,
            error_code=ErrorCode.MESSAGE_VALUE_WRONG_TYPE
        )
        self._assert_stored_message_counter_not_increased()

        self._assert_client_count_is_equal(0)

    def test_provider_forces_computed_task_report_empty_key_returns_400_error(self):
        """
        Tests if on provider ForceReportComputedTask message Concent will return HTTP 400 error
        if empty key was provided in header.

        Expected message exchange:
        Provider -> Concent:   ForceReportComputedTask
        Concent  -> Provider:  HTTP 400 error.
        """

        # STEP 1: Provider forces computed task report via Concent

        compute_task_def = self._get_deserialized_compute_task_def(
            task_id     = '1',
            deadline    = "2017-12-01 11:00:00"
        )

        task_to_compute = self._get_deserialized_task_to_compute(
            timestamp           = "2017-12-01 10:00:00",
            compute_task_def    = compute_task_def,
            provider_public_key='',
        )

        report_computed_task = self._get_deserialized_report_computed_task(
            timestamp = "2017-12-01 10:59:00",
            task_to_compute = task_to_compute,
        )

        serialized_force_report_computed_task = self._get_serialized_force_report_computed_task(
            timestamp = "2017-12-01 10:59:00",
            force_report_computed_task = self._get_deserialized_force_report_computed_task(
                timestamp               = "2017-12-01 10:59:00",
                report_computed_task    = report_computed_task
            ),
            provider_private_key = self.PROVIDER_PRIVATE_KEY
        )

        with freeze_time("2017-12-01 10:59:00"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                           = serialized_force_report_computed_task,
                content_type                   = 'application/octet-stream',
            )
        self._test_400_response(
            response_1,
            error_code=ErrorCode.MESSAGE_VALUE_WRONG_TYPE,
        )
        self._assert_stored_message_counter_not_increased()

        self._assert_client_count_is_equal(0)

    def test_requestor_sends_ack_report_computed_task_with_message_cannot_compute_task(self):
        """
        Tests if on request AckReportComputedTask message Concent will return HTTP 400 error
        if message contains CannotComputeTask instead of TaskToCompute.

        Expected message exchange:
        Requestor -> Concent:    AckReportComputedTask
        Concent   -> Requestor:  HTTP 400 error.
        """
        # STEP 1: Requestor accepts computed task via Concent

        compute_task_def = self._get_deserialized_compute_task_def(
            task_id     = '1',
            deadline    = "2017-12-01 11:00:00"
        )

        task_to_compute = self._get_deserialized_task_to_compute(
            timestamp           = "2017-12-01 10:00:00",
            compute_task_def    = compute_task_def,
        )

        cannot_compute_task = self._get_deserialized_cannot_compute_task(
            timestamp       = "2017-12-01 10:30:00",
            task_to_compute = task_to_compute,
            reason          = message.tasks.CannotComputeTask.REASON.WrongCTD
        )

        # This has to be done manually, otherwise will fail when signing ReportComputedTask
        with freeze_time("2017-12-01 11:00:05"):
            serialized_ack_report_computed_task = self._get_serialized_ack_report_computed_task(
                ack_report_computed_task = message.AckReportComputedTask(
                    report_computed_task=(
                        message.ReportComputedTask(
                            task_to_compute=cannot_compute_task
                        )
                    )
                )
            )

        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:send'),
                data                           = serialized_ack_report_computed_task,
                content_type                   = 'application/octet-stream',
            )
        self._test_400_response(response)
        self._assert_stored_message_counter_not_increased()

        self._assert_client_count_is_equal(0)

    def test_requestor_sends_reject_report_computed_task_with_message_task_to_compute(self):
        """
        Tests if on request RejectReportComputedTask message Concent will return HTTP 400 error
        if message contains TaskToCompute instead of CannotComputeTask .

        Expected message exchange:
        Requestor -> Concent:    RejectReportComputedTask
        Concent   -> Requestor:  HTTP 400 error.
        """
        # STEP 1: Requestor accepts computed task via Concent

        compute_task_def = self._get_deserialized_compute_task_def(
            task_id     = '1',
            deadline    = "2017-12-01 11:00:00"
        )

        task_to_compute = self._get_deserialized_task_to_compute(
            timestamp           = "2017-12-01 10:00:00",
            compute_task_def    = compute_task_def,
        )

        reject_report_computed_task = self._get_deserialized_reject_report_computed_task(
            timestamp           = "2017-12-01 11:00:05",
            task_to_compute     = task_to_compute,
            reason              = message.RejectReportComputedTask.REASON.SubtaskTimeLimitExceeded
        )

        serialized_reject_report_computed_task = self._get_serialized_reject_report_computed_task(
            timestamp = "2017-12-01 11:00:05",
            reject_report_computed_task = reject_report_computed_task,
            requestor_private_key       = self.REQUESTOR_PRIVATE_KEY,
        )

        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:send'),
                data                           = serialized_reject_report_computed_task,
                content_type                   = 'application/octet-stream',
            )
        self.assertEqual(response.status_code,  400)
        self.assertIn('error', response.json().keys())
        self._assert_stored_message_counter_not_increased()

        self._assert_client_count_is_equal(0)

    def test_provider_sends_force_report_computed_task_with_a_cut_message(self):
        """
        Tests if on request ForceReportComputedTask message Concent will return HTTP 400 error
        if message is malformed.

        Expected message exchange:
        Provider  -> Concent:   ForceReportComputedTask
        Concent   -> Provider:  HTTP 400 error.
        """

        # STEP 1: Provider forces computed task report via Concent

        compute_task_def = self._get_deserialized_compute_task_def(
            task_id     = '1',
            deadline    = "2017-12-01 11:00:00"
        )

        task_to_compute = self._get_deserialized_task_to_compute(
            timestamp           = "2017-12-01 10:00:00",
            compute_task_def    = compute_task_def,
        )

        report_computed_task = self._get_deserialized_report_computed_task(
            timestamp = "2017-12-01 10:59:00",
            task_to_compute = task_to_compute,
        )

        serialized_force_report_computed_task = self._get_serialized_force_report_computed_task(
            timestamp = "2017-12-01 10:59:00",
            force_report_computed_task = self._get_deserialized_force_report_computed_task(
                timestamp               = "2017-12-01 10:59:00",
                report_computed_task    = report_computed_task
            ),
            provider_private_key = self.PROVIDER_PRIVATE_KEY
        )

        with freeze_time("2017-12-01 10:59:00"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_report_computed_task[:50],
                content_type                        = 'application/octet-stream',
            )
        self._test_400_response(response_1)
        self._assert_stored_message_counter_not_increased()

        self._assert_client_count_is_equal(0)

    def test_provider_sends_force_report_computed_task_with_malformed_message(self):
        """
        Tests if on request ForceReportComputedTask message Concent will return HTTP 400 error
        if message is malformed.

        Expected message exchange:
        Provider  -> Concent:   ForceReportComputedTask
        Concent   -> Provider:  HTTP 400 error.
        """

        # STEP 1: Provider forces computed task report via Concent

        compute_task_def = self._get_deserialized_compute_task_def(
            task_id     = '1',
            deadline    = "2017-12-01 11:00:00"
        )

        task_to_compute = self._get_deserialized_task_to_compute(
            timestamp           = "2017-12-01 10:00:00",
            compute_task_def    = compute_task_def,
        )

        report_computed_task = self._get_deserialized_report_computed_task(
            timestamp = "2017-12-01 10:59:00",
            task_to_compute = task_to_compute,
        )

        serialized_force_report_computed_task = self._get_serialized_force_report_computed_task(
            timestamp = "2017-12-01 10:59:00",
            force_report_computed_task = self._get_deserialized_force_report_computed_task(
                timestamp               = "2017-12-01 10:59:00",
                report_computed_task    = report_computed_task
            ),
            provider_private_key = self.PROVIDER_PRIVATE_KEY
        )

        serialized_force_report_computed_task = serialized_force_report_computed_task[:120] + b'\x00' + serialized_force_report_computed_task[120:]

        with freeze_time("2017-12-01 10:59:00"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_report_computed_task,
                content_type                        = 'application/octet-stream',
            )
        self._test_400_response(response_1)
        self._assert_stored_message_counter_not_increased()

        self._assert_client_count_is_equal(0)

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

        compute_task_def = self._get_deserialized_compute_task_def(
            task_id     = '1',
            subtask_id  = '8',
            deadline    = "2017-12-01 11:00:00"
        )

        task_to_compute = self._get_deserialized_task_to_compute(
            timestamp           = "2017-12-01 10:00:00",
            compute_task_def    = compute_task_def,
        )

        report_computed_task = self._get_deserialized_report_computed_task(
            timestamp = "2017-12-01 10:59:00",
            task_to_compute = task_to_compute,
        )

        serialized_force_report_computed_task = self._get_serialized_force_report_computed_task(
            timestamp = "2017-12-01 10:59:00",
            force_report_computed_task = self._get_deserialized_force_report_computed_task(
                timestamp               = "2017-12-01 10:59:00",
                report_computed_task    = report_computed_task
            ),
            provider_private_key = self.PROVIDER_PRIVATE_KEY
        )

        with freeze_time("2017-12-01 10:59:00"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_report_computed_task,
                content_type                        = 'application/octet-stream',
            )

        self.assertEqual(response_1.status_code,  202)
        self.assertEqual(len(response_1.content), 0)
        self._assert_stored_message_counter_increased(increased_by = 2)
        self._test_subtask_state(
            task_id                  = '1',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.FORCING_REPORT,
            provider_key             = self._get_encoded_provider_public_key(),
            requestor_key            = self._get_encoded_requestor_public_key(),
            expected_nested_messages = {'task_to_compute', 'report_computed_task'},
            next_deadline=parse_iso_date_to_timestamp("2017-12-01 11:00:10"),
        )
        self._test_last_stored_messages(
            expected_messages = [
                message.TaskToCompute,
                message.ReportComputedTask,
            ],
            task_id         = '1',
            subtask_id      = '8',
        )
        self._test_undelivered_pending_responses(
            subtask_id                         = '8',
            client_public_key                  = self._get_encoded_requestor_public_key(),
            expected_pending_responses_receive = [
                PendingResponse.ResponseType.ForceReportComputedTask,
            ]
        )

        # STEP 2: Concent forces computed task report on the requestor

        with freeze_time("2017-12-01 11:00:05"):
            response_2 = self.client.post(
                reverse('core:receive'),
                data         = self._create_requestor_auth_message(),
                content_type = 'application/octet-stream',
            )

        self._test_response(
            response_2,
            status          = 200,
            key             = self.REQUESTOR_PRIVATE_KEY,
            message_type    = message.concents.ForceReportComputedTask,
            fields          = {
                'timestamp': parse_iso_date_to_timestamp("2017-12-01 11:00:05"),
                'report_computed_task.task_to_compute.timestamp': parse_iso_date_to_timestamp("2017-12-01 10:00:00"),
                'report_computed_task.task_to_compute.compute_task_def':    compute_task_def,
            }
        )
        self._assert_stored_message_counter_not_increased()

        # STEP 3: Requestor accepts computed task via Concent
        serialized_ack_report_computed_task = self._get_serialized_ack_report_computed_task(
            timestamp="2017-12-01 11:00:05",
            ack_report_computed_task=self._get_deserialized_ack_report_computed_task(
                timestamp="2017-12-01 11:00:05",
                report_computed_task=report_computed_task,
                task_to_compute=task_to_compute
            ),
            requestor_private_key=self.REQUESTOR_PRIVATE_KEY
        )

        with freeze_time("2017-12-01 11:00:05"):
            response_3 = self.client.post(
                reverse('core:send'),
                data                            = serialized_ack_report_computed_task,
                content_type                    = 'application/octet-stream',
            )

        self.assertEqual(response_3.status_code,  202)
        self.assertEqual(len(response_3.content), 0)
        self._assert_stored_message_counter_increased(increased_by=1)
        self._test_subtask_state(
            task_id                  = '1',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.REPORTED,
            provider_key             = self._get_encoded_provider_public_key(),
            requestor_key            = self._get_encoded_requestor_public_key(),
            expected_nested_messages = {'task_to_compute', 'report_computed_task', 'ack_report_computed_task'},
        )
        self._test_last_stored_messages(
            expected_messages= [
                message.AckReportComputedTask,
            ],
            task_id         = '1',
            subtask_id      = '8',
        )
        self._test_undelivered_pending_responses(
            subtask_id                         = '8',
            client_public_key                  = self._get_encoded_provider_public_key(),
            expected_pending_responses_receive = [
                PendingResponse.ResponseType.ForceReportComputedTaskResponse,
            ]
        )

        # STEP 4: Concent passes computed task acceptance to the provider

        with freeze_time("2017-12-01 11:00:30"):
            response_4 = self.client.post(
                reverse('core:receive'),
                data                            = self._create_provider_auth_message(),
                content_type                    = 'application/octet-stream',
            )

        self._test_response(
            response_4,
            status=200,
            key=self.PROVIDER_PRIVATE_KEY,
            message_type=message.concents.ForceReportComputedTaskResponse,
            fields={
                'reason': message.concents.ForceReportComputedTaskResponse.REASON.AckFromRequestor,
                'timestamp': parse_iso_date_to_timestamp("2017-12-01 11:00:30"),
                'reject_report_computed_task': None,
                'ack_report_computed_task.timestamp': parse_iso_date_to_timestamp("2017-12-01 11:00:05"),
                'ack_report_computed_task.report_computed_task.task_to_compute.timestamp': parse_iso_date_to_timestamp(
                    "2017-12-01 10:00:00"),
                'ack_report_computed_task.report_computed_task.task_to_compute.compute_task_def': compute_task_def,
            }
        )
        self._assert_stored_message_counter_not_increased()

        self._assert_client_count_is_equal(2)

    def test_provider_forces_computed_task_report_and_tries_to_receive_twice(self):
        """
        Tests if on request ForceReportComputedTask message Concent will return HTTP 204 response
        if Provider tries to receive MessageAckReportComputedTask twice.

        # Expected message exchange:
        # Provider  -> Concent:    MessageForceReportComputedTask
        # Concent   -> Requestor:  MessageForceReportComputedTask
        # Requestor -> Concent:    MessageAckReportComputedTask
        # Concent   -> Provider:   MessageAckReportComputedTask
        # Concent   -> Provider:   HTTP204
        """

        # STEP 1: Provider forces computed task report via Concent

        compute_task_def = self._get_deserialized_compute_task_def(
            task_id     = '1',
            subtask_id  = '8',
            deadline    = "2017-12-01 11:00:00"
        )

        task_to_compute = self._get_deserialized_task_to_compute(
            timestamp           = "2017-12-01 10:00:00",
            compute_task_def    = compute_task_def,
        )

        report_computed_task = self._get_deserialized_report_computed_task(
            timestamp = "2017-12-01 10:59:00",
            task_to_compute = task_to_compute,
        )

        serialized_force_report_computed_task = self._get_serialized_force_report_computed_task(
            timestamp = "2017-12-01 10:59:00",
            force_report_computed_task = self._get_deserialized_force_report_computed_task(
                timestamp               = "2017-12-01 10:59:00",
                report_computed_task    = report_computed_task
            ),
            provider_private_key = self.PROVIDER_PRIVATE_KEY
        )

        with freeze_time("2017-12-01 10:59:00"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_report_computed_task,
                content_type                        = 'application/octet-stream',
            )

        self.assertEqual(response_1.status_code,  202)
        self.assertEqual(len(response_1.content), 0)
        self._assert_stored_message_counter_increased(increased_by = 2)
        self._test_subtask_state(
            task_id                  = '1',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.FORCING_REPORT,
            provider_key             = self._get_encoded_provider_public_key(),
            requestor_key            = self._get_encoded_requestor_public_key(),
            expected_nested_messages = {'task_to_compute', 'report_computed_task'},
            next_deadline=parse_iso_date_to_timestamp("2017-12-01 11:00:10"),
        )
        self._test_last_stored_messages(
            expected_messages = [
                message.TaskToCompute,
                message.ReportComputedTask,
            ],
            task_id         = '1',
            subtask_id      = '8',
        )
        self._test_undelivered_pending_responses(
            subtask_id                         = '8',
            client_public_key                  = self._get_encoded_requestor_public_key(),
            expected_pending_responses_receive = [
                PendingResponse.ResponseType.ForceReportComputedTask,
            ]
        )

        # STEP 2: Concent forces computed task report on the requestor

        with freeze_time("2017-12-01 11:00:05"):
            response_2 = self.client.post(
                reverse('core:receive'),
                data         = self._create_requestor_auth_message(),
                content_type = 'application/octet-stream',
            )

        self._test_response(
            response_2,
            status          = 200,
            key             = self.REQUESTOR_PRIVATE_KEY,
            message_type    = message.concents.ForceReportComputedTask,
            fields          = {
                'timestamp': parse_iso_date_to_timestamp("2017-12-01 11:00:05"),
                'report_computed_task.task_to_compute.timestamp': parse_iso_date_to_timestamp("2017-12-01 10:00:00"),
                'report_computed_task.task_to_compute.compute_task_def':    compute_task_def,
            }
        )
        self._assert_stored_message_counter_not_increased()

        # STEP 3: Requestor accepts computed task via Concent
        serialized_ack_report_computed_task = self._get_serialized_ack_report_computed_task(
            timestamp="2017-12-01 11:00:05",
            ack_report_computed_task=self._get_deserialized_ack_report_computed_task(
                timestamp="2017-12-01 11:00:05",
                report_computed_task=report_computed_task,
                task_to_compute=task_to_compute,
            ),
            requestor_private_key=self.REQUESTOR_PRIVATE_KEY
        )

        with freeze_time("2017-12-01 11:00:05"):
            response_3 = self.client.post(
                reverse('core:send'),
                data                           = serialized_ack_report_computed_task,
                content_type                   = 'application/octet-stream',
            )

        self.assertEqual(response_3.status_code,  202)
        self.assertEqual(len(response_3.content), 0)
        self._assert_stored_message_counter_increased(increased_by=1)
        self._test_subtask_state(
            task_id                  = '1',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.REPORTED,
            provider_key             = self._get_encoded_provider_public_key(),
            requestor_key            = self._get_encoded_requestor_public_key(),
            expected_nested_messages = {'task_to_compute', 'report_computed_task', 'ack_report_computed_task'},
        )
        self._test_last_stored_messages(
            expected_messages= [
                message.AckReportComputedTask,
            ],
            task_id         = '1',
            subtask_id      = '8',
        )
        self._test_undelivered_pending_responses(
            subtask_id                         = '8',
            client_public_key                  = self._get_encoded_provider_public_key(),
            expected_pending_responses_receive = [
                PendingResponse.ResponseType.ForceReportComputedTaskResponse,
            ]
        )

        # STEP 4: Concent passes computed task acceptance to the provider

        with freeze_time("2017-12-01 11:00:15"):
            response_4 = self.client.post(
                reverse('core:receive'),
                data         = self._create_provider_auth_message(),
                content_type = 'application/octet-stream',
            )

        self._test_response(
            response_4,
            status=200,
            key=self.PROVIDER_PRIVATE_KEY,
            message_type=message.concents.ForceReportComputedTaskResponse,
            fields={
                'reason': message.concents.ForceReportComputedTaskResponse.REASON.AckFromRequestor,
                'timestamp': parse_iso_date_to_timestamp("2017-12-01 11:00:15"),
                'reject_report_computed_task': None,
                'ack_report_computed_task.timestamp': parse_iso_date_to_timestamp("2017-12-01 11:00:05"),
                'ack_report_computed_task.report_computed_task.task_to_compute.timestamp': parse_iso_date_to_timestamp(
                    "2017-12-01 10:00:00"
                ),
                'ack_report_computed_task.report_computed_task.task_to_compute.compute_task_def': compute_task_def,
            }
        )
        self._assert_stored_message_counter_not_increased()

        # STEP 5: Concent passes computed task acceptance to the provider again

        with freeze_time("2017-12-01 12:00:00"):
            response_5 = self.client.post(
                reverse('core:receive'),
                data         = self._create_provider_auth_message(),
                content_type = 'application/octet-stream',
            )

        self._test_204_response(response_5)
        self._assert_stored_message_counter_not_increased()

        self._assert_client_count_is_equal(2)

    def test_provider_forces_computed_task_report_and_tries_to_receive_ack_before_requestor_have_a_chance_to_respond_concent_should_return_http_204(self):
        # Expected message exchange:
        # Provider  -> Concent:    MessageForceReportComputedTask
        # Concent   -> Provider:   HTTP 204
        # Concent   -> Requestor:  MessageForceReportComputedTask
        # Concent   -> Provider:   HTTP 204

        # STEP 1: Provider forces computed task report via Concent
        compute_task_def = self._get_deserialized_compute_task_def(
            task_id     = '1',
            subtask_id  = '8',
            deadline    = "2017-12-01 11:00:00"
        )

        task_to_compute = self._get_deserialized_task_to_compute(
            timestamp           = "2017-12-01 10:00:00",
            compute_task_def    = compute_task_def,
        )

        report_computed_task = self._get_deserialized_report_computed_task(
            timestamp = "2017-12-01 10:59:00",
            task_to_compute = task_to_compute,
        )

        serialized_force_report_computed_task = self._get_serialized_force_report_computed_task(
            timestamp = "2017-12-01 10:59:00",
            force_report_computed_task = self._get_deserialized_force_report_computed_task(
                timestamp               = "2017-12-01 10:59:00",
                report_computed_task    = report_computed_task
            ),
            provider_private_key = self.PROVIDER_PRIVATE_KEY
        )

        with freeze_time("2017-12-01 10:59:00"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_report_computed_task,
                content_type                        = 'application/octet-stream',
            )

        self.assertEqual(response_1.status_code,  202)
        self.assertEqual(len(response_1.content), 0)
        self._assert_stored_message_counter_increased(increased_by = 2)
        self._test_subtask_state(
            task_id                  = '1',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.FORCING_REPORT,
            provider_key             = self._get_encoded_provider_public_key(),
            requestor_key            = self._get_encoded_requestor_public_key(),
            expected_nested_messages = {'task_to_compute', 'report_computed_task'},
            next_deadline=parse_iso_date_to_timestamp("2017-12-01 11:00:10"),
        )
        self._test_last_stored_messages(
            expected_messages = [
                message.TaskToCompute,
                message.ReportComputedTask,
            ],
            task_id         = '1',
            subtask_id      = '8',
        )
        self._test_undelivered_pending_responses(
            subtask_id                         = '8',
            client_public_key                  = self._get_encoded_requestor_public_key(),
            expected_pending_responses_receive = [
                PendingResponse.ResponseType.ForceReportComputedTask,
            ]
        )

        # STEP 2: Provider tries to get Ack from Concent before compute_task_def.deadline + CONCENT_MESSAGING_TIME

        with freeze_time("2017-12-01 11:00:00"):
            response_2 = self.client.post(
                reverse('core:receive'),
                data                            = self._create_provider_auth_message(),
                content_type                    = 'application/octet-stream',
            )

        self._test_204_response(response_2)
        self._assert_stored_message_counter_not_increased()

        # STEP 3: Concent forces computed task report on the requestor

        with freeze_time("2017-12-01 11:00:05"):
            response_3 = self.client.post(
                reverse('core:receive'),
                data         = self._create_requestor_auth_message(),
                content_type = 'application/octet-stream',
            )

        self._test_response(
            response_3,
            status          = 200,
            key             = self.REQUESTOR_PRIVATE_KEY,
            message_type    = message.concents.ForceReportComputedTask,
            fields          = {
                'timestamp': parse_iso_date_to_timestamp("2017-12-01 11:00:05"),
                'report_computed_task.task_to_compute.timestamp': parse_iso_date_to_timestamp("2017-12-01 10:00:00"),
                'report_computed_task.task_to_compute.compute_task_def':    compute_task_def,
            }
        )
        self._assert_stored_message_counter_not_increased()

        # STEP 4: Provider tries to get Ack from Concent too soon, again

        with freeze_time("2017-12-01 11:00:06"):
            response_4 = self.client.post(
                reverse('core:receive'),
                data                            = self._create_provider_auth_message(),
                content_type                    = 'application/octet-stream',
            )
        self._test_204_response(response_4)
        self._assert_stored_message_counter_not_increased()

        self._assert_client_count_is_equal(2)

    def test_provider_forces_computed_task_report_and_requestor_sends_rejection_due_to_task_failure(self):
        # Expected message exchange:
        # Provider  -> Concent:    MessageForceReportComputedTask
        # Concent   -> Requestor:  MessageForceReportComputedTask
        # Requestor -> Concent:    MessageRejectReportComputedTask (GotMessageTaskFailure)
        # Concent   -> Provider:   MessageRejectReportComputedTask

        # STEP 1: Provider forces computed task report via Concent

        compute_task_def = self._get_deserialized_compute_task_def(
            task_id='1',
            subtask_id='8',
            deadline="2017-12-01 11:00:00"
        )

        task_to_compute = self._get_deserialized_task_to_compute(
            timestamp="2017-12-01 10:00:00",
            compute_task_def=compute_task_def,
        )

        report_computed_task = self._get_deserialized_report_computed_task(
            timestamp="2017-12-01 10:59:00",
            task_to_compute=task_to_compute,
        )

        serialized_force_report_computed_task = self._get_serialized_force_report_computed_task(
            timestamp="2017-12-01 10:59:00",
            force_report_computed_task=self._get_deserialized_force_report_computed_task(
                timestamp="2017-12-01 10:59:00",
                report_computed_task=report_computed_task
            ),
            provider_private_key=self.PROVIDER_PRIVATE_KEY
        )

        with freeze_time("2017-12-01 10:59:00"):
            response_1 = self.client.post(
                reverse('core:send'),
                data=serialized_force_report_computed_task,
                content_type='application/octet-stream',
            )

        self.assertEqual(response_1.status_code, 202)
        self.assertEqual(len(response_1.content), 0)
        self._assert_stored_message_counter_increased(increased_by=2)
        self._test_subtask_state(
            task_id='1',
            subtask_id='8',
            subtask_state=Subtask.SubtaskState.FORCING_REPORT,
            provider_key=self._get_encoded_provider_public_key(),
            requestor_key=self._get_encoded_requestor_public_key(),
            expected_nested_messages={'task_to_compute', 'report_computed_task'},
            next_deadline=parse_iso_date_to_timestamp("2017-12-01 11:00:10"),
        )
        self._test_last_stored_messages(
            expected_messages=[
                message.TaskToCompute,
                message.ReportComputedTask,
            ],
            task_id='1',
            subtask_id='8',
        )
        self._test_undelivered_pending_responses(
            subtask_id='8',
            client_public_key=self._get_encoded_requestor_public_key(),
            expected_pending_responses_receive=[
                PendingResponse.ResponseType.ForceReportComputedTask,
            ]
        )

        # STEP 2: Concent forces computed task report on the requestor

        with freeze_time("2017-12-01 11:00:05"):
            response_2 = self.client.post(
                reverse('core:receive'),
                data=self._create_requestor_auth_message(),
                content_type='application/octet-stream',
            )

        self._test_response(
            response_2,
            status=200,
            key=self.REQUESTOR_PRIVATE_KEY,
            message_type=message.concents.ForceReportComputedTask,
            fields={
                'timestamp': parse_iso_date_to_timestamp("2017-12-01 11:00:05"),
                'report_computed_task.task_to_compute.timestamp': parse_iso_date_to_timestamp("2017-12-01 10:00:00"),
                'report_computed_task.task_to_compute.compute_task_def': compute_task_def,
            }
        )
        self._assert_stored_message_counter_not_increased()

        # STEP 3: Requestor rejects computed task due to TaskFailure

        task_failure = self._get_deserialized_task_failure(
            timestamp="2017-12-01 10:30:00",
            err='Stop later soldier sit.',
            task_to_compute=task_to_compute,
        )

        reject_report_computed_task = self._get_deserialized_reject_report_computed_task(
            timestamp="2017-12-01 11:00:05",
            task_failure=task_failure,
            task_to_compute=task_to_compute,
            reason=message.RejectReportComputedTask.REASON.GotMessageTaskFailure,
        )

        serialized_reject_report_computed_task = self._get_serialized_reject_report_computed_task(
            timestamp="2017-12-01 11:00:05",
            reject_report_computed_task=reject_report_computed_task,
            requestor_private_key=self.REQUESTOR_PRIVATE_KEY,
        )

        with freeze_time("2017-12-01 11:00:05"):
            response_3 = self.client.post(
                reverse('core:send'),
                data=serialized_reject_report_computed_task,
                content_type='application/octet-stream',
            )

        self.assertEqual(response_3.status_code, 202)
        self.assertEqual(len(response_3.content), 0)
        self._assert_stored_message_counter_increased(increased_by=1)
        self._test_subtask_state(
            task_id='1',
            subtask_id='8',
            subtask_state=Subtask.SubtaskState.FAILED,
            provider_key=self._get_encoded_provider_public_key(),
            requestor_key=self._get_encoded_requestor_public_key(),
            expected_nested_messages={'task_to_compute', 'report_computed_task', 'reject_report_computed_task'},
        )
        self._test_last_stored_messages(
            expected_messages=[
                message.RejectReportComputedTask,
            ],
            task_id='1',
            subtask_id='8',
        )
        self._test_undelivered_pending_responses(
            subtask_id='8',
            client_public_key=self._get_encoded_provider_public_key(),
            expected_pending_responses_receive=[
                PendingResponse.ResponseType.ForceReportComputedTaskResponse,
            ]
        )

        # STEP 4: Concent passes computed task rejection to the provider

        with freeze_time("2017-12-01 11:00:15"):
            response_4 = self.client.post(
                reverse('core:receive'),
                data=self._create_provider_auth_message(),
                content_type='application/octet-stream',
            )

        self._test_response(
            response_4,
            status=200,
            key=self.PROVIDER_PRIVATE_KEY,
            message_type=message.concents.ForceReportComputedTaskResponse,
            fields={
                'reason': message.concents.ForceReportComputedTaskResponse.REASON.RejectFromRequestor,
                'timestamp': parse_iso_date_to_timestamp("2017-12-01 11:00:15"),
                'ack_report_computed_task': None,
                'reject_report_computed_task.timestamp': parse_iso_date_to_timestamp("2017-12-01 11:00:05"),
                'reject_report_computed_task.task_failure.task_to_compute.timestamp': parse_iso_date_to_timestamp("2017-12-01 10:00:00"),
                'reject_report_computed_task.task_failure.task_to_compute.compute_task_def': compute_task_def,
            }
        )
        self._assert_stored_message_counter_not_increased()

        self._assert_client_count_is_equal(2)

    def test_that_message_report_computed_task_in_database_is_replaced_when_requestor_send_diffrent_report_computed_task(self):
        # Expected message exchange:
        # Provider  -> Concent:    MessageForceReportComputedTask
        # Concent   -> Requestor:  MessageForceReportComputedTask
        # Requestor -> Concent:    MessageAckReportComputedTask (diffrent ReportComptedTask)
        # Concent   -> Provider:   MessageAckReportComputedTask

        # STEP 1: Provider forces computed task report via Concent

        task_to_compute = self._get_deserialized_task_to_compute(
            timestamp = "2017-12-01 10:00:00",
            task_id = '1',
            subtask_id = '8',
            deadline = "2017-12-01 11:00:00"
        )

        report_computed_task = self._get_deserialized_report_computed_task(
            timestamp="2017-12-01 10:59:00",
            task_to_compute=task_to_compute,
        )
        different_report_computed_task = self._get_deserialized_report_computed_task(
            timestamp="2017-12-01 10:58:00",
            task_to_compute=task_to_compute,
        )

        serialized_force_report_computed_task = self._get_serialized_force_report_computed_task(
            timestamp="2017-12-01 10:59:00",
            force_report_computed_task=self._get_deserialized_force_report_computed_task(
                timestamp="2017-12-01 10:59:00",
                report_computed_task=report_computed_task
            ),
            provider_private_key=self.PROVIDER_PRIVATE_KEY
        )

        with freeze_time("2017-12-01 10:59:00"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_report_computed_task,
                content_type                        = 'application/octet-stream',
            )

        self.assertEqual(response_1.status_code,  202)
        self.assertEqual(len(response_1.content), 0)

        self._assert_stored_message_counter_increased(increased_by = 2)
        self._test_subtask_state(
            task_id                  = '1',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.FORCING_REPORT,
            provider_key             = self._get_encoded_provider_public_key(),
            requestor_key            = self._get_encoded_requestor_public_key(),
            expected_nested_messages = {'task_to_compute', 'report_computed_task'},
            next_deadline=parse_iso_date_to_timestamp("2017-12-01 11:00:10"),
        )
        self._test_last_stored_messages(
            expected_messages = [
                message.TaskToCompute,
                message.ReportComputedTask,
            ],
            task_id         = '1',
            subtask_id      = '8',
        )
        self._test_undelivered_pending_responses(
            subtask_id                         = '8',
            client_public_key                  = self._get_encoded_requestor_public_key(),
            expected_pending_responses_receive = [
                PendingResponse.ResponseType.ForceReportComputedTask,
            ]
        )

        # STEP 2: Concent forces computed task report on the requestor

        with freeze_time("2017-12-01 11:00:05"):
            response_2 = self.client.post(
                reverse('core:receive'),
                data         = self._create_requestor_auth_message(),
                content_type = 'application/octet-stream',
            )

        self._test_response(
            response_2,
            status          = 200,
            key             = self.REQUESTOR_PRIVATE_KEY,
            message_type    = message.concents.ForceReportComputedTask,
            fields          = {
                'timestamp': parse_iso_date_to_timestamp("2017-12-01 11:00:05"),
                'report_computed_task.timestamp': parse_iso_date_to_timestamp("2017-12-01 10:59:00"),
                'report_computed_task.task_to_compute.compute_task_def':    task_to_compute.compute_task_def,
            }
        )
        self._assert_stored_message_counter_not_increased()

        # STEP 3: Requestor accepts computed task via Concent

        serialized_ack_report_computed_task = self._get_serialized_ack_report_computed_task(
            timestamp="2017-12-01 11:00:05",
            ack_report_computed_task=self._get_deserialized_ack_report_computed_task(
                timestamp="2017-12-01 11:00:05",
                subtask_id='8',
                report_computed_task=different_report_computed_task,
                task_to_compute=task_to_compute
            ),
            requestor_private_key=self.REQUESTOR_PRIVATE_KEY
        )

        with freeze_time("2017-12-01 11:00:05"):
            response_3 = self.client.post(
                reverse('core:send'),
                data                           = serialized_ack_report_computed_task,
                content_type                   = 'application/octet-stream',
            )

        self._test_report_computed_task_in_database(different_report_computed_task)
        self.assertEqual(response_3.status_code,  202)
        self.assertEqual(len(response_3.content), 0)
        self._assert_stored_message_counter_increased(increased_by = 2)
        self._test_subtask_state(
            task_id                  = '1',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.REPORTED,
            provider_key             = self._get_encoded_provider_public_key(),
            requestor_key            = self._get_encoded_requestor_public_key(),
            expected_nested_messages = {'task_to_compute', 'report_computed_task', 'ack_report_computed_task'},
        )
        self._test_last_stored_messages(
            expected_messages= [
                message.AckReportComputedTask,
            ],
            task_id         = '1',
            subtask_id      = '8',
        )
        self._test_undelivered_pending_responses(
            subtask_id                         = '8',
            client_public_key                  = self._get_encoded_provider_public_key(),
            expected_pending_responses_receive = [
                PendingResponse.ResponseType.ForceReportComputedTaskResponse,
            ]
        )

        # STEP 4: Concent passes computed task acceptance to the provider

        with freeze_time("2017-12-01 11:00:15"):
            response_4 = self.client.post(
                reverse('core:receive'),
                data         = self._create_provider_auth_message(),
                content_type = 'application/octet-stream',
            )

        self._test_response(
            response_4,
            status=200,
            key=self.PROVIDER_PRIVATE_KEY,
            message_type=message.concents.ForceReportComputedTaskResponse,
            fields={
                'reason': message.concents.ForceReportComputedTaskResponse.REASON.AckFromRequestor,
                'timestamp': parse_iso_date_to_timestamp("2017-12-01 11:00:15"),
                'reject_report_computed_task': None,
                'ack_report_computed_task.timestamp': parse_iso_date_to_timestamp("2017-12-01 11:00:05"),
                'ack_report_computed_task.report_computed_task.task_to_compute.compute_task_def': task_to_compute.compute_task_def,
                'ack_report_computed_task.report_computed_task.timestamp': parse_iso_date_to_timestamp(
                    "2017-12-01 10:58:00")
            }
        )
        self._assert_stored_message_counter_not_increased()

        self._assert_client_count_is_equal(2)
