import mock

from django.test            import override_settings
from django.urls            import reverse
from freezegun              import freeze_time
from golem_messages         import load
from golem_messages         import message
from golem_messages.message import FileTransferToken

from core.models            import PendingResponse
from core.models            import Subtask
from core.tests.utils       import ConcentIntegrationTestCase
from core.tests.utils import parse_iso_date_to_timestamp
from common.constants        import ErrorCode
from common.testing_helpers  import generate_ecc_key_pair


(CONCENT_PRIVATE_KEY, CONCENT_PUBLIC_KEY)                         = generate_ecc_key_pair()


def request_upload_status_true_mock( _report_computed_task):
    return True


def request_upload_status_false_mock(_report_computed_task):
    return False


@override_settings(
    CONCENT_PRIVATE_KEY         = CONCENT_PRIVATE_KEY,
    CONCENT_PUBLIC_KEY          = CONCENT_PUBLIC_KEY,
    CONCENT_MESSAGING_TIME      = 10,    # seconds
    FORCE_ACCEPTANCE_TIME       = 10,    # seconds
    MINIMUM_UPLOAD_RATE         = 1,     # bits per second
    DOWNLOAD_LEADIN_TIME        = 10,    # seconds
)
class AuthGetTaskResultIntegrationTest(ConcentIntegrationTestCase):

    def setUp(self):
        super().setUp()
        self.patcher = mock.patch('core.transfer_operations.calculate_subtask_verification_time', return_value=1800)
        self.addCleanup(self.patcher.stop)
        self.patcher.start()

    def test_requestor_forces_get_task_result_and_concent_immediately_sends_rejection_due_to_already_sent_message_should_work_only_with_correct_keys(self):
        """
        Tests if on requestor ForceGetTaskResult message Concent will return ForceGetTaskResultRejected
        if ForceGetTaskResult was already sent by this requestor.

        Expected message exchange:
        Requestor               -> Concent:                 ForceGetTaskResult
        Concent                 -> Requestor:               AckForceGetTaskResult
        WrongRequestor/Provider -> Concent                  ForceGetTaskResult
        Concent                 -> WrongRequestor/Provider  AckForceGetTaskResult
        Requestor               -> Concent:                 ForceGetTaskResult
        Concent                 -> Requestor:               ForceGetTaskResultRejected
        """

        # STEP 1: Requestor forces get task result via Concent.
        deserialized_task_to_compute = self._get_deserialized_task_to_compute(
            timestamp = "2017-12-01 10:00:00",
            deadline  = "2017-12-01 11:00:00",
            task_id     = '1',
            subtask_id  = '8',
        )
        deserialized_report_computed_task = self._get_deserialized_report_computed_task(
            timestamp       = "2017-12-01 11:00:07",
            task_to_compute = deserialized_task_to_compute
        )
        original_serialized_force_get_task_result = self._get_serialized_force_get_task_result(
            report_computed_task = deserialized_report_computed_task,
            timestamp            = "2017-12-01 11:00:08",
        )
        deserialized_original_serialized_force_get_task_result = load(
            original_serialized_force_get_task_result,
            CONCENT_PRIVATE_KEY,
            self.REQUESTOR_PUBLIC_KEY,
            check_time=False
        )

        with freeze_time("2017-12-01 11:00:08"):
            response = self.client.post(
                reverse('core:send'),
                data                                = original_serialized_force_get_task_result,
                content_type                        = 'application/octet-stream',
            )

        self.assertEqual(response.status_code, 200)

        self._assert_stored_message_counter_increased(increased_by = 3)
        self._test_subtask_state(
            task_id                  = '1',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.FORCING_RESULT_TRANSFER,
            provider_key             = self._get_encoded_provider_public_key(),
            requestor_key            = self._get_encoded_requestor_public_key(),
            expected_nested_messages = {'task_to_compute', 'report_computed_task', 'force_get_task_result'},
            next_deadline            = parse_iso_date_to_timestamp("2017-12-01 11:00:52"),
        )
        self._test_last_stored_messages(
            expected_messages = [
                message.tasks.TaskToCompute,
                message.tasks.ReportComputedTask,
                message.concents.ForceGetTaskResult,
            ],
            task_id         = '1',
            subtask_id      = '8',
        )
        self._test_undelivered_pending_responses(
            subtask_id                         = '8',
            client_public_key                  = self._get_encoded_provider_public_key(),
            expected_pending_responses_receive = [
                PendingResponse.ResponseType.ForceGetTaskResultUpload,
            ]
        )

        # STEP 2:
        # 2.1. TaskToCompute is send signed with different key, request is rejected with proper error message.
        # 2.2. TaskToCompute is send with different data, request is rejected with proper error message.

        # 2.1.
        deserialized_task_to_compute.sig = None
        task_to_compute = self._sign_message(
            deserialized_task_to_compute,
            self.DIFFERENT_REQUESTOR_PRIVATE_KEY,
        )

        serialized_force_get_task_result = self._get_serialized_force_get_task_result(
            report_computed_task=self._get_deserialized_report_computed_task(
                task_to_compute=task_to_compute,
                timestamp="2017-12-01 11:00:05",
            ),
            timestamp="2017-12-01 11:00:08",
            requestor_private_key=self.DIFFERENT_REQUESTOR_PRIVATE_KEY,
        )

        with mock.patch(
            'core.transfer_operations.request_upload_status',
            side_effect=request_upload_status_false_mock
        ) as request_upload_status_false_mock_function:
            with freeze_time("2017-12-01 11:00:05"):
                response = self.client.post(
                    reverse('core:send'),
                    data=serialized_force_get_task_result,
                    content_type='application/octet-stream',
                )

        request_upload_status_false_mock_function.assert_called_with(
            deserialized_original_serialized_force_get_task_result.report_computed_task
        )

        self._test_400_response(
            response,
            error_message='There was an exception when validating if golem_message {} is signed with public key {}'.format(
                message.TaskToCompute.__name__,
                self.REQUESTOR_PUBLIC_KEY
            ),
            error_code=ErrorCode.MESSAGE_SIGNATURE_WRONG
        )

        # 2.2.
        task_to_compute.sig = None
        task_to_compute.requestor_public_key = self._get_requestor_hex_public_key()
        task_to_compute.provider_id = 'different_id'
        task_to_compute = self._sign_message(
            task_to_compute,
            self.REQUESTOR_PRIVATE_KEY,
        )

        serialized_force_get_task_result = self._get_serialized_force_get_task_result(
            report_computed_task=self._get_deserialized_report_computed_task(
                task_to_compute=task_to_compute,
                timestamp="2017-12-01 11:00:05",
            ),
            timestamp="2017-12-01 11:00:08",
            requestor_private_key=self.DIFFERENT_REQUESTOR_PRIVATE_KEY,
        )

        with mock.patch(
            'core.transfer_operations.request_upload_status',
            side_effect=request_upload_status_false_mock
        ) as request_upload_status_false_mock_function:
            with freeze_time("2017-12-01 11:00:05"):
                response = self.client.post(
                    reverse('core:send'),
                    data=serialized_force_get_task_result,
                    content_type='application/octet-stream',
                )

        request_upload_status_false_mock_function.assert_called_with(
            deserialized_original_serialized_force_get_task_result.report_computed_task
        )

        self.assertEqual(response.status_code,  200)

        message_from_concent = load(response.content, self.REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY, check_time = False)

        self.assertIsInstance(message_from_concent,      message.concents.ServiceRefused)
        self.assertEqual(message_from_concent.timestamp, parse_iso_date_to_timestamp("2017-12-01 11:00:05"))
        self.assertEqual(message_from_concent.reason,    message_from_concent.REASON.DuplicateRequest)

        # STEP 3: Requestor again forces get task result via Concent with correct key.
        # Concent rejects request immediately because message was already sent.
        with mock.patch(
            'core.transfer_operations.request_upload_status',
            side_effect=request_upload_status_false_mock
        ) as request_upload_status_false_mock_function:
            with freeze_time("2017-12-01 11:00:08"):
                response = self.client.post(
                    reverse('core:send'),
                    data=original_serialized_force_get_task_result,
                    content_type='application/octet-stream',
                )

        request_upload_status_false_mock_function.assert_called_with(
            deserialized_original_serialized_force_get_task_result.report_computed_task
        )

        self.assertEqual(response.status_code,  200)

        message_from_concent = load(response.content, self.REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY, check_time = False)

        self.assertIsInstance(message_from_concent,      message.concents.ServiceRefused)
        self.assertEqual(message_from_concent.timestamp, parse_iso_date_to_timestamp("2017-12-01 11:00:08"))
        self.assertEqual(message_from_concent.reason,    message_from_concent.REASON.DuplicateRequest)

        self._test_undelivered_pending_responses(
            subtask_id                         = '8',
            client_public_key                  = self._get_encoded_provider_public_key(),
            expected_pending_responses_receive = [
                PendingResponse.ResponseType.ForceGetTaskResultUpload,
            ]
        )

        self._assert_stored_message_counter_not_increased()
        self._assert_client_count_is_equal(2)

    def test_concent_requests_task_result_from_provider_and_requestor_receives_failure_because_provider_does_not_submit_should_work_only_with_correct_keys(self):
        """
        Tests if on requestor ForceGetTaskResult message Concent will return ForceGetTaskResultFailed
        if provider doesn't submit result.

        Expected message exchange:
        Requestor -> Concent:                   ForceGetTaskResult
        Concent   -> Requestor:                 AckForceGetTaskResult
        Concent   -> WrongProvider/Requestor:   HTTP 204
        Concent   -> Provider:                  ForceGetTaskResultUpload
        Provider  -> Concent:                   no response
        Concent   -> Requestor:                 ForceGetTaskResultFailed
        Concent   -> WrongRequestor/Provider:   ForceGetTaskResultFailed
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
            timestamp       = "2017-12-01 11:00:00",
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
            response = self.client.post(
                reverse('core:send'),
                data=serialized_force_get_task_result,
                content_type='application/octet-stream',
            )

        self.assertEqual(response.status_code,        200)

        self._assert_stored_message_counter_increased(increased_by = 3)
        self._test_subtask_state(
            task_id                  = '99',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.FORCING_RESULT_TRANSFER,
            provider_key             = self._get_encoded_provider_public_key(),
            requestor_key            = self._get_encoded_requestor_public_key(),
            expected_nested_messages = {'task_to_compute', 'report_computed_task', 'force_get_task_result'},
            next_deadline            = parse_iso_date_to_timestamp("2017-12-01 11:00:52"),
        )
        self._test_last_stored_messages(
            expected_messages = [
                message.tasks.TaskToCompute,
                message.tasks.ReportComputedTask,
                message.concents.ForceGetTaskResult,
            ],
            task_id         = '99',
            subtask_id      = '8',
        )
        self._test_undelivered_pending_responses(
            subtask_id                         = '8',
            client_public_key                  = self._get_encoded_provider_public_key(),
            expected_pending_responses_receive = [
                PendingResponse.ResponseType.ForceGetTaskResultUpload,
            ]
        )

        # STEP 2: Provider do not receive force get task result and file transfer token inside
        # ForceGetTaskResultUpload via Concent with different or mixed key.
        with freeze_time("2017-12-01 11:00:02"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = self._create_diff_provider_auth_message(),
                content_type                   = 'application/octet-stream',
            )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(len(response.content),       0)

        with mock.patch(
            'core.transfer_operations.request_upload_status',
            side_effect=request_upload_status_false_mock
        ) as request_upload_status_false_mock_function:
            with freeze_time("2017-12-01 11:00:02"):
                response = self.client.post(
                    reverse('core:receive'),
                    data=self._create_requestor_auth_message(),
                    content_type='application/octet-stream',
                )

        request_upload_status_false_mock_function.assert_called_with(
            deserialized_force_get_task_result.report_computed_task
        )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(len(response.content),       0)

        self._assert_stored_message_counter_not_increased()

        self._test_undelivered_pending_responses(
            subtask_id                         = '8',
            client_public_key                  = self._get_encoded_provider_public_key(),
            expected_pending_responses_receive = [
                PendingResponse.ResponseType.ForceGetTaskResultUpload,
            ]
        )

        # STEP 3: Provider receives force get task result and file transfer token inside ForceGetTaskResultUpload via
        # Concent with correct key.
        with freeze_time("2017-12-01 11:00:02"):
            response = self.client.post(
                reverse('core:receive'),
                data=self._create_provider_auth_message(),
                content_type='application/octet-stream',
            )

        self.assertEqual(response.status_code, 200)

        message_from_concent = load(
            response.content,
            self.PROVIDER_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY,
            check_time = False
        )

        self.assertIsInstance(message_from_concent,   message.concents.ForceGetTaskResultUpload)

        # Assign each message to correct variable
        message_force_get_task_result = message_from_concent.force_get_task_result
        message_file_transfer_token   = message_from_concent.file_transfer_token

        # Test ForceGetTaskResult message

        self.assertIsInstance(message_force_get_task_result,                                 message.concents.ForceGetTaskResult)
        self.assertEqual(message_force_get_task_result.timestamp, parse_iso_date_to_timestamp("2017-12-01 11:00:01"))
        self.assertEqual(message_force_get_task_result.report_computed_task.task_to_compute, deserialized_force_get_task_result.report_computed_task.task_to_compute)
        self.assertEqual(message_force_get_task_result.report_computed_task.task_to_compute.compute_task_def, deserialized_force_get_task_result.report_computed_task.task_to_compute.compute_task_def)
        self.assertEqual(
            message_force_get_task_result.report_computed_task.task_to_compute.compute_task_def['deadline'],
            parse_iso_date_to_timestamp("2017-12-01 11:00:00")
        )
        self.assertEqual(
            message_force_get_task_result.report_computed_task.task_to_compute.compute_task_def['task_id'],
            '99'
        )

        # Test FileTransferToken message
        self.assertIsInstance(message_file_transfer_token, message.FileTransferToken)
        self.assertEqual(message_file_transfer_token.subtask_id,                deserialized_task_to_compute.compute_task_def['subtask_id'])  # pylint: disable=no-member
        self.assertEqual(message_file_transfer_token.timestamp, parse_iso_date_to_timestamp("2017-12-01 11:00:02"))
        self.assertEqual(message_file_transfer_token.token_expiration_deadline, parse_iso_date_to_timestamp("2017-12-01 11:00:52"))
        self.assertEqual(message_file_transfer_token.operation, FileTransferToken.Operation.upload)

        self._assert_stored_message_counter_not_increased()

        # STEP 4: Requestor do not receives force get task result failed due to lack of provider submit
        # with different or mixed key.
        with freeze_time("2017-12-01 11:00:02"):
            response = self.client.post(
                reverse('core:receive'),
                data=self._create_diff_requestor_auth_message(),
                content_type='application/octet-stream',
            )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(len(response.content),       0)

        self._assert_stored_message_counter_not_increased()

        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:receive'),
                data=self._create_provider_auth_message(),
                content_type='application/octet-stream',
            )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(len(response.content),       0)

        self._assert_stored_message_counter_not_increased()

        # STEP 5: Requestor receives force get task result failed due to lack of provider submit with correct key.
        with mock.patch(
            'core.transfer_operations.request_upload_status',
            side_effect=request_upload_status_false_mock
        ) as request_upload_status_false_mock_function:
            with freeze_time("2017-12-01 11:00:54"):
                response = self.client.post(
                    reverse('core:receive'),
                    data=self._create_requestor_auth_message(),
                    content_type='application/octet-stream',
                )

        request_upload_status_false_mock_function.assert_called_with(
            deserialized_force_get_task_result.report_computed_task
        )

        self.assertEqual(response.status_code,        200)

        message_from_concent = load(
            response.content,
            self.REQUESTOR_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY,
            check_time = False
        )

        self.assertIsInstance(message_from_concent, message.concents.ForceGetTaskResultFailed)
        self.assertEqual(message_from_concent.timestamp, parse_iso_date_to_timestamp("2017-12-01 11:00:54"))
        self.assertEqual(message_from_concent.task_to_compute,  deserialized_task_to_compute)
        self.assertEqual(
            message_from_concent.task_to_compute.compute_task_def,
            deserialized_task_to_compute.compute_task_def  # pylint: disable=no-member
        )
        self.assertEqual(
            message_from_concent.task_to_compute.compute_task_def['deadline'],
            parse_iso_date_to_timestamp("2017-12-01 11:00:00")
        )
        self.assertEqual(message_from_concent.task_to_compute.compute_task_def['task_id'], '99')

        self._assert_stored_message_counter_not_increased()
        self._test_subtask_state(
            task_id                  = '99',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.FAILED,  # Should be FAILED?
            provider_key             = self._get_encoded_provider_public_key(),
            requestor_key            = self._get_encoded_requestor_public_key(),
            expected_nested_messages = {'task_to_compute', 'report_computed_task'},
        )

        self._assert_client_count_is_equal(2)

    def test_concent_requests_task_result_from_provider_and_requestor_receives_failure_because_provider_does_not_finish_upload_should_work_only_with_correct_keys(self):
        """
        Tests if on requestor ForceGetTaskResult message Concent will return ForceGetTaskResultFailed
        if provider doesn't finish upload result.

        Expected message exchange:
        Requestor -> Concent:                   ForceGetTaskResult
        Concent   -> Requestor:                 AckForceGetTaskResult
        Concent   -> WrongProvider/Requestor:   HTTP 204
        Concent   -> Provider:                  ForceGetTaskResultUpload
        Provider  -> Concent:                   Starts Upload
        Concent   -> WrongRequestor/Provider:   HTTP 204
        Concent   -> Requestor:                 ForceGetTaskResultFailed
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
            timestamp       = "2017-12-01 11:00:00",
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
            response = self.client.post(
                reverse('core:send'),
                data=serialized_force_get_task_result,
                content_type='application/octet-stream',
            )

        self.assertEqual(response.status_code,      200)

        self._assert_stored_message_counter_increased(increased_by = 3)
        self._test_subtask_state(
            task_id='99',
            subtask_id='8',
            subtask_state=Subtask.SubtaskState.FORCING_RESULT_TRANSFER,
            provider_key=self._get_encoded_provider_public_key(),
            requestor_key=self._get_encoded_requestor_public_key(),
            expected_nested_messages={'task_to_compute', 'report_computed_task', 'force_get_task_result'},
            next_deadline=parse_iso_date_to_timestamp("2017-12-01 11:00:52"),
        )
        self._test_last_stored_messages(
            expected_messages = [
                message.tasks.TaskToCompute,
                message.tasks.ReportComputedTask,
                message.concents.ForceGetTaskResult,
            ],
            task_id         = '99',
            subtask_id      = '8',
        )
        self._test_undelivered_pending_responses(
            subtask_id                         = '8',
            client_public_key                  = self._get_encoded_provider_public_key(),
            expected_pending_responses_receive = [
                PendingResponse.ResponseType.ForceGetTaskResultUpload,
            ]
        )

        # STEP 2: Provider do not receive force get task result and file transfer token inside
        # ForceGetTaskResultUpload via Concent with different or mixed key.
        with freeze_time("2017-12-01 11:00:02"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = self._create_diff_provider_auth_message(),
                content_type                   = 'application/octet-stream',
            )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(len(response.content),       0)

        self._assert_stored_message_counter_not_increased()

        with mock.patch(
            'core.transfer_operations.request_upload_status',
            side_effect=request_upload_status_false_mock
        ) as request_upload_status_false_mock_function:
            with freeze_time("2017-12-01 11:00:02"):
                response = self.client.post(
                    reverse('core:receive'),
                    data=self._create_requestor_auth_message(),
                    content_type='application/octet-stream',
                )

        request_upload_status_false_mock_function.assert_called_with(
            deserialized_force_get_task_result.report_computed_task
        )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(len(response.content),       0)

        self._assert_stored_message_counter_not_increased()

        self._test_undelivered_pending_responses(
            subtask_id                         = '8',
            client_public_key                  = self._get_encoded_provider_public_key(),
            expected_pending_responses_receive = [
                PendingResponse.ResponseType.ForceGetTaskResultUpload,
            ]
        )

        # STEP 3: Provider receives force get task result and file transfer token inside ForceGetTaskResultUpload via
        # Concent with correct key.
        with freeze_time("2017-12-01 11:00:03"):
            response = self.client.post(
                reverse('core:receive'),
                data=self._create_provider_auth_message(),
                content_type='application/octet-stream',
            )

        self.assertEqual(response.status_code,      200)

        message_from_concent = load(
            response.content,
            self.PROVIDER_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY,
            check_time = False
        )
        self.assertIsInstance(message_from_concent, message.concents.ForceGetTaskResultUpload)

        # Assign each message to correct variable
        message_force_get_task_result = message_from_concent.force_get_task_result
        message_file_transfer_token   = message_from_concent.file_transfer_token

        # Test ForceGetTaskResult message

        self.assertIsInstance(message_force_get_task_result, message.concents.ForceGetTaskResult)
        self.assertEqual(
            message_force_get_task_result.timestamp,
            parse_iso_date_to_timestamp("2017-12-01 11:00:01")
        )
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
            parse_iso_date_to_timestamp("2017-12-01 11:00:00")
        )
        self.assertEqual(message_force_get_task_result.report_computed_task.task_to_compute.compute_task_def['task_id'], '99')

        # Test FileTransferToken message
        self.assertIsInstance(message_file_transfer_token, message.FileTransferToken)
        self.assertEqual(message_file_transfer_token.subtask_id,                deserialized_task_to_compute.compute_task_def['subtask_id'])  # pylint: disable=no-member
        self.assertEqual(message_file_transfer_token.timestamp, parse_iso_date_to_timestamp("2017-12-01 11:00:03"))
        self.assertEqual(message_file_transfer_token.token_expiration_deadline, parse_iso_date_to_timestamp("2017-12-01 11:00:52"))
        self.assertEqual(message_file_transfer_token.operation, FileTransferToken.Operation.upload)

        self._assert_stored_message_counter_not_increased()

        # STEP 4: Requestor do not receives force get task result failed due to lack of provider submit
        # with different or mixed key.
        with freeze_time("2017-12-01 11:00:04"):
            response = self.client.post(
                reverse('core:receive'),
                data=self._create_diff_requestor_auth_message(),
                content_type='application/octet-stream',
            )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(len(response.content),       0)

        self._assert_stored_message_counter_not_increased()

        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:receive'),
                data=self._create_provider_auth_message(),
                content_type='application/octet-stream',
            )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(len(response.content),       0)

        self._assert_stored_message_counter_not_increased()

        # STEP 5: Requestor receives force get task result failed due to lack of provider submit with correct key.
        with mock.patch(
            'core.transfer_operations.request_upload_status',
            side_effect=request_upload_status_false_mock
        ) as request_upload_status_false_mock_function:
            with freeze_time("2017-12-01 11:00:54"):
                response = self.client.post(
                    reverse('core:receive'),
                    data=self._create_requestor_auth_message(),
                    content_type='application/octet-stream',
                )

        request_upload_status_false_mock_function.assert_called_with(
            deserialized_force_get_task_result.report_computed_task
        )

        self.assertEqual(response.status_code,      200)

        message_from_concent = load(
            response.content,
            self.REQUESTOR_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY,
            check_time = False
        )

        self.assertIsInstance(message_from_concent, message.concents.ForceGetTaskResultFailed)
        self.assertEqual(message_from_concent.timestamp, parse_iso_date_to_timestamp("2017-12-01 11:00:54"))
        self.assertEqual(message_from_concent.task_to_compute, deserialized_task_to_compute)
        self.assertEqual(
            message_from_concent.task_to_compute.compute_task_def,
            deserialized_task_to_compute.compute_task_def
        )  # pylint: disable=no-member
        self.assertEqual(
            message_from_concent.task_to_compute.compute_task_def['deadline'],
            parse_iso_date_to_timestamp("2017-12-01 11:00:00")
        )
        self.assertEqual(message_from_concent.task_to_compute.compute_task_def['task_id'], '99')

        self._assert_stored_message_counter_not_increased()
        self._test_subtask_state(
            task_id                  = '99',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.FAILED,  # Should be FAILED?
            provider_key             = self._get_encoded_provider_public_key(),
            requestor_key            = self._get_encoded_requestor_public_key(),
            expected_nested_messages = {'task_to_compute', 'report_computed_task'},
        )

        self._assert_client_count_is_equal(2)

    def test_concent_requests_task_result_from_provider_and_requestor_receives_failure_because_provider_uploads_bad_files_should_work_only_with_correct_keys(self):
        """
        Tests if on requestor ForceGetTaskResult message Concent will return ForceGetTaskResultFailed
        if provider uploads bad or incomplete result.

        Expected message exchange:
        Requestor -> Concent:                   ForceGetTaskResult
        Concent   -> Requestor:                 AckForceGetTaskResult
        Concent   -> WrongProvider/Requestor:   ForceGetTaskResultUpload
        Concent   -> Provider:                  ForceGetTaskResultUpload
        Provider  -> Concent:                   Upload bad files
        Concent   -> WrongRequestor/Provider:   ForceGetTaskResultFailed
        Concent   -> Requestor:                 ForceGetTaskResultFailed
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
            timestamp       = "2017-12-01 11:00:00",
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
            response = self.client.post(
                reverse('core:send'),
                data=serialized_force_get_task_result,
                content_type='application/octet-stream',
            )

        self.assertEqual(response.status_code,      200)

        self._assert_stored_message_counter_increased(increased_by = 3)
        self._test_subtask_state(
            task_id='99',
            subtask_id='8',
            subtask_state=Subtask.SubtaskState.FORCING_RESULT_TRANSFER,
            provider_key=self._get_encoded_provider_public_key(),
            requestor_key=self._get_encoded_requestor_public_key(),
            expected_nested_messages={'task_to_compute', 'report_computed_task', 'force_get_task_result'},
            next_deadline=parse_iso_date_to_timestamp("2017-12-01 11:00:52"),
        )
        self._test_last_stored_messages(
            expected_messages = [
                message.tasks.TaskToCompute,
                message.tasks.ReportComputedTask,
                message.concents.ForceGetTaskResult,
            ],
            task_id         = '99',
            subtask_id      = '8',
        )
        self._test_undelivered_pending_responses(
            subtask_id                         = '8',
            client_public_key                  = self._get_encoded_provider_public_key(),
            expected_pending_responses_receive = [
                PendingResponse.ResponseType.ForceGetTaskResultUpload,
            ]
        )

        # STEP 2: Provider do not receive force get task result and file transfer token inside
        # ForceGetTaskResultUpload via Concent with with different or mixed key.
        with freeze_time("2017-12-01 11:00:02"):
            response = self.client.post(
                reverse('core:receive'),
                data=self._create_diff_provider_auth_message(),
                content_type='application/octet-stream',
            )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(len(response.content),       0)

        self._assert_stored_message_counter_not_increased()

        with mock.patch(
            'core.transfer_operations.request_upload_status',
            side_effect=request_upload_status_false_mock
        ) as request_upload_status_false_mock_function:
            with freeze_time("2017-12-01 11:00:02"):
                response = self.client.post(
                    reverse('core:receive'),
                    data=self._create_requestor_auth_message(),
                    content_type='application/octet-stream',
                )

        request_upload_status_false_mock_function.assert_called_with(
            deserialized_force_get_task_result.report_computed_task
        )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(len(response.content),       0)

        self._assert_stored_message_counter_not_increased()

        self._test_undelivered_pending_responses(
            subtask_id                         = '8',
            client_public_key                  = self._get_encoded_provider_public_key(),
            expected_pending_responses_receive = [
                PendingResponse.ResponseType.ForceGetTaskResultUpload,
            ]
        )

        # STEP 3: Provider receives force get task result and file transfer token inside ForceGetTaskResultUpload via
        # Concent with correct key.
        with freeze_time("2017-12-01 11:00:02"):
            response = self.client.post(
                reverse('core:receive'),
                data=self._create_provider_auth_message(),
                content_type='application/octet-stream',
            )

        self.assertEqual(response.status_code,      200)

        message_from_concent = load(
            response.content,
            self.PROVIDER_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY,
            check_time = False
        )
        self.assertIsInstance(message_from_concent, message.concents.ForceGetTaskResultUpload)

        # Assign each message to correct variable
        message_force_get_task_result = message_from_concent.force_get_task_result
        message_file_transfer_token   = message_from_concent.file_transfer_token

        # Test ForceGetTaskResult message

        self.assertIsInstance(message_force_get_task_result,      message.concents.ForceGetTaskResult)
        self.assertEqual(message_force_get_task_result.timestamp, parse_iso_date_to_timestamp("2017-12-01 11:00:01"))
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
            parse_iso_date_to_timestamp("2017-12-01 11:00:00")
        )
        self.assertEqual(message_force_get_task_result.report_computed_task.task_to_compute.compute_task_def['task_id'], '99')

        # Test FileTransferToken message
        self.assertIsInstance(message_file_transfer_token, message.FileTransferToken)
        self.assertEqual(message_file_transfer_token.subtask_id,                deserialized_task_to_compute.compute_task_def['subtask_id'])  # pylint: disable=no-member
        self.assertEqual(message_file_transfer_token.timestamp, parse_iso_date_to_timestamp("2017-12-01 11:00:02"))
        self.assertEqual(message_file_transfer_token.token_expiration_deadline, parse_iso_date_to_timestamp("2017-12-01 11:00:52"))
        self.assertEqual(message_file_transfer_token.operation, FileTransferToken.Operation.upload)

        self._assert_stored_message_counter_not_increased()

        # STEP 4: Requestor do not receives force get task result failed due to lack of provider submit
        # with different or mixed key.
        with freeze_time("2017-12-01 11:00:54"):
            response = self.client.post(
                reverse('core:receive'),
                data=self._create_diff_requestor_auth_message(),
                content_type='application/octet-stream',
            )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(len(response.content),       0)

        self._assert_stored_message_counter_not_increased()

        with freeze_time("2017-12-01 11:00:54"):
            response = self.client.post(
                reverse('core:receive'),
                data=self._create_provider_auth_message(),
                content_type='application/octet-stream',
            )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(len(response.content),       0)

        self._assert_stored_message_counter_not_increased()

        # STEP 5: Requestor receives force get task result failed due to lack of provider submit with correct key.
        with freeze_time("2017-12-01 11:00:54"):
            response = self.client.post(
                reverse('core:receive'),
                data=self._create_requestor_auth_message(),
                content_type='application/octet-stream',
            )

        self.assertEqual(response.status_code,      200)

        message_from_concent = load(
            response.content,
            self.REQUESTOR_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY,
            check_time = False
        )

        self.assertIsInstance(message_from_concent, message.concents.ForceGetTaskResultFailed)
        self.assertEqual(message_from_concent.timestamp, parse_iso_date_to_timestamp("2017-12-01 11:00:54"))
        self.assertEqual(message_from_concent.task_to_compute, deserialized_task_to_compute)
        self.assertEqual(
            message_from_concent.task_to_compute.compute_task_def,
            deserialized_task_to_compute.compute_task_def  # pylint: disable=no-member
        )
        self.assertEqual(
            message_from_concent.task_to_compute.compute_task_def['deadline'],
            parse_iso_date_to_timestamp("2017-12-01 11:00:00")
        )
        self.assertEqual(message_from_concent.task_to_compute.compute_task_def['task_id'], '99')

        self._assert_stored_message_counter_not_increased()
        self._test_subtask_state(
            task_id='99',
            subtask_id='8',
            subtask_state=Subtask.SubtaskState.FAILED,
            provider_key=self._get_encoded_provider_public_key(),
            requestor_key=self._get_encoded_requestor_public_key(),
            expected_nested_messages={'task_to_compute', 'report_computed_task'},
        )

        self._assert_client_count_is_equal(2)

    def test_concent_requests_task_result_from_provider_and_requestor_receives_task_result_should_work_only_with_correct_keys(self):
        """
        Tests if on requestor ForceGetTaskResult message Concent will return ForceGetTaskResultUpload
        if provider uploads correct result.

        Expected message exchange:
        Requestor -> Concent:                   ForceGetTaskResult
        Concent   -> Requestor:                 AckForceGetTaskResult
        Concent   -> WrongProvider/Requestor:   HTTP 204
        Concent   -> Provider:                  ForceGetTaskResultUpload
        Provider  -> Concent:                   Upload good files
        Concent   -> WrongRequestor/Provider:   HTTP 204
        Concent   -> Requestor:                 ForceGetTaskResultDownload
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
            timestamp       = "2017-12-01 11:00:00",
            task_to_compute = deserialized_task_to_compute
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
            response = self.client.post(
                reverse('core:send'),
                data=serialized_force_get_task_result,
                content_type='application/octet-stream',
            )

        self.assertEqual(response.status_code,      200)

        self._assert_stored_message_counter_increased(increased_by = 3)
        self._test_subtask_state(
            task_id                  = '99',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.FORCING_RESULT_TRANSFER,
            provider_key             = self._get_encoded_provider_public_key(),
            requestor_key            = self._get_encoded_requestor_public_key(),
            expected_nested_messages = {'task_to_compute', 'report_computed_task', 'force_get_task_result'},
            next_deadline            = parse_iso_date_to_timestamp("2017-12-01 11:00:52"),
        )
        self._test_last_stored_messages(
            expected_messages = [
                message.tasks.TaskToCompute,
                message.tasks.ReportComputedTask,
                message.concents.ForceGetTaskResult,
            ],
            task_id         = '99',
            subtask_id      = '8',
        )
        self._test_undelivered_pending_responses(
            subtask_id                         = '8',
            client_public_key                  = self._get_encoded_provider_public_key(),
            expected_pending_responses_receive = [
                PendingResponse.ResponseType.ForceGetTaskResultUpload,
            ]
        )

        # STEP 2: Provider do not receive force get task result and file transfer token inside
        # ForceGetTaskResultUpload via Concent with with different or mixed key.
        with freeze_time("2017-12-01 11:00:02"):
            response = self.client.post(
                reverse('core:receive'),
                data=self._create_diff_provider_auth_message(),
                content_type='application/octet-stream',
            )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(len(response.content),       0)

        self._assert_stored_message_counter_not_increased()

        with mock.patch(
            'core.transfer_operations.request_upload_status',
            side_effect=request_upload_status_false_mock
        ) as request_upload_status_false_mock_function:
            with freeze_time("2017-12-01 11:00:02"):
                response = self.client.post(
                    reverse('core:receive'),
                    data=self._create_requestor_auth_message(),
                    content_type='application/octet-stream',
                )

        request_upload_status_false_mock_function.assert_called_with(
            deserialized_force_get_task_result.report_computed_task
        )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(len(response.content),       0)

        self._assert_stored_message_counter_not_increased()

        self._test_undelivered_pending_responses(
            subtask_id                         = '8',
            client_public_key                  = self._get_encoded_provider_public_key(),
            expected_pending_responses_receive = [
                PendingResponse.ResponseType.ForceGetTaskResultUpload,
            ]
        )

        # STEP 3: Provider receives force get task result and file transfer token inside ForceGetTaskResultUpload via
        # Concent with correct key.
        with freeze_time("2017-12-01 11:00:02"):
            response = self.client.post(
                reverse('core:receive'),
                data=self._create_provider_auth_message(),
                content_type='application/octet-stream',
            )

        self.assertEqual(response.status_code, 200)

        message_from_concent = load(response.content, self.PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY, check_time = False)
        self.assertIsInstance(message_from_concent, message.concents.ForceGetTaskResultUpload)

        # Assign each message to correct variable
        message_force_get_task_result = message_from_concent.force_get_task_result
        message_file_transfer_token   = message_from_concent.file_transfer_token

        # Test ForceGetTaskResult message
        self.assertIsInstance(message_force_get_task_result,                                 message.concents.ForceGetTaskResult)
        self.assertEqual(message_force_get_task_result.timestamp, parse_iso_date_to_timestamp("2017-12-01 11:00:01"))
        self.assertEqual(message_force_get_task_result.report_computed_task.task_to_compute, deserialized_task_to_compute)
        self.assertEqual(
            message_force_get_task_result.report_computed_task.task_to_compute.compute_task_def,
            deserialized_task_to_compute.compute_task_def  # pylint: disable=no-member
        )
        self.assertEqual(
            message_force_get_task_result.report_computed_task.task_to_compute.compute_task_def['deadline'],
            parse_iso_date_to_timestamp("2017-12-01 11:00:00")
        )
        self.assertEqual(
            message_force_get_task_result.report_computed_task.task_to_compute.compute_task_def['task_id'],
            '99'
        )

        # Test FileTransferToken message
        self.assertIsInstance(message_file_transfer_token, message.FileTransferToken)
        self.assertEqual(message_file_transfer_token.subtask_id,                deserialized_task_to_compute.compute_task_def['subtask_id'])  # pylint: disable=no-member
        self.assertEqual(message_file_transfer_token.timestamp, parse_iso_date_to_timestamp("2017-12-01 11:00:02"))
        self.assertEqual(message_file_transfer_token.token_expiration_deadline, parse_iso_date_to_timestamp("2017-12-01 11:00:52"))
        self.assertEqual(message_file_transfer_token.operation, FileTransferToken.Operation.upload)

        self._assert_stored_message_counter_not_increased()

        # STEP 4: Requestor do not receives force get task result failed due to lack of provider submit
        # with different or mixed key.
        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:receive'),
                data=self._create_diff_requestor_auth_message(),
                content_type='application/octet-stream',
            )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(len(response.content),       0)

        self._assert_stored_message_counter_not_increased()

        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:receive'),
                data=self._create_provider_auth_message(),
                content_type='application/octet-stream',
            )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(len(response.content),       0)

        self._assert_stored_message_counter_not_increased()

        # STEP 5: Requestor receives force get task result failed due to lack of provider submit with correct key.
        with mock.patch(
            'core.transfer_operations.request_upload_status',
            side_effect=request_upload_status_true_mock
        ) as request_upload_status_true_mock_function:
            with freeze_time("2017-12-01 11:00:08"):
                response = self.client.post(
                    reverse('core:receive'),
                    data=self._create_requestor_auth_message(),
                    content_type='application/octet-stream',
                )

        request_upload_status_true_mock_function.assert_called_with(
            deserialized_force_get_task_result.report_computed_task
        )

        self.assertEqual(response.status_code,      200)

        message_from_concent = load(
            response.content,
            self.REQUESTOR_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY,
            check_time = False
        )

        self.assertIsInstance(message_from_concent,      message.concents.ForceGetTaskResultDownload)
        self.assertEqual(message_from_concent.timestamp, parse_iso_date_to_timestamp("2017-12-01 11:00:08"))

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
            parse_iso_date_to_timestamp("2017-12-01 11:00:00")
        )
        self.assertEqual(message_from_concent.force_get_task_result.report_computed_task.task_to_compute.compute_task_def['task_id'], '99')
        self.assertEqual(message_from_concent.file_transfer_token.subtask_id, deserialized_task_to_compute.compute_task_def['subtask_id'])  # pylint: disable=no-member
        self.assertIsInstance(message_from_concent.file_transfer_token, message.FileTransferToken)
        self.assertEqual(
            message_from_concent.file_transfer_token.timestamp,
            parse_iso_date_to_timestamp("2017-12-01 11:00:08")
        )
        self.assertEqual(
            message_from_concent.file_transfer_token.token_expiration_deadline,
            parse_iso_date_to_timestamp("2017-12-01 11:30:00")
        )
        self.assertEqual(message_from_concent.file_transfer_token.operation, FileTransferToken.Operation.download)

        self._assert_stored_message_counter_not_increased()
        self._test_subtask_state(
            task_id                  = '99',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.RESULT_UPLOADED,
            provider_key             = self._get_encoded_provider_public_key(),
            requestor_key            = self._get_encoded_requestor_public_key(),
            expected_nested_messages = {'task_to_compute', 'report_computed_task'},
        )

        self._assert_client_count_is_equal(2)
