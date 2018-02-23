from base64 import b64encode

from django.test                    import override_settings
from django.urls                    import reverse
from freezegun                      import freeze_time

from golem_messages                 import message
from core.tests.utils               import ConcentIntegrationTestCase
from utils.testing_helpers          import generate_ecc_key_pair


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
                HTTP_CONCENT_CLIENT_PUBLIC_KEY      = self._get_encoded_provider_public_key(),
                HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
            )

        self._test_response(
            response_1,
            status          = 200,
            key             = self.PROVIDER_PRIVATE_KEY,
            message_type    = message.concents.ForceReportComputedTaskResponse,
            fields          = {
                'timestamp':                                                    self._parse_iso_date_to_timestamp("2017-12-01 11:01:00"),
                'reject_report_computed_task.timestamp':                        self._parse_iso_date_to_timestamp("2017-12-01 11:01:00"),
                'reject_report_computed_task.reason':                           message.RejectReportComputedTask.REASON.TaskTimeLimitExceeded,
                'reject_report_computed_task.task_to_compute.compute_task_def': compute_task_def
            }
        )

    def test_provider_forces_computed_task_report_and_requestor_sends_acknowledgement(self):
        # Expected message exchange:
        # Provider  -> Concent:    MessageForceReportComputedTask
        # Concent   -> Requestor:  MessageForceReportComputedTask
        # Requestor -> Concent:    MessageAckReportComputedTask
        # Concent   -> Provider:   MessageAckReportComputedTask

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
                data                                = serialized_force_report_computed_task,
                content_type                        = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY      = self._get_encoded_provider_public_key(),
                HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
            )

        self.assertEqual(response_1.status_code,  202)
        self.assertEqual(len(response_1.content), 0)

        self._test_database_objects(
            last_object_type            = message.concents.ForceReportComputedTask,
            task_id                     = '1',
            receive_delivered_status    = False,
        )

        # STEP 2: Concent forces computed task report on the requestor

        with freeze_time("2017-12-01 11:00:05"):
            response_2 = self.client.post(
                reverse('core:receive'),
                data         = '',
                content_type = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
            )

        self._test_response(
            response_2,
            status          = 200,
            key             = self.REQUESTOR_PRIVATE_KEY,
            message_type    = message.concents.ForceReportComputedTask,
            fields          = {
                'timestamp':                                                self._parse_iso_date_to_timestamp("2017-12-01 11:00:05"),
                'report_computed_task.timestamp':                           self._parse_iso_date_to_timestamp("2017-12-01 10:59:00"),
                'report_computed_task.task_to_compute.compute_task_def':    compute_task_def,
            }
        )
        self._test_database_objects(
            last_object_type            = message.concents.ForceReportComputedTask,
            task_id                     = '1',
            receive_delivered_status    = True,
        )

        # STEP 3: Requestor accepts computed task via Concent

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
            response_3 = self.client.post(
                reverse('core:send'),
                data                           = serialized_ack_report_computed_task,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
            )

        self.assertEqual(response_3.status_code,  202)
        self.assertEqual(len(response_3.content), 0)
        self._test_database_objects(
            last_object_type            = message.concents.AckReportComputedTask,
            task_id                     = '1',
            receive_delivered_status    = False,
        )

        # STEP 4: Concent passes computed task acceptance to the provider

        with freeze_time("2017-12-01 11:00:15"):
            response_4 = self.client.post(
                reverse('core:receive'),
                data         = '',
                content_type = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_provider_public_key(),
            )

        self._test_response(
            response_4,
            status          = 200,
            key             = self.PROVIDER_PRIVATE_KEY,
            message_type    = message.concents.ForceReportComputedTaskResponse,
            fields          = {
                'timestamp':                                                    self._parse_iso_date_to_timestamp("2017-12-01 11:00:15"),
                'ack_report_computed_task.timestamp':                           self._parse_iso_date_to_timestamp("2017-12-01 11:00:05"),
                'ack_report_computed_task.task_to_compute.compute_task_def':    compute_task_def,
            }
        )

    def test_provider_forces_computed_task_report_and_requestor_sends_rejection_due_to_failed_computation(self):
        # Expected message exchange:
        # Provider  -> Concent:    MessageForceReportComputedTask
        # Concent   -> Requestor:  MessageForceReportComputedTask
        # Requestor -> Concent:    MessageRejectReportComputedTask (failed computation)
        # Concent   -> Provider:   MessageRejectReportComputedTask

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
                data                                = serialized_force_report_computed_task,
                content_type                        = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY      = self._get_encoded_provider_public_key(),
                HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
            )

        self.assertEqual(response_1.status_code,  202)
        self.assertEqual(len(response_1.content), 0)
        self._test_database_objects(
            last_object_type            = message.concents.ForceReportComputedTask,
            task_id                     = '1',
            receive_delivered_status    = False,
        )

        # STEP 2: Concent forces computed task report on the requestor

        with freeze_time("2017-12-01 11:00:05"):
            response_2 = self.client.post(
                reverse('core:receive'),
                data         = '',
                content_type = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY   = self._get_encoded_requestor_public_key(),
            )

        self._test_response(
            response_2,
            status          = 200,
            key             = self.REQUESTOR_PRIVATE_KEY,
            message_type    = message.concents.ForceReportComputedTask,
            fields          = {
                'timestamp':                                                self._parse_iso_date_to_timestamp("2017-12-01 11:00:05"),
                'report_computed_task.task_to_compute.timestamp':           self._parse_iso_date_to_timestamp("2017-12-01 10:00:00"),
                'report_computed_task.task_to_compute.compute_task_def':    compute_task_def,
            }
        )

        # STEP 3: Requestor rejects computed task due to CannotComputeTask or TaskFailure

        cannot_compute_task = self._get_deserialized_cannot_compute_task(
            timestamp       = "2017-12-01 10:30:00",
            task_to_compute = task_to_compute,
            reason          = message.tasks.CannotComputeTask.REASON.WrongKey
        )

        reject_report_computed_task = self._get_deserialized_reject_report_computed_task(
            timestamp           = "2017-12-01 11:00:05",
            cannot_compute_task = cannot_compute_task,
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
                HTTP_CONCENT_CLIENT_PUBLIC_KEY  = self._get_encoded_requestor_public_key(),
            )

        self.assertEqual(response_3.status_code,  202)
        self.assertEqual(len(response_3.content), 0)
        self._test_database_objects(
            last_object_type            = message.concents.RejectReportComputedTask,
            task_id                     = '1',
            receive_delivered_status    = False,
        )
        # STEP 4: Concent passes computed task rejection to the provider

        with freeze_time("2017-12-01 11:00:15"):
            response_4 = self.client.post(
                reverse('core:receive'),
                data                            = '',
                content_type                    = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY  = self._get_encoded_provider_public_key(),
            )

        self._test_response(
            response_4,
            status          = 200,
            key             = self.PROVIDER_PRIVATE_KEY,
            message_type    = message.concents.ForceReportComputedTaskResponse,
            fields          = {
                'timestamp':                                                                        self._parse_iso_date_to_timestamp("2017-12-01 11:00:15"),
                'reject_report_computed_task.timestamp':                                            self._parse_iso_date_to_timestamp("2017-12-01 11:00:05"),
                'reject_report_computed_task.cannot_compute_task.task_to_compute.timestamp':        self._parse_iso_date_to_timestamp("2017-12-01 10:00:00"),
                'reject_report_computed_task.cannot_compute_task.task_to_compute.compute_task_def': compute_task_def,
            }
        )

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
                HTTP_CONCENT_CLIENT_PUBLIC_KEY      = self._get_encoded_provider_public_key(),
                HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
            )

        self.assertEqual(response_1.status_code,  202)
        self.assertEqual(len(response_1.content), 0)
        self._test_database_objects(
            last_object_type            = message.concents.ForceReportComputedTask,
            task_id                     = '1',
            receive_delivered_status    = False,
        )

        # STEP 2: Concent forces computed task report on the requestor

        with freeze_time("2017-12-01 11:00:05"):
            response_2 = self.client.post(
                reverse('core:receive'),
                data         = '',
                content_type = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
            )

        self._test_response(
            response_2,
            status          = 200,
            key             = self.REQUESTOR_PRIVATE_KEY,
            message_type    = message.concents.ForceReportComputedTask,
            fields          = {
                'timestamp':                                                self._parse_iso_date_to_timestamp("2017-12-01 11:00:05"),
                'report_computed_task.task_to_compute.timestamp':           self._parse_iso_date_to_timestamp("2017-12-01 10:00:00"),
                'report_computed_task.task_to_compute.compute_task_def':    compute_task_def,
            }
        )

        # STEP 3: Requestor rejects computed task claiming that the deadline has been exceeded

        cannot_compute_task = self._get_deserialized_cannot_compute_task(
            timestamp       = "2017-12-01 10:30:00",
            task_to_compute = task_to_compute,
            reason          = message.tasks.CannotComputeTask.REASON.WrongCTD
        )

        reject_report_computed_task = self._get_deserialized_reject_report_computed_task(
            timestamp           = "2017-12-01 11:00:05",
            cannot_compute_task = cannot_compute_task,
            reason              = message.concents.RejectReportComputedTask.REASON.TaskTimeLimitExceeded
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
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
            )

        self.assertEqual(response_3.status_code,                    202)
        self.assertEqual(len(response_3.content),                   0)
        self._test_database_objects(
            last_object_type            = message.concents.RejectReportComputedTask,
            task_id                     = '1',
            receive_delivered_status    = False,
        )

        # STEP 4: Concent overrides computed task rejection and sends acceptance message to the provider

        with freeze_time("2017-12-01 11:00:15"):
            response_4 = self.client.post(
                reverse('core:receive'),
                data                            = '',
                content_type                    = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY  = self._get_encoded_provider_public_key(),
            )

        self._test_response(
            response_4,
            status          = 200,
            key             = self.PROVIDER_PRIVATE_KEY,
            message_type    = message.concents.ForceReportComputedTaskResponse,
            fields          = {
                'timestamp':                                                    self._parse_iso_date_to_timestamp("2017-12-01 11:00:15"),
                'ack_report_computed_task.timestamp':                           self._parse_iso_date_to_timestamp("2017-12-01 11:00:15"),
                'ack_report_computed_task.task_to_compute.timestamp':           self._parse_iso_date_to_timestamp("2017-12-01 10:00:00"),
                'ack_report_computed_task.task_to_compute.compute_task_def':    compute_task_def,
            }
        )

        # STEP 5: Requestor receives computed task report verdict out of band due to an overridden decision

        with freeze_time("2017-12-01 11:00:15"):
            response_5 = self.client.post(
                reverse('core:receive_out_of_band'),
                data         = '',
                content_type = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
            )

        self._test_response(
            response_5,
            status          = 200,
            key             = self.REQUESTOR_PRIVATE_KEY,
            message_type    = message.concents.VerdictReportComputedTask,
            fields          = {
                'timestamp':                                                    self._parse_iso_date_to_timestamp("2017-12-01 11:00:15"),
                'ack_report_computed_task.timestamp':                           self._parse_iso_date_to_timestamp("2017-12-01 11:00:15"),
                'ack_report_computed_task.task_to_compute.timestamp':           self._parse_iso_date_to_timestamp("2017-12-01 10:00:00"),
                'ack_report_computed_task.task_to_compute.compute_task_def':    compute_task_def,
            }
        )

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
                HTTP_CONCENT_CLIENT_PUBLIC_KEY      = self._get_encoded_provider_public_key(),
                HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
            )

        self.assertEqual(response_1.status_code,  202)
        self.assertEqual(len(response_1.content), 0)
        self._test_database_objects(
            last_object_type            = message.concents.ForceReportComputedTask,
            task_id                     = '1',
            receive_delivered_status    = False,
        )

        # STEP 2: Concent forces computed task report on the requestor

        with freeze_time("2017-12-01 11:00:05"):
            response_2 = self.client.post(
                reverse('core:receive'),
                data         = '',
                content_type = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
            )

        self._test_response(
            response_2,
            status          = 200,
            key             = self.REQUESTOR_PRIVATE_KEY,
            message_type    = message.concents.ForceReportComputedTask,
            fields          = {
                'timestamp':                                                self._parse_iso_date_to_timestamp("2017-12-01 11:00:05"),
                'report_computed_task.task_to_compute.timestamp':           self._parse_iso_date_to_timestamp("2017-12-01 10:00:00"),
                'report_computed_task.task_to_compute.compute_task_def':    compute_task_def,
            }
        )

        # STEP 3: Concent accepts computed task due to lack of response from the requestor

        with freeze_time("2017-12-01 11:00:15"):
            response_3 = self.client.post(
                reverse('core:receive'),
                data                            = '',
                content_type                    = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY  = self._get_encoded_provider_public_key(),
            )
        self._test_response(
            response_3,
            status          = 200,
            key             = self.PROVIDER_PRIVATE_KEY,
            message_type    = message.concents.ForceReportComputedTaskResponse,
            fields          = {
                'timestamp':                                                    self._parse_iso_date_to_timestamp("2017-12-01 11:00:15"),
                'ack_report_computed_task.timestamp':                           self._parse_iso_date_to_timestamp("2017-12-01 11:00:15"),
                'ack_report_computed_task.task_to_compute.timestamp':           self._parse_iso_date_to_timestamp("2017-12-01 10:00:00"),
                'ack_report_computed_task.task_to_compute.compute_task_def':    compute_task_def,
            }
        )

        # STEP 4: Requestor receives task computation report verdict out of band due to lack of response

        with freeze_time("2017-12-01 11:00:15"):
            response_4 = self.client.post(
                reverse('core:receive_out_of_band'),
                data                            = '',
                content_type                    = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY  = self._get_encoded_requestor_public_key(),
            )
        self._test_response(
            response_4,
            status          = 200,
            key             = self.REQUESTOR_PRIVATE_KEY,
            message_type    = message.concents.VerdictReportComputedTask,
            fields          = {
                'timestamp':                                                    self._parse_iso_date_to_timestamp("2017-12-01 11:00:15"),
                'ack_report_computed_task.timestamp':                           self._parse_iso_date_to_timestamp("2017-12-01 11:00:15"),
                'ack_report_computed_task.task_to_compute.timestamp':           self._parse_iso_date_to_timestamp("2017-12-01 10:00:00"),
                'ack_report_computed_task.task_to_compute.compute_task_def':    compute_task_def,
            }
        )

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
                HTTP_CONCENT_CLIENT_PUBLIC_KEY      = self._get_encoded_provider_public_key(),
                HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
            )

        self.assertEqual(response_1.status_code,  202)
        self.assertEqual(len(response_1.content), 0)
        self._test_database_objects(
            last_object_type            = message.concents.ForceReportComputedTask,
            task_id                     = '1',
            receive_delivered_status    = False,
        )

        # STEP 2: Provider forces computed task report via Concent again
        with freeze_time("2017-12-01 10:59:00"):
            response_2 = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_report_computed_task,
                content_type                        = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY      = self._get_encoded_provider_public_key(),
                HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
            )
        self._test_400_response(response_2)

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
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
            )

        self._test_400_response(response)

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

        cannot_compute_task = self._get_deserialized_cannot_compute_task(
            timestamp       = "2017-12-01 10:30:00",
            task_to_compute = task_to_compute,
            reason          = message.tasks.CannotComputeTask.REASON.WrongCTD
        )

        reject_report_computed_task = self._get_deserialized_reject_report_computed_task(
            timestamp           = "2017-12-01 11:00:05",
            cannot_compute_task = cannot_compute_task,
            reason              = message.concents.RejectReportComputedTask.REASON.TaskTimeLimitExceeded,
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
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
            )

        self._test_400_response(response)

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
                HTTP_CONCENT_CLIENT_PUBLIC_KEY      = self._get_encoded_provider_public_key(),
                HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
            )

        self.assertEqual(response_1.status_code,  202)
        self.assertEqual(len(response_1.content), 0)
        self._test_database_objects(
            last_object_type            = message.concents.ForceReportComputedTask,
            task_id                     = '1',
            receive_delivered_status    = False,
        )

        # STEP 2: Concent forces computed task report on the requestor

        with freeze_time("2017-12-01 11:00:05"):
            response_2 = self.client.post(
                reverse('core:receive'),
                data         = '',
                content_type = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
            )

        self._test_response(
            response_2,
            status          = 200,
            key             = self.REQUESTOR_PRIVATE_KEY,
            message_type    = message.concents.ForceReportComputedTask,
            fields          = {
                'timestamp':                                                self._parse_iso_date_to_timestamp("2017-12-01 11:00:05"),
                'report_computed_task.task_to_compute.timestamp':           self._parse_iso_date_to_timestamp("2017-12-01 10:00:00"),
                'report_computed_task.task_to_compute.compute_task_def':    compute_task_def,
            }
        )

        # STEP 3: Requestor accepts computed task via Concent

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
            response_3 = self.client.post(
                reverse('core:send'),
                data                           = serialized_ack_report_computed_task,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
            )

        self.assertEqual(response_3.status_code,  202)
        self.assertEqual(len(response_3.content), 0)
        self._test_database_objects(
            last_object_type            = message.concents.AckReportComputedTask,
            task_id                     = '1',
            receive_delivered_status    = False,
        )
        # STEP 4: Requestor rejects computed task via Concent

        cannot_compute_task = self._get_deserialized_cannot_compute_task(
            timestamp       = "2017-12-01 10:30:00",
            task_to_compute = task_to_compute,
            reason          = message.tasks.CannotComputeTask.REASON.WrongEnvironment
        )

        reject_report_computed_task = self._get_deserialized_reject_report_computed_task(
            timestamp           = "2017-12-01 11:00:05",
            cannot_compute_task = cannot_compute_task,
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
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
            )

        self._test_400_response(response_4)

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
                HTTP_CONCENT_CLIENT_PUBLIC_KEY      = self._get_encoded_provider_public_key(),
                HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
            )

        self.assertEqual(response_1.status_code,  202)
        self.assertEqual(len(response_1.content), 0)
        self._test_database_objects(
            last_object_type            = message.concents.ForceReportComputedTask,
            task_id                     = '1',
            receive_delivered_status    = False,
        )

        # STEP 2: Concent forces computed task report on the requestor

        with freeze_time("2017-12-01 11:00:05"):
            response_2 = self.client.post(
                reverse('core:receive'),
                data         = '',
                content_type = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
            )

        self._test_response(
            response_2,
            status          = 200,
            key             = self.REQUESTOR_PRIVATE_KEY,
            message_type    = message.concents.ForceReportComputedTask,
            fields          = {
                'timestamp':                                                self._parse_iso_date_to_timestamp("2017-12-01 11:00:05"),
                'report_computed_task.task_to_compute.timestamp':           self._parse_iso_date_to_timestamp("2017-12-01 10:00:00"),
                'report_computed_task.task_to_compute.compute_task_def':    compute_task_def,
            }
        )

        # STEP 3: Requestor rejects computed task via Concent

        cannot_compute_task = self._get_deserialized_cannot_compute_task(
            timestamp       = "2017-12-01 10:30:00",
            task_to_compute = task_to_compute,
            reason          = message.tasks.CannotComputeTask.REASON.WrongCTD
        )

        reject_report_computed_task = self._get_deserialized_reject_report_computed_task(
            timestamp           = "2017-12-01 11:00:05",
            cannot_compute_task = cannot_compute_task,
            reason              = message.concents.RejectReportComputedTask.REASON.TaskTimeLimitExceeded
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
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
            )

        self.assertEqual(response_3.status_code,  202)
        self._test_database_objects(
            last_object_type            = message.concents.RejectReportComputedTask,
            task_id                     = '1',
            receive_delivered_status    = False,
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
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
            )

        self._test_400_response(response_4)

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
                HTTP_CONCENT_CLIENT_PUBLIC_KEY      = self._get_encoded_provider_public_key(),
                HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
            )

        self.assertEqual(response_1.status_code,  202)
        self.assertEqual(len(response_1.content), 0)
        self._test_database_objects(
            last_object_type            = message.concents.ForceReportComputedTask,
            task_id                     = '1',
            receive_delivered_status    = False,
        )

        # STEP 2: Concent forces computed task report on the requestor

        with freeze_time("2017-12-01 11:00:05"):
            response_2 = self.client.post(
                reverse('core:receive'),
                data         = '',
                content_type = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
            )

        self._test_response(
            response_2,
            status          = 200,
            key             = self.REQUESTOR_PRIVATE_KEY,
            message_type    = message.concents.ForceReportComputedTask,
            fields          = {
                'timestamp':                                                self._parse_iso_date_to_timestamp("2017-12-01 11:00:05"),
                'report_computed_task.task_to_compute.timestamp':           self._parse_iso_date_to_timestamp("2017-12-01 10:00:00"),
                'report_computed_task.task_to_compute.compute_task_def':    compute_task_def,
            }
        )

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
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
            )

        self._test_400_response(response_3)

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
                data                                = serialized_force_report_computed_task,
                content_type                        = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY      = self._get_encoded_provider_public_key(),
                HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
            )

        self.assertEqual(response_1.status_code,  202)
        self.assertEqual(len(response_1.content), 0)
        self._test_database_objects(
            last_object_type            = message.concents.ForceReportComputedTask,
            task_id                     = '1',
            receive_delivered_status    = False,
        )

        # STEP 2: Concent forces computed task report on the requestor

        with freeze_time("2017-12-01 11:00:05"):
            response_2 = self.client.post(
                reverse('core:receive'),
                data         = '',
                content_type = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
            )

        self._test_response(
            response_2,
            status          = 200,
            key             = self.REQUESTOR_PRIVATE_KEY,
            message_type    = message.concents.ForceReportComputedTask,
            fields          = {
                'timestamp':                                                self._parse_iso_date_to_timestamp("2017-12-01 11:00:05"),
                'report_computed_task.task_to_compute.timestamp':           self._parse_iso_date_to_timestamp("2017-12-01 10:00:00"),
                'report_computed_task.task_to_compute.compute_task_def':    compute_task_def,
            }
        )

        # STEP 3: Requestor rejects computed task via Concent after deadline

        cannot_compute_task = self._get_deserialized_cannot_compute_task(
            timestamp       = "2017-12-01 10:30:00",
            task_to_compute = task_to_compute,
            reason          = message.tasks.CannotComputeTask.REASON.WrongKey
        )

        reject_report_computed_task = self._get_deserialized_reject_report_computed_task(
            timestamp           = "2017-12-01 11:00:15",
            cannot_compute_task = cannot_compute_task,
            reason              = message.concents.RejectReportComputedTask.REASON.TaskTimeLimitExceeded
        )

        serialized_reject_report_computed_task = self._get_serialized_reject_report_computed_task(
            timestamp = "2017-12-01 11:00:15",
            reject_report_computed_task = reject_report_computed_task,
            requestor_private_key       = self.REQUESTOR_PRIVATE_KEY,
        )

        with freeze_time("2017-12-01 11:00:15"):
            response_3 = self.client.post(
                reverse('core:send'),
                data                            = serialized_reject_report_computed_task,
                content_type                    = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY  = self._get_encoded_requestor_public_key(),
            )

        self._test_400_response(response_3)

    def test_provider_forces_computed_task_report_missing_key_returns_400_error(self):
        """
        Tests if on provider ForceReportComputedTask message Concent will return HTTP 400 error
        if no key was provided in header.

        Expected message exchange:
        Provider -> Concent:    ForceReportComputedTask
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
                data            = serialized_force_report_computed_task,
                content_type    = 'application/octet-stream',
            )

        self._test_400_response(response_1)

    def test_provider_forces_computed_task_report_bad_key_returns_400_error(self):
        """
        Tests if on provider ForceReportComputedTask message Concent will return HTTP 400 error
        if bad key was provided in header.

        Expected message exchange:
        Provider -> Concent:    ForceReportComputedTask
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
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = 'bad__key' * 11,
            )

        self._test_400_response(response_1)

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
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = b64encode(self.PROVIDER_PUBLIC_KEY)[:32].decode('ascii'),
            )

        self._test_400_response(response_1)

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
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = '',
            )

        self._test_400_response(response_1)

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

        serialized_ack_report_computed_task = self._get_serialized_ack_report_computed_task(
            timestamp = "2017-12-01 11:00:05",
            ack_report_computed_task = self._get_deserialized_ack_report_computed_task(
                timestamp       = "2017-12-01 11:00:05",
                subtask_id      = '1',
                task_to_compute = cannot_compute_task
            ),
            requestor_private_key = self.REQUESTOR_PRIVATE_KEY
        )

        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:send'),
                data                           = serialized_ack_report_computed_task,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
            )

        self._test_400_response(response)

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
            reason              = message.concents.RejectReportComputedTask.REASON.TaskTimeLimitExceeded
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
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
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
                HTTP_CONCENT_CLIENT_PUBLIC_KEY      = self._get_encoded_provider_public_key(),
                HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
            )

        self._test_400_response(response_1)

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
                HTTP_CONCENT_CLIENT_PUBLIC_KEY      = self._get_encoded_provider_public_key(),
                HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
            )
        self._test_400_response(response_1)

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
                HTTP_CONCENT_CLIENT_PUBLIC_KEY      = self._get_encoded_provider_public_key(),
                HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
            )

        self.assertEqual(response_1.status_code,  202)
        self.assertEqual(len(response_1.content), 0)
        self._test_database_objects(
            last_object_type            = message.concents.ForceReportComputedTask,
            task_id                     = '1',
            receive_delivered_status    = False,
        )

        # STEP 2: Concent forces computed task report on the requestor

        with freeze_time("2017-12-01 11:00:05"):
            response_2 = self.client.post(
                reverse('core:receive'),
                data         = '',
                content_type = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
            )

        self._test_response(
            response_2,
            status          = 200,
            key             = self.REQUESTOR_PRIVATE_KEY,
            message_type    = message.concents.ForceReportComputedTask,
            fields          = {
                'timestamp':                                                self._parse_iso_date_to_timestamp("2017-12-01 11:00:05"),
                'report_computed_task.task_to_compute.timestamp':           self._parse_iso_date_to_timestamp("2017-12-01 10:00:00"),
                'report_computed_task.task_to_compute.compute_task_def':    compute_task_def,
            }
        )

        # STEP 3: Requestor accepts computed task via Concent

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
            response_3 = self.client.post(
                reverse('core:send'),
                data                            = serialized_ack_report_computed_task,
                content_type                    = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY  = self._get_encoded_requestor_public_key(),
            )

        self.assertEqual(response_3.status_code,  202)
        self.assertEqual(len(response_3.content), 0)
        self._test_database_objects(
            last_object_type            = message.concents.AckReportComputedTask,
            task_id                     = '1',
            receive_delivered_status    = False,
        )

        # STEP 4: Concent passes computed task acceptance to the provider

        with freeze_time("2017-12-01 11:00:30"):
            response_4 = self.client.post(
                reverse('core:receive'),
                data                            = '',
                content_type                    = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY  = self._get_encoded_provider_public_key(),
            )

        self._test_204_response(response_4)

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
                data                                = serialized_force_report_computed_task,
                content_type                        = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY      = self._get_encoded_provider_public_key(),
                HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
            )

        self.assertEqual(response_1.status_code,  202)
        self.assertEqual(len(response_1.content), 0)
        self._test_database_objects(
            last_object_type            = message.concents.ForceReportComputedTask,
            task_id                     = '1',
            receive_delivered_status    = False,
        )

        # STEP 2: Concent forces computed task report on the requestor

        with freeze_time("2017-12-01 11:00:05"):
            response_2 = self.client.post(
                reverse('core:receive'),
                data         = '',
                content_type = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
            )

        self._test_response(
            response_2,
            status          = 200,
            key             = self.REQUESTOR_PRIVATE_KEY,
            message_type    = message.concents.ForceReportComputedTask,
            fields          = {
                'timestamp':                                                self._parse_iso_date_to_timestamp("2017-12-01 11:00:05"),
                'report_computed_task.task_to_compute.timestamp':           self._parse_iso_date_to_timestamp("2017-12-01 10:00:00"),
                'report_computed_task.task_to_compute.compute_task_def':    compute_task_def,
            }
        )

        # STEP 3: Requestor accepts computed task via Concent

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
            response_3 = self.client.post(
                reverse('core:send'),
                data                           = serialized_ack_report_computed_task,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
            )

        self.assertEqual(response_3.status_code,  202)
        self.assertEqual(len(response_3.content), 0)
        self._test_database_objects(
            last_object_type            = message.concents.AckReportComputedTask,
            task_id                     = '1',
            receive_delivered_status    = False,
        )

        # STEP 4: Concent passes computed task acceptance to the provider

        with freeze_time("2017-12-01 11:00:15"):
            response_4 = self.client.post(
                reverse('core:receive'),
                data         = '',
                content_type = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_provider_public_key(),
            )

        self._test_response(
            response_4,
            status          = 200,
            key             = self.PROVIDER_PRIVATE_KEY,
            message_type    = message.concents.ForceReportComputedTaskResponse,
            fields          = {
                'timestamp':                                                    self._parse_iso_date_to_timestamp("2017-12-01 11:00:15"),
                'ack_report_computed_task.timestamp':                           self._parse_iso_date_to_timestamp("2017-12-01 11:00:05"),
                'ack_report_computed_task.task_to_compute.timestamp':           self._parse_iso_date_to_timestamp("2017-12-01 10:00:00"),
                'ack_report_computed_task.task_to_compute.compute_task_def':    compute_task_def,
            }
        )

        # STEP 5: Concent passes computed task acceptance to the provider again

        with freeze_time("2017-12-01 12:00:00"):
            response_5 = self.client.post(
                reverse('core:receive'),
                data         = '',
                content_type = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_provider_public_key(),
            )

        self._test_204_response(response_5)
