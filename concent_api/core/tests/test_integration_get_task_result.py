from django.test            import override_settings
from django.urls            import reverse
from freezegun              import freeze_time
from golem_messages         import load
from golem_messages         import message

from core.tests.utils       import ConcentIntegrationTestCase
from utils.testing_helpers  import generate_ecc_key_pair


(CONCENT_PRIVATE_KEY, CONCENT_PUBLIC_KEY) = generate_ecc_key_pair()


@override_settings(
    CONCENT_PRIVATE_KEY    = CONCENT_PRIVATE_KEY,
    CONCENT_PUBLIC_KEY     = CONCENT_PUBLIC_KEY,
    CONCENT_MESSAGING_TIME = 10,  # seconds
    FORCE_ACCEPTANCE_TIME  = 10,  # seconds
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
            task_to_compute = deserialized_task_to_compute
        )
        serialized_force_get_task_result = self._get_serialized_force_get_task_result(
            report_computed_task = deserialized_report_computed_task,
            timestamp       = "2017-12-01 11:00:11",
        )

        with freeze_time("2017-12-01 11:00:11"):
            response = self.client.post(
                reverse('core:send'),
                data                           = serialized_force_get_task_result,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_requestor_public_key()
            )

        self.assertEqual(response.status_code, 200)

        message_from_concent = load(response.content, self.REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY, check_time = False)

        self.assertIsInstance(message_from_concent, message.concents.ForceGetTaskResultRejected)
        self.assertEqual(message_from_concent.timestamp, self._parse_iso_date_to_timestamp("2017-12-01 11:00:11"))
        self.assertEqual(message_from_concent.reason, message_from_concent.REASON.AcceptanceTimeLimitExceeded)

    def test_requestor_forces_get_task_result_and_concent_immediately_sends_rejection_due_to_already_sent_message(self):
        """
        Tests if on requestor ForceGetTaskResult message Concent will return ForceGetTaskResultRejected
        if ForceGetTaskResult was already sent by this requestor.

        Expected message exchange:
        Requestor -> Concent:    ForceGetTaskResult
        Requestor -> Concent:    ForceGetTaskResult
        Concent   -> Requestor:  ForceGetTaskResultRejected
        """

        # STEP 1: Requestor forces get task result via Concent.
        deserialized_task_to_compute = self._get_deserialized_task_to_compute(
            timestamp   = "2017-12-01 10:00:00",
            deadline    = "2017-12-01 11:00:00",
        )
        deserialized_report_computed_task = self._get_deserialized_report_computed_task(
            task_to_compute = deserialized_task_to_compute
        )
        serialized_force_get_task_result = self._get_serialized_force_get_task_result(
            report_computed_task = deserialized_report_computed_task,
            timestamp       = "2017-12-01 11:00:08",
        )

        with freeze_time("2017-12-01 11:00:08"):
            response = self.client.post(
                reverse('core:send'),
                data                           = serialized_force_get_task_result,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_requestor_public_key()
            )

        assert response.status_code == 200

        # STEP 2: Requestor again forces get task result via Concent.
        # Concent rejects request immediately because message was already sent.
        with freeze_time("2017-12-01 11:00:09"):
            response = self.client.post(
                reverse('core:send'),
                data                           = serialized_force_get_task_result,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_requestor_public_key()
            )

        self.assertEqual(response.status_code,  200)

        message_from_concent = load(response.content, self.REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY, check_time = False)

        self.assertIsInstance(message_from_concent, message.concents.ForceGetTaskResultRejected)
        self.assertEqual(message_from_concent.timestamp, self._parse_iso_date_to_timestamp("2017-12-01 11:00:08"))
        self.assertEqual(message_from_concent.reason, message_from_concent.REASON.OperationAlreadyInitiated)

    def test_requestor_forces_get_task_result_and_concent_immediately_sends_acknowledgement(self):
        """
        Tests if on requestor ForceGetTaskResult message Concent will return ForceGetTaskResultAck
        if all conditions were met.

        Expected message exchange:
        Requestor -> Concent:    ForceGetTaskResult
        Concent   -> Requestor:  ForceGetTaskResultAck
        """

        # STEP 1: Requestor forces get task result via Concent.
        # Concent accepts request if all conditions were met.
        deserialized_task_to_compute = self._get_deserialized_task_to_compute(
            timestamp   = "2017-12-01 10:00:00",
            deadline    = "2017-12-01 11:00:00",
        )
        deserialized_report_computed_task = self._get_deserialized_report_computed_task(
            task_to_compute = deserialized_task_to_compute
        )
        serialized_force_get_task_result = self._get_serialized_force_get_task_result(
            report_computed_task = deserialized_report_computed_task,
            timestamp       = "2017-12-01 11:00:09",
        )

        with freeze_time("2017-12-01 11:00:09"):
            response = self.client.post(
                reverse('core:send'),
                data                           = serialized_force_get_task_result,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_requestor_public_key()
            )

        self.assertEqual(response.status_code,  200)

        message_from_concent = load(response.content, self.REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY, check_time = False)

        self.assertIsInstance(message_from_concent, message.concents.ForceGetTaskResultAck)
        self.assertEqual(message_from_concent.timestamp, self._parse_iso_date_to_timestamp("2017-12-01 11:00:09"))

    def test_concent_requests_task_result_from_provider_and_requestor_receives_failure_because_provider_does_not_submit(self):
        """
        Tests if on requestor ForceGetTaskResult message Concent will return ForceGetTaskResultFailed
        if provider doesn't submit result.

        Expected message exchange:
        Requestor -> Concent:     ForceGetTaskResult
        Concent   -> Requestor:   ForceGetTaskResultAck
        Concent   -> Provider:    ForceGetTaskResultUpload
        Provider  -> Concent:     no response
        Concent   -> Requestor:   ForceGetTaskResultFailed
        """

        # STEP 1: Requestor forces get task result via Concent.
        # Concent accepts request if all conditions were met.
        deserialized_task_to_compute = self._get_deserialized_task_to_compute(
            timestamp   = "2017-12-01 10:00:00",
            task_id     = '99',
            deadline    = "2017-12-01 11:00:00"
        )
        deserialized_report_computed_task = self._get_deserialized_report_computed_task(
            task_to_compute = deserialized_task_to_compute
        )
        serialized_force_get_task_result = self._get_serialized_force_get_task_result(
            report_computed_task = deserialized_report_computed_task,
            timestamp       = "2017-12-01 11:00:01",
        )
        deserialized_force_get_task_result = load(
            serialized_force_get_task_result,
            CONCENT_PRIVATE_KEY,
            self.REQUESTOR_PUBLIC_KEY,
            check_time=False,
        )

        with freeze_time("2017-12-01 11:00:01"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                           = serialized_force_get_task_result,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_requestor_public_key()
            )

        self.assertEqual(response_1.status_code, 200)

        # STEP 2: Provider receives force get task result and file transfer token inside ForceGetTaskResultUpload via Concent.
        with freeze_time("2017-12-01 11:00:12"):
            response_2 = self.client.post(
                reverse('core:receive'),
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_provider_public_key()
            )

        self.assertEqual(response_2.status_code, 200)

        message_from_concent = load(response_2.content, self.PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY, check_time = False)
        self.assertIsInstance(message_from_concent, message.concents.ForceGetTaskResultUpload)

        # Assign each message to correct variable
        message_force_get_task_result = message_from_concent.force_get_task_result
        message_file_transfer_token = message_from_concent.file_transfer_token

        # Test ForceGetTaskResult message

        self.assertIsInstance(message_force_get_task_result, message.concents.ForceGetTaskResult)
        self.assertEqual(message_force_get_task_result.timestamp, self._parse_iso_date_to_timestamp("2017-12-01 11:00:01"))
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
        self.assertEqual(message_file_transfer_token.timestamp, self._parse_iso_date_to_timestamp("2017-12-01 11:00:12"))
        self.assertEqual(message_file_transfer_token.token_expiration_deadline, self._parse_iso_date_to_timestamp("2017-12-01 11:30:12"))
        self.assertEqual(message_file_transfer_token.operation, 'upload')

        # STEP 3: Requestor receives force get task result failed due to lack of provider submit.
        with freeze_time("2017-12-01 11:00:21"):
            response_3 = self.client.post(
                reverse('core:receive'),
                data                           = '',
                content_type                   = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
            )

        self.assertEqual(response_3.status_code,  200)

        message_from_concent = load(response_3.content, self.REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY, check_time = False)

        self.assertIsInstance(message_from_concent, message.concents.ForceGetTaskResultFailed)
        self.assertEqual(message_from_concent.timestamp, self._parse_iso_date_to_timestamp("2017-12-01 11:00:21"))
        self.assertEqual(message_from_concent.task_to_compute, deserialized_task_to_compute)
        self.assertEqual(message_from_concent.task_to_compute.compute_task_def, deserialized_task_to_compute.compute_task_def)   # pylint: disable=no-member
        self.assertEqual(
            message_from_concent.task_to_compute.compute_task_def['deadline'],
            self._parse_iso_date_to_timestamp("2017-12-01 11:00:00")
        )
        self.assertEqual(message_from_concent.task_to_compute.compute_task_def['task_id'], '99')

    def test_concent_requests_task_result_from_provider_and_requestor_receives_failure_because_provider_does_not_finish_upload(self):
        """
        Tests if on requestor ForceGetTaskResult message Concent will return ForceGetTaskResultFailed
        if provider doesn't finish upload result.

        Expected message exchange:
        Requestor -> Concent:     ForceGetTaskResult
        Concent   -> Requestor:   ForceGetTaskResultAck
        Concent   -> Provider:    ForceGetTaskResultUpload
        Provider  -> Concent:     Starts Upload
        Concent   -> Requestor:   ForceGetTaskResultFailed
        """

        # STEP 1: Requestor forces get task result via Concent.
        # Concent accepts request if all conditions were met.
        deserialized_task_to_compute = self._get_deserialized_task_to_compute(
            timestamp   = "2017-12-01 10:00:00",
            task_id     = '99',
            deadline    = "2017-12-01 11:00:00"
        )
        deserialized_report_computed_task = self._get_deserialized_report_computed_task(
            task_to_compute = deserialized_task_to_compute
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
                data                           = serialized_force_get_task_result,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_requestor_public_key()
            )

        self.assertEqual(response_1.status_code, 200)

        # STEP 2: Provider receives force get task result and file transfer token inside ForceGetTaskResultUpload via Concent.
        with freeze_time("2017-12-01 11:00:12"):
            response_2 = self.client.post(
                reverse('core:receive'),
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_provider_public_key()
            )

        self.assertEqual(response_2.status_code, 200)

        message_from_concent = load(response_2.content, self.PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY, check_time = False)
        self.assertIsInstance(message_from_concent, message.concents.ForceGetTaskResultUpload)

        # Assign each message to correct variable
        message_force_get_task_result = message_from_concent.force_get_task_result
        message_file_transfer_token = message_from_concent.file_transfer_token

        # Test ForceGetTaskResult message

        self.assertIsInstance(message_force_get_task_result, message.concents.ForceGetTaskResult)
        self.assertEqual(message_force_get_task_result.timestamp, self._parse_iso_date_to_timestamp("2017-12-01 11:00:01"))
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
        self.assertIsInstance(message_file_transfer_token, message.FileTransferToken)
        self.assertEqual(message_file_transfer_token.timestamp, self._parse_iso_date_to_timestamp("2017-12-01 11:00:12"))
        self.assertEqual(message_file_transfer_token.token_expiration_deadline, self._parse_iso_date_to_timestamp("2017-12-01 11:30:12"))
        self.assertEqual(message_file_transfer_token.operation, 'upload')

        # STEP 3: Requestor receives force get task result failed due to lack of provider submit.
        with freeze_time("2017-12-01 11:00:21"):
            response_3 = self.client.post(
                reverse('core:receive'),
                data                           = '',
                content_type                   = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
            )

        self.assertEqual(response_3.status_code,  200)

        message_from_concent = load(response_3.content, self.REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY, check_time = False)

        self.assertIsInstance(message_from_concent, message.concents.ForceGetTaskResultFailed)
        self.assertEqual(message_from_concent.timestamp, self._parse_iso_date_to_timestamp("2017-12-01 11:00:21"))
        self.assertEqual(message_from_concent.task_to_compute, deserialized_task_to_compute)
        self.assertEqual(message_from_concent.task_to_compute.compute_task_def, deserialized_task_to_compute.compute_task_def)   # pylint: disable=no-member
        self.assertEqual(
            message_from_concent.task_to_compute.compute_task_def['deadline'],
            self._parse_iso_date_to_timestamp("2017-12-01 11:00:00")
        )
        self.assertEqual(message_from_concent.task_to_compute.compute_task_def['task_id'], '99')

    def test_concent_requests_task_result_from_provider_and_requestor_receives_failure_because_provider_uploads_bad_files(self):
        """
        Tests if on requestor ForceGetTaskResult message Concent will return ForceGetTaskResultFailed
        if provider uploads bad or incomplete result.

        Expected message exchange:
        Requestor -> Concent:     ForceGetTaskResult
        Concent   -> Requestor:   ForceGetTaskResultAck
        Concent   -> Provider:    ForceGetTaskResultUpload
        Provider  -> Concent:     TODO: Upload bad files
        Concent   -> Requestor:   ForceGetTaskResultFailed
        """

        # STEP 1: Requestor forces get task result via Concent.
        # Concent accepts request if all conditions were met.
        deserialized_task_to_compute = self._get_deserialized_task_to_compute(
            timestamp   = "2017-12-01 10:00:00",
            task_id     = '99',
            deadline    = "2017-12-01 11:00:00"
        )
        deserialized_report_computed_task = self._get_deserialized_report_computed_task(
            task_to_compute = deserialized_task_to_compute
        )
        serialized_force_get_task_result = self._get_serialized_force_get_task_result(
            report_computed_task = deserialized_report_computed_task,
            timestamp       = "2017-12-01 11:00:01",
        )
        deserialized_force_get_task_result = load(
            serialized_force_get_task_result,
            CONCENT_PRIVATE_KEY,
            self.REQUESTOR_PUBLIC_KEY,
            check_time=False,
        )

        with freeze_time("2017-12-01 11:00:01"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                           = serialized_force_get_task_result,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_requestor_public_key()
            )

        self.assertEqual(response_1.status_code, 200)

        # STEP 2: Provider receives force get task result and file transfer token inside ForceGetTaskResultUpload via Concent.
        with freeze_time("2017-12-01 11:00:12"):
            response_2 = self.client.post(
                reverse('core:receive'),
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_provider_public_key()
            )

        self.assertEqual(response_2.status_code, 200)

        message_from_concent = load(response_2.content, self.PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY, check_time = False)
        self.assertIsInstance(message_from_concent, message.concents.ForceGetTaskResultUpload)

        # Assign each message to correct variable
        message_force_get_task_result = message_from_concent.force_get_task_result
        message_file_transfer_token = message_from_concent.file_transfer_token

        # Test ForceGetTaskResult message

        self.assertIsInstance(message_force_get_task_result, message.concents.ForceGetTaskResult)
        self.assertEqual(message_force_get_task_result.timestamp, self._parse_iso_date_to_timestamp("2017-12-01 11:00:01"))
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
        self.assertEqual(message_file_transfer_token.timestamp, self._parse_iso_date_to_timestamp("2017-12-01 11:00:12"))
        self.assertEqual(message_file_transfer_token.token_expiration_deadline, self._parse_iso_date_to_timestamp("2017-12-01 11:30:12"))
        self.assertEqual(message_file_transfer_token.operation, 'upload')

        # STEP 3: Requestor receives force get task result failed due to lack of provider submit.
        with freeze_time("2017-12-01 11:00:21"):
            response_3 = self.client.post(
                reverse('core:receive'),
                data         = '',
                content_type = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
            )

        self.assertEqual(response_3.status_code,  200)

        message_from_concent = load(response_3.content, self.REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY, check_time = False)

        self.assertIsInstance(message_from_concent, message.concents.ForceGetTaskResultFailed)
        self.assertEqual(message_from_concent.timestamp, self._parse_iso_date_to_timestamp("2017-12-01 11:00:21"))
        self.assertEqual(message_from_concent.task_to_compute, deserialized_task_to_compute)
        self.assertEqual(message_from_concent.task_to_compute.compute_task_def, deserialized_task_to_compute.compute_task_def)   # pylint: disable=no-member
        self.assertEqual(
            message_from_concent.task_to_compute.compute_task_def['deadline'],
            self._parse_iso_date_to_timestamp("2017-12-01 11:00:00")
        )
        self.assertEqual(message_from_concent.task_to_compute.compute_task_def['task_id'], '99')

    def test_concent_requests_task_result_from_provider_and_requestor_receives_task_result(self):
        """
        Tests if on requestor ForceGetTaskResult message Concent will return ForceGetTaskResultUpload
        if provider uploads correct result.

        Expected message exchange:
        Requestor -> Concent:     ForceGetTaskResult
        Concent   -> Requestor:   ForceGetTaskResultAck
        Concent   -> Provider:    ForceGetTaskResultUpload
        Provider  -> Concent:     Upload good files
        Concent   -> Requestor:   ForceGetTaskResultUpload
        """

        # STEP 1: Requestor forces get task result via Concent.
        # Concent accepts request if all conditions were met.
        deserialized_task_to_compute = self._get_deserialized_task_to_compute(
            timestamp   = "2017-12-01 10:00:00",
            task_id     = '99',
            deadline    = "2017-12-01 11:00:00"
        )
        deserialized_report_computed_task = self._get_deserialized_report_computed_task(
            task_to_compute = deserialized_task_to_compute
        )
        serialized_force_get_task_result = self._get_serialized_force_get_task_result(
            report_computed_task = deserialized_report_computed_task,
            timestamp       = "2017-12-01 11:00:01",
        )
        deserialized_force_get_task_result = load(
            serialized_force_get_task_result,
            CONCENT_PRIVATE_KEY,
            self.REQUESTOR_PUBLIC_KEY,
            check_time=False,
        )

        with freeze_time("2017-12-01 11:00:01"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                           = serialized_force_get_task_result,
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_requestor_public_key()
            )

        self.assertEqual(response_1.status_code, 200)

        # STEP 2: Provider receives force get task result and file transfer token inside ForceGetTaskResultUpload via Concent.
        with freeze_time("2017-12-01 11:00:12"):
            response_2 = self.client.post(
                reverse('core:receive'),
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_provider_public_key()
            )

        self.assertEqual(response_2.status_code, 200)

        message_from_concent = load(response_2.content, self.PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY, check_time = False)
        self.assertIsInstance(message_from_concent, message.concents.ForceGetTaskResultUpload)

        # Assign each message to correct variable
        message_force_get_task_result = message_from_concent.force_get_task_result
        message_file_transfer_token = message_from_concent.file_transfer_token

        # Test ForceGetTaskResult message
        self.assertIsInstance(message_force_get_task_result, message.concents.ForceGetTaskResult)
        self.assertEqual(message_force_get_task_result.timestamp, self._parse_iso_date_to_timestamp("2017-12-01 11:00:01"))
        self.assertEqual(message_force_get_task_result.report_computed_task.task_to_compute, deserialized_task_to_compute)
        self.assertEqual(message_force_get_task_result.report_computed_task.task_to_compute.compute_task_def, deserialized_task_to_compute.compute_task_def)   # pylint: disable=no-member
        self.assertEqual(
            message_force_get_task_result.report_computed_task.task_to_compute.compute_task_def['deadline'],
            self._parse_iso_date_to_timestamp("2017-12-01 11:00:00")
        )
        self.assertEqual(message_force_get_task_result.report_computed_task.task_to_compute.compute_task_def['task_id'], '99')

        # Test FileTransferToken message
        self.assertIsInstance(message_file_transfer_token, message.FileTransferToken)
        self.assertEqual(message_file_transfer_token.timestamp, self._parse_iso_date_to_timestamp("2017-12-01 11:00:12"))
        self.assertEqual(message_file_transfer_token.token_expiration_deadline, self._parse_iso_date_to_timestamp("2017-12-01 11:30:12"))
        self.assertEqual(message_file_transfer_token.operation, 'upload')

        # STEP 3: Requestor receives force get task result failed due to lack of provider submit.
        with freeze_time("2017-12-01 11:00:21"):
            response_3 = self.client.post(
                reverse('core:receive'),
                data                           = '',
                content_type                   = '',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
            )

        self.assertEqual(response_3.status_code,  200)

        message_from_concent = load(response_3.content, self.REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY, check_time = False)

        self.assertIsInstance(message_from_concent, message.concents.ForceGetTaskResultUpload)
        self.assertEqual(message_from_concent.timestamp, self._parse_iso_date_to_timestamp("2017-12-01 11:00:21"))

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
        self.assertEqual(
            message_from_concent.file_transfer_token.timestamp,
            self._parse_iso_date_to_timestamp("2017-12-01 11:00:21")
        )
        self.assertEqual(
            message_from_concent.file_transfer_token.token_expiration_deadline,
            self._parse_iso_date_to_timestamp("2017-12-01 11:30:21")
        )
        self.assertEqual(message_from_concent.file_transfer_token.operation, 'download')
