import mock

from django.test            import override_settings
from django.urls            import reverse
from freezegun              import freeze_time
from golem_messages         import load
from golem_messages         import message
from golem_messages.message import FileTransferToken

from core.tests.utils       import ConcentIntegrationTestCase
from core.models            import PendingResponse
from core.models            import Subtask
from utils.testing_helpers  import generate_ecc_key_pair


(CONCENT_PRIVATE_KEY, CONCENT_PUBLIC_KEY) = generate_ecc_key_pair()


def request_upload_status_true_mock(_request_upload_status_false_mock):
    return True


def request_upload_status_false_mock(_request_upload_status_false_mock):
    return False


@override_settings(
    CONCENT_PRIVATE_KEY         = CONCENT_PRIVATE_KEY,
    CONCENT_PUBLIC_KEY          = CONCENT_PUBLIC_KEY,
    CONCENT_MESSAGING_TIME      = 10,    # seconds
    FORCE_ACCEPTANCE_TIME       = 10,    # seconds
    MINIMUM_UPLOAD_RATE         = 1,     # bits per second
    DOWNLOAD_LEADIN_TIME        = 10,    # seconds
    SUBTASK_VERIFICATION_TIME   = 1800,  # 30 minutes
)
class GetTaskResultIntegrationTest(ConcentIntegrationTestCase):

    def test_requestor_forces_get_task_result_and_concent_immediately_sends_rejection_due_to_exceeded_time_for_download(self):
        """
        Tests if on requestor ForceGetTaskResult message Concent will return ForceGetTaskResultRejected
        if time for download is exceeded.

        Expected message exchange:
        Requestor -> Concent:    ForceGetTaskResult
        Concent   -> Requestor:  ForceGetTaskResultRejected
        """

        # STEP 1: Requestor forces get task result via Concent.
        # Concent rejects request immediately when download time is exceeded.
        deserialized_task_to_compute = self._get_deserialized_task_to_compute(
            timestamp   = "2017-12-01 10:00:00",
            deadline    = "2017-12-01 11:00:00",
        )
        deserialized_report_computed_task = self._get_deserialized_report_computed_task(
            task_to_compute = deserialized_task_to_compute,
            size=1,
        )
        serialized_force_get_task_result = self._get_serialized_force_get_task_result(
            report_computed_task    = deserialized_report_computed_task,
            timestamp               = "2017-12-01 11:00:11",
        )

        with freeze_time("2017-12-01 11:02:31"):
            response = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_get_task_result,
                content_type                        = 'application/octet-stream',
            )

        self.assertEqual(response.status_code, 200)

        message_from_concent = load(response.content, self.REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY, check_time = False)

        self.assertIsInstance(message_from_concent,         message.concents.ForceGetTaskResultRejected)
        self.assertEqual(message_from_concent.timestamp,    self._parse_iso_date_to_timestamp("2017-12-01 11:02:31"))
        self.assertEqual(message_from_concent.reason,       message_from_concent.REASON.AcceptanceTimeLimitExceeded)
        self._assert_stored_message_counter_not_increased()

    def test_requestor_forces_get_task_result_and_concent_immediately_sends_rejection_due_to_already_sent_message(self):
        """
        Tests if on requestor ForceGetTaskResult message Concent will return ForceGetTaskResultRejected
        if ForceGetTaskResult was already sent by this requestor.

        Expected message exchange:
        Requestor -> Concent:    ForceGetTaskResult
        Requestor -> Concent:    ForceGetTaskResult
        Concent   -> Requestor:  ServiceRefused
        """

        # STEP 1: Requestor forces get task result via Concent.
        deserialized_task_to_compute = self._get_deserialized_task_to_compute(
            timestamp   = "2017-12-01 10:00:00",
            deadline    = "2017-12-01 11:00:00",
            task_id     = '1',
            subtask_id  = '8',
        )
        deserialized_report_computed_task = self._get_deserialized_report_computed_task(
            task_to_compute = deserialized_task_to_compute,
            timestamp       = "2017-12-01 11:00:08",
        )
        serialized_force_get_task_result = self._get_serialized_force_get_task_result(
            report_computed_task    = deserialized_report_computed_task,
            timestamp               = "2017-12-01 11:00:08",
        )

        with freeze_time("2017-12-01 11:00:08"):
            response = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_get_task_result,
                content_type                        = 'application/octet-stream',
            )

        assert response.status_code == 200

        self._assert_stored_message_counter_increased(increased_by = 2)
        self._test_subtask_state(
            task_id                  = '1',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.FORCING_RESULT_TRANSFER,
            provider_key             = self._get_encoded_provider_public_key(),
            requestor_key            = self._get_encoded_requestor_public_key(),
            expected_nested_messages = {'task_to_compute', 'report_computed_task'},
            next_deadline            = self._parse_iso_date_to_timestamp("2017-12-01 11:00:28"),
        )
        self._test_last_stored_messages(
            expected_messages = [
                message.tasks.TaskToCompute,
                message.tasks.ReportComputedTask,
            ],
            task_id         = '1',
            subtask_id      = '8',
            timestamp       = "2017-12-01 11:00:08"
        )
        self._test_undelivered_pending_responses(
            subtask_id                         = '8',
            client_public_key                  = self._get_encoded_provider_public_key(),
            expected_pending_responses_receive = [
                PendingResponse.ResponseType.ForceGetTaskResultUpload,
            ]
        )

        # STEP 2: Requestor again forces get task result via Concent.
        # Concent rejects request immediately because message was already sent.
        with mock.patch('core.transfer_operations.request_upload_status', request_upload_status_false_mock):
            with freeze_time("2017-12-01 11:00:09"):
                response = self.client.post(
                    reverse('core:send'),
                    data                                = serialized_force_get_task_result,
                    content_type                        = 'application/octet-stream',
                )

        self.assertEqual(response.status_code,  200)

        message_from_concent = load(response.content, self.REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY, check_time = False)

        self.assertIsInstance(message_from_concent,         message.concents.ServiceRefused)
        self.assertEqual(message_from_concent.timestamp,    self._parse_iso_date_to_timestamp("2017-12-01 11:00:09"))
        self.assertEqual(message_from_concent.reason,       message_from_concent.REASON.DuplicateRequest)
        self._assert_stored_message_counter_not_increased()
        self._test_undelivered_pending_responses(
            subtask_id                         = '8',
            client_public_key                  = self._get_encoded_provider_public_key(),
            expected_pending_responses_receive = [
                PendingResponse.ResponseType.ForceGetTaskResultUpload,
            ]
        )

        self._assert_client_count_is_equal(2)

    def test_requestor_forces_get_task_result_and_concent_immediately_sends_acknowledgement(self):
        """
        Tests if on requestor ForceGetTaskResult message Concent will return AckForceGetTaskResult
        if all conditions were met.

        Expected message exchange:
        Requestor -> Concent:    ForceGetTaskResult
        Concent   -> Requestor:  AckForceGetTaskResult
        """

        # STEP 1: Requestor forces get task result via Concent.
        # Concent accepts request if all conditions were met.
        deserialized_task_to_compute = self._get_deserialized_task_to_compute(
            timestamp   = "2017-12-01 10:00:00",
            deadline    = "2017-12-01 11:00:00",
            task_id     = '1',
            subtask_id  = '8',
        )
        deserialized_report_computed_task = self._get_deserialized_report_computed_task(
            task_to_compute = deserialized_task_to_compute,
            timestamp       = "2017-12-01 11:00:09",
        )
        serialized_force_get_task_result = self._get_serialized_force_get_task_result(
            report_computed_task = deserialized_report_computed_task,
            timestamp       = "2017-12-01 11:00:09",
        )

        with freeze_time("2017-12-01 11:00:10"):
            response = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_get_task_result,
                content_type                        = 'application/octet-stream',
            )

        self.assertEqual(response.status_code,  200)

        message_from_concent = load(response.content, self.REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY, check_time = False)

        self.assertIsInstance(message_from_concent,         message.concents.AckForceGetTaskResult)
        self.assertEqual(message_from_concent.timestamp,    self._parse_iso_date_to_timestamp("2017-12-01 11:00:10"))

        self._assert_stored_message_counter_increased(increased_by = 2)
        self._test_subtask_state(
            task_id                  = '1',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.FORCING_RESULT_TRANSFER,
            provider_key             = self._get_encoded_provider_public_key(),
            requestor_key            = self._get_encoded_requestor_public_key(),
            expected_nested_messages = {'task_to_compute', 'report_computed_task'},
            next_deadline            = self._parse_iso_date_to_timestamp("2017-12-01 11:00:29"),
        )
        self._test_last_stored_messages(
            expected_messages = [
                message.tasks.TaskToCompute,
                message.tasks.ReportComputedTask,
            ],
            task_id         = '1',
            subtask_id      = '8',
            timestamp       = "2017-12-01 11:00:10"
        )
        self._test_undelivered_pending_responses(
            subtask_id                         = '8',
            client_public_key                  = self._get_encoded_provider_public_key(),
            expected_pending_responses_receive = [
                PendingResponse.ResponseType.ForceGetTaskResultUpload,
            ]
        )

        self._assert_client_count_is_equal(2)

    def test_concent_requests_task_result_from_provider_and_requestor_receives_failure_because_provider_does_not_submit(self):
        """
        Tests if on requestor ForceGetTaskResult message Concent will return ForceGetTaskResultFailed
        if provider doesn't submit result.

        Expected message exchange:
        Requestor -> Concent:     ForceGetTaskResult
        Concent   -> Requestor:   AckForceGetTaskResult
        Concent   -> Provider:    ForceGetTaskResultUpload
        Provider  -> Concent:     no response
        Concent   -> Requestor:   ForceGetTaskResultFailed
        """

        # STEP 1: Requestor forces get task result via Concent.
        # Concent accepts request if all conditions were met.
        deserialized_task_to_compute = self._get_deserialized_task_to_compute(
            timestamp   = "2017-12-01 10:00:00",
            task_id     = '99',
            subtask_id  = '8',
            deadline    = "2017-12-01 11:00:00"
        )
        deserialized_report_computed_task = self._get_deserialized_report_computed_task(
            task_to_compute = deserialized_task_to_compute,
            timestamp       = "2017-12-01 11:00:01",
        )
        serialized_force_get_task_result = self._get_serialized_force_get_task_result(
            report_computed_task = deserialized_report_computed_task,
            timestamp       = "2017-12-01 11:00:01",
        )
        deserialized_force_get_task_result = load(
            serialized_force_get_task_result,
            CONCENT_PRIVATE_KEY,
            self.REQUESTOR_PUBLIC_KEY,
            check_time = False,
        )

        with freeze_time("2017-12-01 11:00:01"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_get_task_result,
                content_type                        = 'application/octet-stream',
            )

        self.assertEqual(response_1.status_code, 200)
        self._assert_stored_message_counter_increased(increased_by = 2)
        self._test_subtask_state(
            task_id                  = '99',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.FORCING_RESULT_TRANSFER,
            provider_key             = self._get_encoded_provider_public_key(),
            requestor_key            = self._get_encoded_requestor_public_key(),
            expected_nested_messages = {'task_to_compute', 'report_computed_task'},
            next_deadline            = self._parse_iso_date_to_timestamp("2017-12-01 11:00:21"),
        )
        self._test_last_stored_messages(
            expected_messages = [
                message.tasks.TaskToCompute,
                message.tasks.ReportComputedTask,
            ],
            task_id         = '99',
            subtask_id      = '8',
            timestamp       = "2017-12-01 11:00:01"
        )
        self._test_undelivered_pending_responses(
            subtask_id                         = '8',
            client_public_key                  = self._get_encoded_provider_public_key(),
            expected_pending_responses_receive = [
                PendingResponse.ResponseType.ForceGetTaskResultUpload,
            ]
        )

        # STEP 2: Provider receives force get task result and file transfer token inside ForceGetTaskResultUpload via Concent.
        with mock.patch('core.transfer_operations.request_upload_status', request_upload_status_false_mock):
            with freeze_time("2017-12-01 11:00:12"):
                response_2 = self.client.post(
                    reverse('core:receive'),
                    data                           = self._create_provider_auth_message(),
                    content_type                   = 'application/octet-stream',
                )

        self.assertEqual(response_2.status_code, 200)
        self._assert_stored_message_counter_increased(increased_by = 0)

        message_from_concent = load(response_2.content, self.PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY, check_time = False)
        self.assertIsInstance(message_from_concent,     message.concents.ForceGetTaskResultUpload)

        # Assign each message to correct variable
        message_force_get_task_result = message_from_concent.force_get_task_result
        message_file_transfer_token = message_from_concent.file_transfer_token

        # Test ForceGetTaskResult message

        self.assertEqual(message_from_concent.timestamp,            self._parse_iso_date_to_timestamp("2017-12-01 11:00:12"))
        self.assertIsInstance(message_force_get_task_result,        message.concents.ForceGetTaskResult)
        self.assertEqual(message_force_get_task_result.timestamp,   self._parse_iso_date_to_timestamp("2017-12-01 11:00:12"))
        self.assertEqual(
            message_force_get_task_result.report_computed_task.task_to_compute,
            deserialized_force_get_task_result.report_computed_task.task_to_compute
        )
        self.assertEqual(
            message_force_get_task_result.report_computed_task.task_to_compute.compute_task_def,
            deserialized_force_get_task_result.report_computed_task.task_to_compute.compute_task_def
        )
        self.assertEqual(
            message_force_get_task_result.report_computed_task.task_to_compute.compute_task_def['deadline'],
            self._parse_iso_date_to_timestamp("2017-12-01 11:00:00")
        )
        self.assertEqual(message_force_get_task_result.report_computed_task.task_to_compute.compute_task_def['task_id'], '99')

        # Test FileTransferToken message
        self.assertIsInstance(message_file_transfer_token, message.FileTransferToken)
        self.assertEqual(message_file_transfer_token.sig,  self._add_signature_to_message(message_file_transfer_token, CONCENT_PRIVATE_KEY))
        self.assertEqual(message_file_transfer_token.authorized_client_public_key, self.PROVIDER_PUBLIC_KEY)
        self.assertEqual(message_file_transfer_token.subtask_id, deserialized_task_to_compute.compute_task_def['subtask_id'])  # pylint: disable=no-member
        self.assertEqual(message_file_transfer_token.timestamp, self._parse_iso_date_to_timestamp("2017-12-01 11:00:12"))
        self.assertEqual(message_file_transfer_token.token_expiration_deadline, self._parse_iso_date_to_timestamp("2017-12-01 11:02:32"))
        self.assertEqual(message_file_transfer_token.operation, FileTransferToken.Operation.upload)

        # STEP 3: Requestor receives force get task result failed due to lack of provider submit.
        with mock.patch('core.transfer_operations.request_upload_status', request_upload_status_false_mock):
            with freeze_time("2017-12-01 11:00:21"):
                response_3 = self.client.post(
                    reverse('core:receive'),
                    data                           = self._create_requestor_auth_message(),
                    content_type                   = 'application/octet-stream',
                )

        self.assertEqual(response_3.status_code, 200)
        self._assert_stored_message_counter_not_increased()
        self._test_subtask_state(
            task_id                  = '99',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.FAILED,
            provider_key             = self._get_encoded_provider_public_key(),
            requestor_key            = self._get_encoded_requestor_public_key(),
            expected_nested_messages = {'task_to_compute', 'report_computed_task'},
            next_deadline            = None,
        )

        message_from_concent = load(response_3.content, self.REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY, check_time = False)

        self.assertIsInstance(message_from_concent,                             message.concents.ForceGetTaskResultFailed)
        self.assertEqual(message_from_concent.timestamp,                        self._parse_iso_date_to_timestamp("2017-12-01 11:00:21"))
        self.assertEqual(message_from_concent.task_to_compute,                  deserialized_task_to_compute)
        self.assertEqual(message_from_concent.task_to_compute.compute_task_def, deserialized_task_to_compute.compute_task_def)   # pylint: disable=no-member
        self.assertEqual(
            message_from_concent.task_to_compute.compute_task_def['deadline'],
            self._parse_iso_date_to_timestamp("2017-12-01 11:00:00")
        )
        self.assertEqual(message_from_concent.task_to_compute.compute_task_def['task_id'], '99')

        self._assert_client_count_is_equal(2)

    def test_concent_requests_task_result_from_provider_and_requestor_receives_failure_because_provider_does_not_finish_upload(self):
        """
        Tests if on requestor ForceGetTaskResult message Concent will return ForceGetTaskResultFailed
        if provider doesn't finish upload result.

        Expected message exchange:
        Requestor -> Concent:     ForceGetTaskResult
        Concent   -> Requestor:   AckForceGetTaskResult
        Concent   -> Requestor:   ForceGetTaskResultFailed
        """

        # STEP 1: Requestor forces get task result via Concent.
        # Concent accepts request if all conditions were met.
        deserialized_task_to_compute = self._get_deserialized_task_to_compute(
            timestamp   = "2017-12-01 10:00:00",
            task_id     = '99',
            subtask_id  = '8',
            deadline    = "2017-12-01 11:00:00"
        )
        deserialized_report_computed_task = self._get_deserialized_report_computed_task(
            task_to_compute = deserialized_task_to_compute,
            timestamp       = "2017-12-01 11:00:01",
        )
        serialized_force_get_task_result = self._get_serialized_force_get_task_result(
            report_computed_task = deserialized_report_computed_task,
            timestamp       = "2017-12-01 11:00:01",
        )

        with freeze_time("2017-12-01 11:00:01"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_get_task_result,
                content_type                        = 'application/octet-stream',
            )

        self.assertEqual(response_1.status_code, 200)
        self._assert_stored_message_counter_increased(increased_by = 2)
        self._test_subtask_state(
            task_id                  = '99',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.FORCING_RESULT_TRANSFER,
            provider_key             = self._get_encoded_provider_public_key(),
            requestor_key            = self._get_encoded_requestor_public_key(),
            next_deadline            = self._parse_iso_date_to_timestamp("2017-12-01 11:00:21"),
            expected_nested_messages = {'task_to_compute', 'report_computed_task'},
        )
        self._test_undelivered_pending_responses(
            subtask_id                         = '8',
            client_public_key                  = self._get_encoded_provider_public_key(),
            expected_pending_responses_receive = [
                PendingResponse.ResponseType.ForceGetTaskResultUpload,
            ]
        )

        # STEP 2: Provider receives force get task result and file transfer token inside ForceGetTaskResultUpload via Concent.
        with mock.patch('core.transfer_operations.request_upload_status', request_upload_status_false_mock):
            with freeze_time("2017-12-01 11:00:12"):
                response_2 = self.client.post(
                    reverse('core:receive'),
                    data                           = self._create_provider_auth_message(),
                    content_type                   = 'application/octet-stream',
                )

        self.assertEqual(response_2.status_code, 200)
        self._assert_stored_message_counter_increased(increased_by = 0)
        self._test_subtask_state(
            task_id                  = '99',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.FORCING_RESULT_TRANSFER,
            provider_key             = self._get_encoded_provider_public_key(),
            requestor_key            = self._get_encoded_requestor_public_key(),
            next_deadline            = self._parse_iso_date_to_timestamp("2017-12-01 11:00:21"),
            expected_nested_messages = {'task_to_compute', 'report_computed_task'},
        )

        # STEP 2: Requestor receives force get task result failed due to lack of provider submit.
        with mock.patch('core.transfer_operations.request_upload_status', request_upload_status_false_mock):
            with freeze_time("2017-12-01 11:00:21"):
                response_3 = self.client.post(
                    reverse('core:receive'),
                    data                           = self._create_requestor_auth_message(),
                    content_type                   = 'application/octet-stream',
                )

        self.assertEqual(response_3.status_code, 200)
        self._assert_stored_message_counter_not_increased()
        self._test_subtask_state(
            task_id                  = '99',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.FAILED,
            provider_key             = self._get_encoded_provider_public_key(),
            requestor_key            = self._get_encoded_requestor_public_key(),
            next_deadline            = None,
            expected_nested_messages = {'task_to_compute', 'report_computed_task'},
        )

        message_from_concent = load(response_3.content, self.REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY, check_time = False)

        self.assertIsInstance(message_from_concent,                             message.concents.ForceGetTaskResultFailed)
        self.assertEqual(message_from_concent.timestamp,                        self._parse_iso_date_to_timestamp("2017-12-01 11:00:21"))
        self.assertEqual(message_from_concent.task_to_compute,                  deserialized_task_to_compute)
        self.assertEqual(message_from_concent.task_to_compute.compute_task_def, deserialized_task_to_compute.compute_task_def)   # pylint: disable=no-member
        self.assertEqual(
            message_from_concent.task_to_compute.compute_task_def['deadline'],
            self._parse_iso_date_to_timestamp("2017-12-01 11:00:00")
        )
        self.assertEqual(message_from_concent.task_to_compute.compute_task_def['task_id'], '99')

    def test_concent_requests_task_result_from_provider_and_requestor_receives_force_get_task_upload_because_file_already_uploaded(self):
        """
        Tests if on requestor ForceGetTaskResult message Concent will return ForceGetTaskResultFailed
        if provider doesn't finish upload result.

        Expected message exchange:
        Requestor -> Concent:     ForceGetTaskResult
        Concent   -> Requestor:   AckForceGetTaskResult
        Concent   -> Requestor:   ForceGetTaskResultUpload
        """

        # STEP 1: Requestor forces get task result via Concent.
        # Concent accepts request if all conditions were met.
        deserialized_task_to_compute = self._get_deserialized_task_to_compute(
            timestamp   = "2017-12-01 10:00:00",
            task_id     = '99',
            subtask_id  = '8',
            deadline    = "2017-12-01 11:00:00"
        )
        deserialized_report_computed_task = self._get_deserialized_report_computed_task(
            task_to_compute = deserialized_task_to_compute,
            timestamp       = "2017-12-01 11:00:01",
        )
        serialized_force_get_task_result = self._get_serialized_force_get_task_result(
            report_computed_task = deserialized_report_computed_task,
            timestamp       = "2017-12-01 11:00:01",
        )
        deserialized_force_get_task_result = load(
            serialized_force_get_task_result,
            CONCENT_PRIVATE_KEY,
            self.REQUESTOR_PUBLIC_KEY,
            check_time = False,
        )

        with freeze_time("2017-12-01 11:00:01"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_get_task_result,
                content_type                        = 'application/octet-stream',
            )

        self.assertEqual(response_1.status_code, 200)
        self._assert_stored_message_counter_increased(increased_by = 2)
        self._test_subtask_state(
            task_id                  = '99',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.FORCING_RESULT_TRANSFER,
            provider_key             = self._get_encoded_provider_public_key(),
            requestor_key            = self._get_encoded_requestor_public_key(),
            expected_nested_messages = {'task_to_compute', 'report_computed_task'},
            next_deadline            = self._parse_iso_date_to_timestamp("2017-12-01 11:00:21"),
        )
        self._test_last_stored_messages(
            expected_messages = [
                message.tasks.TaskToCompute,
                message.tasks.ReportComputedTask,
            ],
            task_id         = '99',
            subtask_id      = '8',
            timestamp       = "2017-12-01 11:00:01"
        )

        # STEP 2: Provider receives force get task result and file transfer token inside ForceGetTaskResultUpload via Concent.
        with mock.patch('core.transfer_operations.request_upload_status', request_upload_status_false_mock):
            with freeze_time("2017-12-01 11:00:06"):
                response_2 = self.client.post(
                    reverse('core:receive'),
                    data                           = self._create_provider_auth_message(),
                    content_type                   = 'application/octet-stream',
                )

        self.assertEqual(response_2.status_code, 200)
        self._assert_stored_message_counter_increased(increased_by = 0)

        message_from_concent = load(response_2.content, self.PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY, check_time = False)
        self.assertIsInstance(message_from_concent, message.concents.ForceGetTaskResultUpload)

        # Assign each message to correct variable
        message_force_get_task_result = message_from_concent.force_get_task_result
        message_file_transfer_token = message_from_concent.file_transfer_token

        # Test ForceGetTaskResult message

        self.assertEqual(message_from_concent.timestamp,            self._parse_iso_date_to_timestamp("2017-12-01 11:00:06"))
        self.assertIsInstance(message_force_get_task_result,        message.concents.ForceGetTaskResult)
        self.assertEqual(message_force_get_task_result.timestamp,   self._parse_iso_date_to_timestamp("2017-12-01 11:00:06"))
        self.assertEqual(
            message_force_get_task_result.report_computed_task.task_to_compute,
            deserialized_force_get_task_result.report_computed_task.task_to_compute,
        )
        self.assertEqual(
            message_force_get_task_result.report_computed_task.task_to_compute.compute_task_def,
            deserialized_force_get_task_result.report_computed_task.task_to_compute.compute_task_def,
        )
        self.assertEqual(
            message_force_get_task_result.report_computed_task.task_to_compute.compute_task_def['deadline'],
            self._parse_iso_date_to_timestamp("2017-12-01 11:00:00")
        )
        self.assertEqual(message_force_get_task_result.report_computed_task.task_to_compute.compute_task_def['task_id'], '99')

        # Test FileTransferToken message
        self.assertIsInstance(message_file_transfer_token,                      message.FileTransferToken)
        self.assertEqual(message_file_transfer_token.sig,                       self._add_signature_to_message(message_file_transfer_token, CONCENT_PRIVATE_KEY))
        self.assertEqual(message_file_transfer_token.authorized_client_public_key, self.PROVIDER_PUBLIC_KEY)
        self.assertEqual(message_file_transfer_token.subtask_id,                deserialized_task_to_compute.compute_task_def['subtask_id'])  # pylint: disable=no-member
        self.assertEqual(message_file_transfer_token.timestamp,                 self._parse_iso_date_to_timestamp("2017-12-01 11:00:06"))
        self.assertEqual(message_file_transfer_token.token_expiration_deadline, self._parse_iso_date_to_timestamp("2017-12-01 11:02:32"))
        self.assertEqual(message_file_transfer_token.operation, FileTransferToken.Operation.upload)

        # STEP 3: Requestor receives force get task result upload.
        with mock.patch('core.transfer_operations.request_upload_status', request_upload_status_true_mock):
            with freeze_time("2017-12-01 11:00:21"):
                response_3 = self.client.post(
                    reverse('core:receive'),
                    data                           = self._create_requestor_auth_message(),
                    content_type                   = 'application/octet-stream',
                )

        self.assertEqual(response_3.status_code, 200)
        self._assert_stored_message_counter_increased(increased_by = 0)
        self._test_subtask_state(
            task_id                  = '99',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.RESULT_UPLOADED,  # Should be FAILED?
            provider_key             = self._get_encoded_provider_public_key(),
            requestor_key            = self._get_encoded_requestor_public_key(),
            expected_nested_messages = {'task_to_compute', 'report_computed_task'},
            next_deadline            = None,
        )

        message_from_concent = load(response_3.content, self.REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY, check_time = False)

        self.assertIsInstance(message_from_concent,                                                         message.concents.ForceGetTaskResultDownload)
        self.assertEqual(message_from_concent.timestamp,                                                    self._parse_iso_date_to_timestamp("2017-12-01 11:00:21"))
        self.assertEqual(message_from_concent.force_get_task_result.report_computed_task.task_to_compute,   deserialized_task_to_compute)
        self.assertIsInstance(message_from_concent.file_transfer_token,                                     message.FileTransferToken)
        self.assertEqual(message_from_concent.file_transfer_token.sig,                                      self._add_signature_to_message(message_from_concent.file_transfer_token, CONCENT_PRIVATE_KEY))
        self.assertEqual(message_from_concent.file_transfer_token.authorized_client_public_key, self.REQUESTOR_PUBLIC_KEY)
        self.assertEqual(message_from_concent.file_transfer_token.subtask_id,                               deserialized_task_to_compute.compute_task_def['subtask_id'])  # pylint: disable=no-member
        self.assertEqual(message_from_concent.file_transfer_token.timestamp,                                self._parse_iso_date_to_timestamp("2017-12-01 11:00:21"))
        self.assertEqual(message_from_concent.file_transfer_token.token_expiration_deadline,                self._parse_iso_date_to_timestamp("2017-12-01 11:30:00"))
        self.assertEqual(message_from_concent.file_transfer_token.operation, FileTransferToken.Operation.download)

        self._assert_client_count_is_equal(2)

    def test_concent_requests_task_result_from_provider_and_requestor_receives_failure_because_provider_uploads_bad_files(self):
        """
        Tests if on requestor ForceGetTaskResult message Concent will return ForceGetTaskResultFailed
        if provider uploads bad or incomplete result.

        Expected message exchange:
        Requestor -> Concent:     ForceGetTaskResult
        Concent   -> Requestor:   AckForceGetTaskResult
        Concent   -> Provider:    ForceGetTaskResultUpload
        Provider  -> Concent:     TODO: Upload bad files
        Concent   -> Requestor:   ForceGetTaskResultFailed
        """

        # STEP 1: Requestor forces get task result via Concent.
        # Concent accepts request if all conditions were met.
        deserialized_task_to_compute = self._get_deserialized_task_to_compute(
            timestamp   = "2017-12-01 10:00:00",
            task_id     = '99',
            subtask_id  = '8',
            deadline    = "2017-12-01 11:00:00"
        )
        deserialized_report_computed_task = self._get_deserialized_report_computed_task(
            task_to_compute = deserialized_task_to_compute,
            timestamp       = "2017-12-01 11:00:01",
        )
        serialized_force_get_task_result = self._get_serialized_force_get_task_result(
            report_computed_task = deserialized_report_computed_task,
            timestamp       = "2017-12-01 11:00:01",
        )
        deserialized_force_get_task_result = load(
            serialized_force_get_task_result,
            CONCENT_PRIVATE_KEY,
            self.REQUESTOR_PUBLIC_KEY,
            check_time = False,
        )

        with freeze_time("2017-12-01 11:00:01"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_get_task_result,
                content_type                        = 'application/octet-stream',
            )

        self.assertEqual(response_1.status_code, 200)
        self._assert_stored_message_counter_increased(increased_by = 2)
        self._test_subtask_state(
            task_id                  = '99',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.FORCING_RESULT_TRANSFER,
            provider_key             = self._get_encoded_provider_public_key(),
            requestor_key            = self._get_encoded_requestor_public_key(),
            expected_nested_messages = {'task_to_compute', 'report_computed_task'},
            next_deadline            = self._parse_iso_date_to_timestamp("2017-12-01 11:00:21"),
        )
        self._test_last_stored_messages(
            expected_messages = [
                message.tasks.TaskToCompute,
                message.tasks.ReportComputedTask,
            ],
            task_id         = '99',
            subtask_id      = '8',
            timestamp       = "2017-12-01 11:00:01"
        )

        # STEP 2: Provider receives force get task result and file transfer token inside ForceGetTaskResultUpload via Concent.
        with mock.patch('core.transfer_operations.request_upload_status', request_upload_status_true_mock):
            with freeze_time("2017-12-01 11:00:12"):
                response_2 = self.client.post(
                    reverse('core:receive'),
                    data                           = self._create_provider_auth_message(),
                    content_type                   = 'application/octet-stream',
                )

        self.assertEqual(response_2.status_code, 200)
        self._assert_stored_message_counter_increased(increased_by = 0)

        message_from_concent = load(response_2.content, self.PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY, check_time = False)
        self.assertIsInstance(message_from_concent, message.concents.ForceGetTaskResultUpload)

        # Assign each message to correct variable
        message_force_get_task_result   = message_from_concent.force_get_task_result
        message_file_transfer_token     = message_from_concent.file_transfer_token

        # Test ForceGetTaskResult message

        self.assertEqual(message_from_concent.timestamp,            self._parse_iso_date_to_timestamp("2017-12-01 11:00:12"))
        self.assertIsInstance(message_force_get_task_result,        message.concents.ForceGetTaskResult)
        self.assertEqual(message_force_get_task_result.timestamp,   self._parse_iso_date_to_timestamp("2017-12-01 11:00:12"))
        self.assertEqual(
            message_force_get_task_result.report_computed_task.task_to_compute,
            deserialized_force_get_task_result.report_computed_task.task_to_compute
        )
        self.assertEqual(
            message_force_get_task_result.report_computed_task.task_to_compute.compute_task_def,
            deserialized_force_get_task_result.report_computed_task.task_to_compute.compute_task_def
        )
        self.assertEqual(
            message_force_get_task_result.report_computed_task.task_to_compute.compute_task_def['deadline'],
            self._parse_iso_date_to_timestamp("2017-12-01 11:00:00")
        )
        self.assertEqual(message_force_get_task_result.report_computed_task.task_to_compute.compute_task_def['task_id'], '99')

        # Test FileTransferToken message
        self.assertIsInstance(message_file_transfer_token,                      message.FileTransferToken)
        self.assertEqual(message_file_transfer_token.sig,                       self._add_signature_to_message(message_file_transfer_token, CONCENT_PRIVATE_KEY))
        self.assertEqual(message_file_transfer_token.authorized_client_public_key, self.PROVIDER_PUBLIC_KEY)
        self.assertEqual(message_file_transfer_token.subtask_id,                deserialized_task_to_compute.compute_task_def['subtask_id'])  # pylint: disable=no-member
        self.assertEqual(message_file_transfer_token.timestamp,                 self._parse_iso_date_to_timestamp("2017-12-01 11:00:12"))
        self.assertEqual(message_file_transfer_token.token_expiration_deadline, self._parse_iso_date_to_timestamp("2017-12-01 11:02:32"))
        self.assertEqual(message_file_transfer_token.operation, FileTransferToken.Operation.upload)

        # STEP 3: Requestor receives force get task result failed due to lack of provider submit.
        with mock.patch('core.transfer_operations.request_upload_status', request_upload_status_true_mock):
            with freeze_time("2017-12-01 11:00:21"):
                response_3 = self.client.post(
                    reverse('core:receive'),
                    data         = self._create_requestor_auth_message(),
                    content_type = 'application/octet-stream',
                )

        self.assertEqual(response_3.status_code, 200)
        self._assert_stored_message_counter_increased(increased_by = 0)
        self._test_subtask_state(
            task_id                  = '99',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.RESULT_UPLOADED,
            provider_key             = self._get_encoded_provider_public_key(),
            requestor_key            = self._get_encoded_requestor_public_key(),
            expected_nested_messages = {'task_to_compute', 'report_computed_task'},
            next_deadline            = None,
        )

        message_from_concent = load(response_3.content, self.REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY, check_time = False)

        self.assertIsInstance(message_from_concent,                                                                         message.concents.ForceGetTaskResultDownload)
        self.assertEqual(message_from_concent.timestamp,                                                                    self._parse_iso_date_to_timestamp("2017-12-01 11:00:21"))
        self.assertEqual(message_from_concent.file_transfer_token.sig,                                                      self._add_signature_to_message(message_from_concent.file_transfer_token, CONCENT_PRIVATE_KEY))
        self.assertEqual(message_from_concent.file_transfer_token.authorized_client_public_key, self.REQUESTOR_PUBLIC_KEY)
        self.assertEqual(message_from_concent.force_get_task_result.report_computed_task.task_to_compute,                   deserialized_task_to_compute)
        self.assertEqual(message_from_concent.force_get_task_result.report_computed_task.task_to_compute.compute_task_def,  deserialized_task_to_compute.compute_task_def)   # pylint: disable=no-member
        self.assertEqual(
            message_from_concent.force_get_task_result.report_computed_task.task_to_compute.compute_task_def['deadline'],
            self._parse_iso_date_to_timestamp("2017-12-01 11:00:00")
        )
        self.assertEqual(message_from_concent.force_get_task_result.report_computed_task.task_to_compute.compute_task_def['task_id'], '99')

        self._assert_client_count_is_equal(2)

    def test_concent_requests_task_result_from_provider_and_requestor_receives_task_result(self):
        """
        Tests if on requestor ForceGetTaskResult message Concent will return ForceGetTaskResultUpload
        if provider uploads correct result.

        Expected message exchange:
        Requestor -> Concent:     ForceGetTaskResult
        Concent   -> Requestor:   AckForceGetTaskResult
        Concent   -> Provider:    ForceGetTaskResultUpload
        Provider  -> Concent:     Upload good files
        Concent   -> Requestor:   ForceGetTaskResultDownload
        """

        # STEP 1: Requestor forces get task result via Concent.
        # Concent accepts request if all conditions were met.
        deserialized_task_to_compute = self._get_deserialized_task_to_compute(
            timestamp   = "2017-12-01 10:00:00",
            task_id     = '99',
            subtask_id  = '8',
            deadline    = "2017-12-01 11:00:00"
        )
        deserialized_report_computed_task = self._get_deserialized_report_computed_task(
            task_to_compute = deserialized_task_to_compute,
            timestamp       = "2017-12-01 11:00:01",
        )
        serialized_force_get_task_result = self._get_serialized_force_get_task_result(
            report_computed_task = deserialized_report_computed_task,
            timestamp            = "2017-12-01 11:00:01",
        )
        deserialized_force_get_task_result = load(
            serialized_force_get_task_result,
            CONCENT_PRIVATE_KEY,
            self.REQUESTOR_PUBLIC_KEY,
            check_time = False,
        )

        with freeze_time("2017-12-01 11:00:01"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_get_task_result,
                content_type                        = 'application/octet-stream',
            )

        self.assertEqual(response_1.status_code, 200)
        self._assert_stored_message_counter_increased(increased_by = 2)
        self._test_subtask_state(
            task_id                  = '99',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.FORCING_RESULT_TRANSFER,
            provider_key             = self._get_encoded_provider_public_key(),
            requestor_key            = self._get_encoded_requestor_public_key(),
            expected_nested_messages = {'task_to_compute', 'report_computed_task'},
            next_deadline            = self._parse_iso_date_to_timestamp("2017-12-01 11:00:21"),
        )
        self._test_last_stored_messages(
            expected_messages = [
                message.tasks.TaskToCompute,
                message.tasks.ReportComputedTask,
            ],
            task_id         = '99',
            subtask_id      = '8',
            timestamp       = "2017-12-01 11:00:01"
        )
        self._test_undelivered_pending_responses(
            subtask_id                         = '8',
            client_public_key                  = self._get_encoded_provider_public_key(),
            expected_pending_responses_receive = [
                PendingResponse.ResponseType.ForceGetTaskResultUpload,
            ]
        )

        # STEP 2: Provider receives force get task result and file transfer token inside ForceGetTaskResultUpload via Concent.
        with mock.patch('core.transfer_operations.request_upload_status', request_upload_status_false_mock):
            with freeze_time("2017-12-01 11:00:12"):
                response_2 = self.client.post(
                    reverse('core:receive'),
                    data                           = self._create_provider_auth_message(),
                    content_type                   = 'application/octet-stream',
                )

        self.assertEqual(response_2.status_code, 200)
        self._assert_stored_message_counter_not_increased()

        message_from_concent = load(response_2.content, self.PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY, check_time = False)
        self.assertIsInstance(message_from_concent, message.concents.ForceGetTaskResultUpload)

        # Assign each message to correct variable
        message_force_get_task_result   = message_from_concent.force_get_task_result
        message_file_transfer_token     = message_from_concent.file_transfer_token

        # Test ForceGetTaskResult message

        self.assertEqual(message_from_concent.timestamp,                                                        self._parse_iso_date_to_timestamp("2017-12-01 11:00:12"))
        self.assertIsInstance(message_force_get_task_result,                                                    message.concents.ForceGetTaskResult)
        self.assertEqual(message_force_get_task_result.timestamp,                                               self._parse_iso_date_to_timestamp("2017-12-01 11:00:12"))
        self.assertEqual(message_force_get_task_result.report_computed_task.task_to_compute,                    deserialized_task_to_compute)
        self.assertEqual(message_force_get_task_result.report_computed_task.task_to_compute.compute_task_def,   deserialized_task_to_compute.compute_task_def)   # pylint: disable=no-member
        self.assertEqual(
            message_force_get_task_result.report_computed_task.task_to_compute.compute_task_def['deadline'],
            self._parse_iso_date_to_timestamp("2017-12-01 11:00:00")
        )
        self.assertEqual(message_force_get_task_result.report_computed_task.task_to_compute.compute_task_def['task_id'], '99')

        # Test FileTransferToken message
        self.assertIsInstance(message_file_transfer_token, message.FileTransferToken)
        self.assertEqual(message_file_transfer_token.sig,       self._add_signature_to_message(message_file_transfer_token, CONCENT_PRIVATE_KEY))
        self.assertEqual(message_file_transfer_token.authorized_client_public_key, self.PROVIDER_PUBLIC_KEY)
        self.assertEqual(message_file_transfer_token.subtask_id, deserialized_task_to_compute.compute_task_def['subtask_id'])  # pylint: disable=no-member
        self.assertEqual(message_file_transfer_token.timestamp, self._parse_iso_date_to_timestamp("2017-12-01 11:00:12"))
        self.assertEqual(message_file_transfer_token.token_expiration_deadline, self._parse_iso_date_to_timestamp("2017-12-01 11:02:32"))
        self.assertEqual(message_file_transfer_token.operation, FileTransferToken.Operation.upload)

        # STEP 3: Requestor receives force get task result download because Provider uploaded file.
        with mock.patch('core.transfer_operations.request_upload_status', request_upload_status_true_mock):
            with freeze_time("2017-12-01 11:00:21"):
                response_3 = self.client.post(
                    reverse('core:receive'),
                    data                           = self._create_requestor_auth_message(),
                    content_type                   = 'application/octet-stream',
                )

        self.assertEqual(response_3.status_code,  200)
        self._test_subtask_state(
            task_id                  = '99',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.RESULT_UPLOADED,
            provider_key             = self._get_encoded_provider_public_key(),
            requestor_key            = self._get_encoded_requestor_public_key(),
            expected_nested_messages = {'task_to_compute', 'report_computed_task'},
            next_deadline            = None,
        )

        message_from_concent = load(response_3.content, self.REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY, check_time = False)

        self.assertIsInstance(message_from_concent,         message.concents.ForceGetTaskResultDownload)
        self.assertEqual(message_from_concent.timestamp,    self._parse_iso_date_to_timestamp("2017-12-01 11:00:21"))

        self.assertEqual(
            message_from_concent.force_get_task_result.report_computed_task.task_to_compute,
            deserialized_force_get_task_result.report_computed_task.task_to_compute,
        )
        self.assertEqual(
            message_from_concent.force_get_task_result.report_computed_task.task_to_compute.compute_task_def,
            deserialized_force_get_task_result.report_computed_task.task_to_compute.compute_task_def,
        )
        self.assertEqual(
            message_from_concent.force_get_task_result.report_computed_task.task_to_compute.compute_task_def['deadline'],
            self._parse_iso_date_to_timestamp("2017-12-01 11:00:00")
        )
        self.assertEqual(message_from_concent.force_get_task_result.report_computed_task.task_to_compute.compute_task_def['task_id'], '99')

        self.assertIsInstance(message_from_concent.file_transfer_token, message.FileTransferToken)
        self.assertEqual(message_from_concent.file_transfer_token.sig,  self._add_signature_to_message(message_from_concent.file_transfer_token, CONCENT_PRIVATE_KEY))
        self.assertEqual(message_from_concent.file_transfer_token.authorized_client_public_key, self.REQUESTOR_PUBLIC_KEY)
        self.assertEqual(message_from_concent.file_transfer_token.subtask_id, deserialized_task_to_compute.compute_task_def['subtask_id'])  # pylint: disable=no-member
        self.assertEqual(
            message_from_concent.file_transfer_token.timestamp,
            self._parse_iso_date_to_timestamp("2017-12-01 11:00:21")
        )
        self.assertEqual(
            message_from_concent.file_transfer_token.token_expiration_deadline,
            self._parse_iso_date_to_timestamp("2017-12-01 11:30:00")
        )
        self.assertEqual(message_from_concent.file_transfer_token.operation, FileTransferToken.Operation.download)

        self._assert_client_count_is_equal(2)
