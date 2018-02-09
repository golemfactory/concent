from unittest               import skip
import mock

from django.test            import override_settings
from django.urls            import reverse
from freezegun              import freeze_time
from golem_messages         import load
from golem_messages         import message

from core.models            import MessageAuth
from core.tests.utils       import ConcentIntegrationTestCase
from utils.testing_helpers  import generate_ecc_key_pair


(CONCENT_PRIVATE_KEY, CONCENT_PUBLIC_KEY)                         = generate_ecc_key_pair()


def get_file_status_true_mock(_file_transfer_token_from_database):
    return True


def get_file_status_false_mock(_file_transfer_token_from_database):
    return False


@override_settings(
    CONCENT_PRIVATE_KEY    = CONCENT_PRIVATE_KEY,
    CONCENT_PUBLIC_KEY     = CONCENT_PUBLIC_KEY,
    CONCENT_MESSAGING_TIME = 10,  # seconds
    FORCE_ACCEPTANCE_TIME  = 10,  # seconds
)
class AuthGetTaskResultIntegrationTest(ConcentIntegrationTestCase):

    @skip('Waiting for change to ServiceRefused instead ForceGetTaskResultRejected')
    def test_requestor_forces_get_task_result_and_concent_immediately_sends_rejection_due_to_already_sent_message_should_work_only_with_correct_keys(self):
        """
        Tests if on requestor ForceGetTaskResult message Concent will return ForceGetTaskResultRejected
        if ForceGetTaskResult was already sent by this requestor.

        Expected message exchange:
        Requestor               -> Concent:                 ForceGetTaskResult
        Concent                 -> Requestor:               ForceGetTaskResultAck
        WrongRequestor/Provider -> Concent                  ForceGetTaskResult
        Concent                 -> WrongRequestor/Provider  ForceGetTaskResultAck
        Requestor               -> Concent:                 ForceGetTaskResult
        Concent                 -> Requestor:               ForceGetTaskResultRejected
        """

        # STEP 1: Requestor forces get task result via Concent.
        deserialized_task_to_compute = self._get_deserialized_task_to_compute(
            timestamp = "2017-12-01 10:00:00",
            deadline  = "2017-12-01 11:00:00",
        )
        deserialized_report_computed_task = self._get_deserialized_report_computed_task(
            task_to_compute = deserialized_task_to_compute
        )
        original_serialized_force_get_task_result = self._get_serialized_force_get_task_result(
            report_computed_task = deserialized_report_computed_task,
            timestamp            = "2017-12-01 11:00:08",
        )

        with freeze_time("2017-12-01 11:00:08"):
            response = self.client.post(
                reverse('core:send'),
                data                                = original_serialized_force_get_task_result,
                content_type                        = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY      = self._get_encoded_requestor_public_key(),
                HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = self._get_encoded_provider_public_key(),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(MessageAuth.objects.count(), 1)

        message_auth = MessageAuth.objects.last()
        self.assertEqual(message_auth.message.type,               message.concents.ForceGetTaskResult.TYPE)
        self.assertEqual(message_auth.provider_public_key_bytes,  self.PROVIDER_PUBLIC_KEY)
        self.assertEqual(message_auth.requestor_public_key_bytes, self.REQUESTOR_PUBLIC_KEY)

        # STEP 2: Requestor again forces get task result via Concent with wrong key or mixed key.
        # Concent do not rejects request immediately because message was already sent.
        serialized_force_get_task_result = self._get_serialized_force_get_task_result(
            report_computed_task  = deserialized_report_computed_task,
            timestamp             = "2017-12-01 11:00:08",
            requestor_private_key = self.DIFFERENT_REQUESTOR_PRIVATE_KEY,
        )

        with freeze_time("2017-12-01 11:00:08"):
            response = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_get_task_result,
                content_type                        = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY      = self._get_encoded_key(self.DIFFERENT_REQUESTOR_PUBLIC_KEY),
                HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = self._get_encoded_provider_public_key(),
            )

        self.assertEqual(response.status_code,  200)

        message_from_concent = load(
            response.content,
            self.DIFFERENT_REQUESTOR_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY,
            check_time = False
        )

        self.assertIsInstance(message_from_concent, message.concents.ForceGetTaskResultAck)
        self.assertEqual(message_from_concent.timestamp, self._parse_iso_date_to_timestamp("2017-12-01 11:00:08"))

        self.assertEqual(MessageAuth.objects.count(), 2)

        message_auth = MessageAuth.objects.last()
        self.assertEqual(message_auth.message.type,               message.concents.ForceGetTaskResult.TYPE)
        self.assertEqual(message_auth.provider_public_key_bytes,  self.PROVIDER_PUBLIC_KEY)
        self.assertEqual(message_auth.requestor_public_key_bytes, self.DIFFERENT_REQUESTOR_PUBLIC_KEY)

        serialized_force_get_task_result = self._get_serialized_force_get_task_result(
            report_computed_task  = deserialized_report_computed_task,
            timestamp             = "2017-12-01 11:00:08",
            requestor_private_key = self.PROVIDER_PRIVATE_KEY,
        )

        with freeze_time("2017-12-01 11:00:08"):
            response = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_get_task_result,
                content_type                        = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY      = self._get_encoded_provider_public_key(),
                HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
            )

        self.assertEqual(response.status_code,  200)

        message_from_concent = load(response.content, self.PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY, check_time = False)

        self.assertIsInstance(message_from_concent, message.concents.ForceGetTaskResultAck)
        self.assertEqual(message_from_concent.timestamp, self._parse_iso_date_to_timestamp("2017-12-01 11:00:08"))

        self.assertEqual(MessageAuth.objects.count(), 3)

        message_auth = MessageAuth.objects.last()
        self.assertEqual(message_auth.message.type,               message.concents.ForceGetTaskResult.TYPE)
        self.assertEqual(message_auth.provider_public_key_bytes,  self.REQUESTOR_PUBLIC_KEY)
        self.assertEqual(message_auth.requestor_public_key_bytes, self.PROVIDER_PUBLIC_KEY)

        # STEP 3: Requestor again forces get task result via Concent with correct key.
        # Concent rejects request immediately because message was already sent.
        with freeze_time("2017-12-01 11:00:08"):
            response = self.client.post(
                reverse('core:send'),
                data                                = original_serialized_force_get_task_result,
                content_type                        = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY      = self._get_encoded_requestor_public_key(),
                HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = self._get_encoded_provider_public_key(),
            )

        self.assertEqual(response.status_code,  200)

        message_from_concent = load(response.content, self.REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY, check_time = False)

        self.assertIsInstance(message_from_concent,      message.concents.ForceGetTaskResultRejected)
        self.assertEqual(message_from_concent.timestamp, self._parse_iso_date_to_timestamp("2017-12-01 11:00:08"))
        self.assertEqual(message_from_concent.reason,    message_from_concent.REASON.OperationAlreadyInitiated)

        self.assertEqual(MessageAuth.objects.count(), 3)

    def test_concent_requests_task_result_from_provider_and_requestor_receives_failure_because_provider_does_not_submit_should_work_only_with_correct_keys(self):
        """
        Tests if on requestor ForceGetTaskResult message Concent will return ForceGetTaskResultFailed
        if provider doesn't submit result.

        Expected message exchange:
        Requestor -> Concent:                   ForceGetTaskResult
        Concent   -> Requestor:                 ForceGetTaskResultAck
        Concent   -> WrongProvider/Requestor:   HTTP 204
        Concent   -> Provider:                  ForceGetTaskResultUpload
        Provider  -> Concent:                   no response
        Concent   -> Requestor:                 ForceGetTaskResultFailed
        Concent   -> WrongRequestor/Provider:   ForceGetTaskResultFailed
        """

        # STEP 1: Requestor forces get task result via Concent.
        # Concent accepts request if all conditions were met.
        deserialized_task_to_compute = self._get_deserialized_task_to_compute(
            timestamp = "2017-12-01 10:00:00",
            task_id   = '99',
            deadline  = "2017-12-01 11:00:00"
        )
        deserialized_report_computed_task = self._get_deserialized_report_computed_task(
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
                data                                = serialized_force_get_task_result,
                content_type                        = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY      = self._get_encoded_requestor_public_key(),
                HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = self._get_encoded_provider_public_key(),
            )

        self.assertEqual(response.status_code,        200)
        self.assertEqual(MessageAuth.objects.count(), 1)

        message_auth = MessageAuth.objects.last()
        self.assertEqual(message_auth.message.type,               message.concents.ForceGetTaskResult.TYPE)
        self.assertEqual(message_auth.provider_public_key_bytes,  self.PROVIDER_PUBLIC_KEY)
        self.assertEqual(message_auth.requestor_public_key_bytes, self.REQUESTOR_PUBLIC_KEY)

        # STEP 2: Provider do not receive force get task result and file transfer token inside
        # ForceGetTaskResultUpload via Concent with with different or mixed key.
        with freeze_time("2017-12-01 11:00:12"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = '',
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_key(self.DIFFERENT_PROVIDER_PUBLIC_KEY)
            )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(len(response.content),       0)
        self.assertEqual(MessageAuth.objects.count(), 1)

        with freeze_time("2017-12-01 11:00:12"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = '',
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_requestor_public_key()
            )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(len(response.content),       0)
        self.assertEqual(MessageAuth.objects.count(), 1)

        # STEP 3: Provider receives force get task result and file transfer token inside ForceGetTaskResultUpload via
        # Concent with correct key.
        with freeze_time("2017-12-01 11:00:12"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = '',
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_provider_public_key()
            )

        self.assertEqual(response.status_code, 200)

        message_from_concent = load(
            response.content,
            self.PROVIDER_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY,
            check_time = False
        )

        self.assertIsInstance(message_from_concent,   message.concents.ForceGetTaskResultUpload)
        self.assertEqual(MessageAuth.objects.count(), 2)

        message_auth = MessageAuth.objects.last()
        self.assertEqual(message_auth.message.type,               message.concents.ForceGetTaskResultUpload.TYPE)
        self.assertEqual(message_auth.provider_public_key_bytes,  self.PROVIDER_PUBLIC_KEY)
        self.assertEqual(message_auth.requestor_public_key_bytes, self.REQUESTOR_PUBLIC_KEY)

        # Assign each message to correct variable
        message_force_get_task_result = message_from_concent.force_get_task_result
        message_file_transfer_token   = message_from_concent.file_transfer_token

        # Test ForceGetTaskResult message

        self.assertIsInstance(message_force_get_task_result,                                 message.concents.ForceGetTaskResult)
        self.assertEqual(message_force_get_task_result.timestamp,                            self._parse_iso_date_to_timestamp("2017-12-01 11:00:01"))
        self.assertEqual(message_force_get_task_result.report_computed_task.task_to_compute, deserialized_force_get_task_result.report_computed_task.task_to_compute)
        self.assertEqual(message_force_get_task_result.report_computed_task.task_to_compute.compute_task_def, deserialized_force_get_task_result.report_computed_task.task_to_compute.compute_task_def)
        self.assertEqual(
            message_force_get_task_result.report_computed_task.task_to_compute.compute_task_def['deadline'],
            self._parse_iso_date_to_timestamp("2017-12-01 11:00:00")
        )
        self.assertEqual(
            message_force_get_task_result.report_computed_task.task_to_compute.compute_task_def['task_id'],
            '99'
        )

        # Test FileTransferToken message
        self.assertIsInstance(message_file_transfer_token, message.FileTransferToken)
        self.assertEqual(message_file_transfer_token.timestamp,                 self._parse_iso_date_to_timestamp("2017-12-01 11:00:12"))
        self.assertEqual(message_file_transfer_token.token_expiration_deadline, self._parse_iso_date_to_timestamp("2017-12-01 11:30:12"))
        self.assertEqual(message_file_transfer_token.operation,                 'upload')

        # STEP 4: Requestor do not receives force get task result failed due to lack of provider submit
        # with different or mixed key.
        with mock.patch('core.views.get_file_status', get_file_status_false_mock):
            with freeze_time("2017-12-01 11:00:21"):
                response = self.client.post(
                    reverse('core:receive'),
                    data                           = '',
                    content_type                   = '',
                    HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_key(self.DIFFERENT_REQUESTOR_PUBLIC_KEY),
                )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(MessageAuth.objects.count(), 2)
        self.assertEqual(len(response.content),       0)

        with mock.patch('core.views.get_file_status', get_file_status_false_mock):
            with freeze_time("2017-12-01 11:00:21"):
                response = self.client.post(
                    reverse('core:receive'),
                    data                           = '',
                    content_type                   = '',
                    HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_provider_public_key(),
                )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(MessageAuth.objects.count(), 2)
        self.assertEqual(len(response.content),       0)

        # STEP 5: Requestor receives force get task result failed due to lack of provider submit with correct key.
        with mock.patch('core.views.get_file_status', get_file_status_false_mock):
            with freeze_time("2017-12-01 11:00:21"):
                response = self.client.post(
                    reverse('core:receive'),
                    data                           = '',
                    content_type                   = '',
                    HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
                )

        self.assertEqual(response.status_code,        200)
        self.assertEqual(MessageAuth.objects.count(), 3)

        message_auth = MessageAuth.objects.last()
        self.assertEqual(message_auth.message.type,               message.concents.ForceGetTaskResultFailed.TYPE)
        self.assertEqual(message_auth.provider_public_key_bytes,  self.PROVIDER_PUBLIC_KEY)
        self.assertEqual(message_auth.requestor_public_key_bytes, self.REQUESTOR_PUBLIC_KEY)

        message_from_concent = load(
            response.content,
            self.REQUESTOR_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY,
            check_time = False
        )

        self.assertIsInstance(message_from_concent, message.concents.ForceGetTaskResultFailed)
        self.assertEqual(message_from_concent.timestamp,        self._parse_iso_date_to_timestamp("2017-12-01 11:00:21"))
        self.assertEqual(message_from_concent.task_to_compute,  deserialized_task_to_compute)
        self.assertEqual(
            message_from_concent.task_to_compute.compute_task_def,
            deserialized_task_to_compute.compute_task_def  # pylint: disable=no-member
        )
        self.assertEqual(
            message_from_concent.task_to_compute.compute_task_def['deadline'],
            self._parse_iso_date_to_timestamp("2017-12-01 11:00:00")
        )
        self.assertEqual(message_from_concent.task_to_compute.compute_task_def['task_id'], '99')

    def test_concent_requests_task_result_from_provider_and_requestor_receives_failure_because_provider_does_not_finish_upload_should_work_only_with_correct_keys(self):
        """
        Tests if on requestor ForceGetTaskResult message Concent will return ForceGetTaskResultFailed
        if provider doesn't finish upload result.

        Expected message exchange:
        Requestor -> Concent:                   ForceGetTaskResult
        Concent   -> Requestor:                 ForceGetTaskResultAck
        Concent   -> WrongProvider/Requestor:   HTTP 204
        Concent   -> Provider:                  ForceGetTaskResultUpload
        Provider  -> Concent:                   Starts Upload
        Concent   -> WrongRequestor/Provider:   HTTP 204
        Concent   -> Requestor:                 ForceGetTaskResultFailed
        """

        # STEP 1: Requestor forces get task result via Concent.
        # Concent accepts request if all conditions were met.
        deserialized_task_to_compute = self._get_deserialized_task_to_compute(
            timestamp = "2017-12-01 10:00:00",
            task_id   = '99',
            deadline  = "2017-12-01 11:00:00"
        )
        deserialized_report_computed_task = self._get_deserialized_report_computed_task(
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
                data                                = serialized_force_get_task_result,
                content_type                        = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY      = self._get_encoded_requestor_public_key(),
                HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = self._get_encoded_provider_public_key(),
            )

        self.assertEqual(response.status_code,      200)
        self.assertEqual(MessageAuth.objects.count(), 1)

        message_auth = MessageAuth.objects.last()
        self.assertEqual(message_auth.message.type,               message.concents.ForceGetTaskResult.TYPE)
        self.assertEqual(message_auth.provider_public_key_bytes,  self.PROVIDER_PUBLIC_KEY)
        self.assertEqual(message_auth.requestor_public_key_bytes, self.REQUESTOR_PUBLIC_KEY)

        # STEP 2: Provider do not receive force get task result and file transfer token inside
        # ForceGetTaskResultUpload via Concent with different or mixed key.
        with freeze_time("2017-12-01 11:00:12"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = '',
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_key(self.DIFFERENT_PROVIDER_PUBLIC_KEY)
            )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(len(response.content),       0)
        self.assertEqual(MessageAuth.objects.count(), 1)

        with freeze_time("2017-12-01 11:00:12"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = '',
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_requestor_public_key()
            )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(len(response.content),       0)
        self.assertEqual(MessageAuth.objects.count(), 1)

        # STEP 3: Provider receives force get task result and file transfer token inside ForceGetTaskResultUpload via
        # Concent with correct key.
        with freeze_time("2017-12-01 11:00:12"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = '',
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_provider_public_key()
            )

        self.assertEqual(response.status_code,      200)
        self.assertEqual(MessageAuth.objects.count(), 2)

        message_auth = MessageAuth.objects.last()
        self.assertEqual(message_auth.message.type,               message.concents.ForceGetTaskResultUpload.TYPE)
        self.assertEqual(message_auth.provider_public_key_bytes,  self.PROVIDER_PUBLIC_KEY)
        self.assertEqual(message_auth.requestor_public_key_bytes, self.REQUESTOR_PUBLIC_KEY)

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
            self._parse_iso_date_to_timestamp("2017-12-01 11:00:01")
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
            self._parse_iso_date_to_timestamp("2017-12-01 11:00:00")
        )
        self.assertEqual(message_force_get_task_result.report_computed_task.task_to_compute.compute_task_def['task_id'], '99')

        # Test FileTransferToken message
        self.assertIsInstance(message_file_transfer_token, message.FileTransferToken)
        self.assertEqual(message_file_transfer_token.timestamp,                 self._parse_iso_date_to_timestamp("2017-12-01 11:00:12"))
        self.assertEqual(message_file_transfer_token.token_expiration_deadline, self._parse_iso_date_to_timestamp("2017-12-01 11:30:12"))
        self.assertEqual(message_file_transfer_token.operation,                 'upload')

        # STEP 4: Requestor do not receives force get task result failed due to lack of provider submit
        # with different or mixed key.
        with mock.patch('core.views.get_file_status', get_file_status_false_mock):
            with freeze_time("2017-12-01 11:00:21"):
                response = self.client.post(
                    reverse('core:receive'),
                    data                           ='',
                    content_type                   = '',
                    HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_key(self.DIFFERENT_REQUESTOR_PUBLIC_KEY),
                )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(MessageAuth.objects.count(), 2)
        self.assertEqual(len(response.content),       0)

        with mock.patch('core.views.get_file_status', get_file_status_false_mock):
            with freeze_time("2017-12-01 11:00:21"):
                response = self.client.post(
                    reverse('core:receive'),
                    data                           = '',
                    content_type                   = '',
                    HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_provider_public_key(),
                )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(MessageAuth.objects.count(), 2)
        self.assertEqual(len(response.content),       0)

        # STEP 5: Requestor receives force get task result failed due to lack of provider submit with correct key.
        with mock.patch('core.views.get_file_status', get_file_status_false_mock):
            with freeze_time("2017-12-01 11:00:21"):
                response = self.client.post(
                    reverse('core:receive'),
                    data                           = '',
                    content_type                   = '',
                    HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
                )

        self.assertEqual(response.status_code,      200)
        self.assertEqual(MessageAuth.objects.count(), 3)

        message_auth = MessageAuth.objects.last()
        self.assertEqual(message_auth.message.type,               message.concents.ForceGetTaskResultFailed.TYPE)
        self.assertEqual(message_auth.provider_public_key_bytes,  self.PROVIDER_PUBLIC_KEY)
        self.assertEqual(message_auth.requestor_public_key_bytes, self.REQUESTOR_PUBLIC_KEY)

        message_from_concent = load(
            response.content,
            self.REQUESTOR_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY,
            check_time = False
        )

        self.assertIsInstance(message_from_concent, message.concents.ForceGetTaskResultFailed)
        self.assertEqual(message_from_concent.timestamp,                                    self._parse_iso_date_to_timestamp("2017-12-01 11:00:21"))
        self.assertEqual(message_from_concent.task_to_compute,                              deserialized_task_to_compute)
        self.assertEqual(message_from_concent.task_to_compute.compute_task_def,             deserialized_task_to_compute.compute_task_def)   # pylint: disable=no-member
        self.assertEqual(message_from_concent.task_to_compute.compute_task_def['deadline'], self._parse_iso_date_to_timestamp("2017-12-01 11:00:00"))
        self.assertEqual(message_from_concent.task_to_compute.compute_task_def['task_id'],  '99')

    def test_concent_requests_task_result_from_provider_and_requestor_receives_failure_because_provider_uploads_bad_files_should_work_only_with_correct_keys(self):
        """
        Tests if on requestor ForceGetTaskResult message Concent will return ForceGetTaskResultFailed
        if provider uploads bad or incomplete result.

        Expected message exchange:
        Requestor -> Concent:                   ForceGetTaskResult
        Concent   -> Requestor:                 ForceGetTaskResultAck
        Concent   -> WrongProvider/Requestor:   ForceGetTaskResultUpload
        Concent   -> Provider:                  ForceGetTaskResultUpload
        Provider  -> Concent:                   Upload bad files
        Concent   -> WrongRequestor/Provider:   ForceGetTaskResultFailed
        Concent   -> Requestor:                 ForceGetTaskResultFailed
        """

        # STEP 1: Requestor forces get task result via Concent.
        # Concent accepts request if all conditions were met.
        deserialized_task_to_compute = self._get_deserialized_task_to_compute(
            timestamp = "2017-12-01 10:00:00",
            task_id   = '99',
            deadline  = "2017-12-01 11:00:00"
        )
        deserialized_report_computed_task = self._get_deserialized_report_computed_task(
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
                data                                = serialized_force_get_task_result,
                content_type                        = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY      = self._get_encoded_requestor_public_key(),
                HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = self._get_encoded_provider_public_key(),
            )

        self.assertEqual(response.status_code,      200)
        self.assertEqual(MessageAuth.objects.count(), 1)

        message_auth = MessageAuth.objects.last()
        self.assertEqual(message_auth.message.type,               message.concents.ForceGetTaskResult.TYPE)
        self.assertEqual(message_auth.provider_public_key_bytes,  self.PROVIDER_PUBLIC_KEY)
        self.assertEqual(message_auth.requestor_public_key_bytes, self.REQUESTOR_PUBLIC_KEY)

        # STEP 2: Provider do not receive force get task result and file transfer token inside
        # ForceGetTaskResultUpload via Concent with with different or mixed key.
        with freeze_time("2017-12-01 11:00:12"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = '',
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_key(self.DIFFERENT_PROVIDER_PUBLIC_KEY)
            )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(len(response.content),       0)
        self.assertEqual(MessageAuth.objects.count(), 1)

        with freeze_time("2017-12-01 11:00:12"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = '',
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_requestor_public_key()
            )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(len(response.content),       0)
        self.assertEqual(MessageAuth.objects.count(), 1)

        # STEP 3: Provider receives force get task result and file transfer token inside ForceGetTaskResultUpload via
        # Concent with correct key.
        with freeze_time("2017-12-01 11:00:12"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = '',
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_provider_public_key()
            )

        self.assertEqual(response.status_code,      200)
        self.assertEqual(MessageAuth.objects.count(), 2)

        message_auth = MessageAuth.objects.last()
        self.assertEqual(message_auth.message.type,               message.concents.ForceGetTaskResultUpload.TYPE)
        self.assertEqual(message_auth.provider_public_key_bytes,  self.PROVIDER_PUBLIC_KEY)
        self.assertEqual(message_auth.requestor_public_key_bytes, self.REQUESTOR_PUBLIC_KEY)

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
        self.assertEqual(message_file_transfer_token.timestamp,                 self._parse_iso_date_to_timestamp("2017-12-01 11:00:12"))
        self.assertEqual(message_file_transfer_token.token_expiration_deadline, self._parse_iso_date_to_timestamp("2017-12-01 11:30:12"))
        self.assertEqual(message_file_transfer_token.operation,                 'upload')

        # STEP 4: Requestor do not receives force get task result failed due to lack of provider submit
        # with different or mixed key.
        with mock.patch('core.views.get_file_status', get_file_status_false_mock):
            with freeze_time("2017-12-01 11:00:21"):
                response = self.client.post(
                    reverse('core:receive'),
                    data                           = '',
                    content_type                   = '',
                    HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_key(self.DIFFERENT_REQUESTOR_PUBLIC_KEY),
                )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(MessageAuth.objects.count(), 2)
        self.assertEqual(len(response.content),       0)

        with mock.patch('core.views.get_file_status', get_file_status_false_mock):
            with freeze_time("2017-12-01 11:00:21"):
                response = self.client.post(
                    reverse('core:receive'),
                    data                           = '',
                    content_type                   = '',
                    HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_provider_public_key(),
                )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(MessageAuth.objects.count(), 2)
        self.assertEqual(len(response.content),       0)

        # STEP 5: Requestor receives force get task result failed due to lack of provider submit with correct key.
        with mock.patch('core.views.get_file_status', get_file_status_false_mock):
            with freeze_time("2017-12-01 11:00:21"):
                response = self.client.post(
                    reverse('core:receive'),
                    data                           = '',
                    content_type                   = '',
                    HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
                )

        self.assertEqual(response.status_code,      200)
        self.assertEqual(MessageAuth.objects.count(), 3)

        message_auth = MessageAuth.objects.last()
        self.assertEqual(message_auth.message.type,               message.concents.ForceGetTaskResultFailed.TYPE)
        self.assertEqual(message_auth.provider_public_key_bytes,  self.PROVIDER_PUBLIC_KEY)
        self.assertEqual(message_auth.requestor_public_key_bytes, self.REQUESTOR_PUBLIC_KEY)

        message_from_concent = load(
            response.content,
            self.REQUESTOR_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY,
            check_time = False
        )

        self.assertIsInstance(message_from_concent, message.concents.ForceGetTaskResultFailed)
        self.assertEqual(message_from_concent.timestamp,       self._parse_iso_date_to_timestamp("2017-12-01 11:00:21"))
        self.assertEqual(message_from_concent.task_to_compute, deserialized_task_to_compute)
        self.assertEqual(
            message_from_concent.task_to_compute.compute_task_def,
            deserialized_task_to_compute.compute_task_def  # pylint: disable=no-member
        )
        self.assertEqual(
            message_from_concent.task_to_compute.compute_task_def['deadline'],
            self._parse_iso_date_to_timestamp("2017-12-01 11:00:00")
        )
        self.assertEqual(message_from_concent.task_to_compute.compute_task_def['task_id'], '99')

    def test_concent_requests_task_result_from_provider_and_requestor_receives_task_result_should_work_only_with_correct_keys(self):
        """
        Tests if on requestor ForceGetTaskResult message Concent will return ForceGetTaskResultUpload
        if provider uploads correct result.

        Expected message exchange:
        Requestor -> Concent:                   ForceGetTaskResult
        Concent   -> Requestor:                 ForceGetTaskResultAck
        Concent   -> WrongProvider/Requestor:   HTTP 204
        Concent   -> Provider:                  ForceGetTaskResultUpload
        Provider  -> Concent:                   Upload good files
        Concent   -> WrongRequestor/Provider:   HTTP 204
        Concent   -> Requestor:                 ForceGetTaskResultUpload
        """

        # STEP 1: Requestor forces get task result via Concent.
        # Concent accepts request if all conditions were met.
        deserialized_task_to_compute = self._get_deserialized_task_to_compute(
            timestamp = "2017-12-01 10:00:00",
            task_id   = '99',
            deadline  = "2017-12-01 11:00:00"
        )
        deserialized_report_computed_task = self._get_deserialized_report_computed_task(
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
                data                                = serialized_force_get_task_result,
                content_type                        = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY      = self._get_encoded_requestor_public_key(),
                HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY =self._get_encoded_provider_public_key(),
            )

        self.assertEqual(response.status_code,      200)
        self.assertEqual(MessageAuth.objects.count(), 1)

        message_auth = MessageAuth.objects.last()
        self.assertEqual(message_auth.message.type,               message.concents.ForceGetTaskResult.TYPE)
        self.assertEqual(message_auth.provider_public_key_bytes,  self.PROVIDER_PUBLIC_KEY)
        self.assertEqual(message_auth.requestor_public_key_bytes, self.REQUESTOR_PUBLIC_KEY)

        # STEP 2: Provider do not receive force get task result and file transfer token inside
        # ForceGetTaskResultUpload via Concent with with different or mixed key.
        with freeze_time("2017-12-01 11:00:12"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = '',
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_key(self.DIFFERENT_PROVIDER_PUBLIC_KEY)
            )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(len(response.content),       0)
        self.assertEqual(MessageAuth.objects.count(), 1)

        with freeze_time("2017-12-01 11:00:12"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = '',
                content_type                   ='application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_requestor_public_key()
            )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(len(response.content),       0)
        self.assertEqual(MessageAuth.objects.count(), 1)

        # STEP 3: Provider receives force get task result and file transfer token inside ForceGetTaskResultUpload via
        # Concent with correct key.
        with freeze_time("2017-12-01 11:00:12"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = '',
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_provider_public_key()
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(MessageAuth.objects.count(), 2)

        message_auth = MessageAuth.objects.last()
        self.assertEqual(message_auth.message.type,               message.concents.ForceGetTaskResultUpload.TYPE)
        self.assertEqual(message_auth.provider_public_key_bytes,  self.PROVIDER_PUBLIC_KEY)
        self.assertEqual(message_auth.requestor_public_key_bytes, self.REQUESTOR_PUBLIC_KEY)

        message_from_concent = load(response.content, self.PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY, check_time = False)
        self.assertIsInstance(message_from_concent, message.concents.ForceGetTaskResultUpload)

        # Assign each message to correct variable
        message_force_get_task_result = message_from_concent.force_get_task_result
        message_file_transfer_token   = message_from_concent.file_transfer_token

        # Test ForceGetTaskResult message
        self.assertIsInstance(message_force_get_task_result,                                 message.concents.ForceGetTaskResult)
        self.assertEqual(message_force_get_task_result.timestamp,                            self._parse_iso_date_to_timestamp("2017-12-01 11:00:01"))
        self.assertEqual(message_force_get_task_result.report_computed_task.task_to_compute, deserialized_task_to_compute)
        self.assertEqual(
            message_force_get_task_result.report_computed_task.task_to_compute.compute_task_def,
            deserialized_task_to_compute.compute_task_def  # pylint: disable=no-member
        )
        self.assertEqual(
            message_force_get_task_result.report_computed_task.task_to_compute.compute_task_def['deadline'],
            self._parse_iso_date_to_timestamp("2017-12-01 11:00:00")
        )
        self.assertEqual(
            message_force_get_task_result.report_computed_task.task_to_compute.compute_task_def['task_id'],
            '99'
        )

        # Test FileTransferToken message
        self.assertIsInstance(message_file_transfer_token, message.FileTransferToken)
        self.assertEqual(message_file_transfer_token.timestamp,                 self._parse_iso_date_to_timestamp("2017-12-01 11:00:12"))
        self.assertEqual(message_file_transfer_token.token_expiration_deadline, self._parse_iso_date_to_timestamp("2017-12-01 11:30:12"))
        self.assertEqual(message_file_transfer_token.operation,                 'upload')

        # STEP 4: Requestor do not receives force get task result failed due to lack of provider submit
        # with different or mixed key.
        with mock.patch('core.views.get_file_status', get_file_status_false_mock):
            with freeze_time("2017-12-01 11:00:21"):
                response = self.client.post(
                    reverse('core:receive'),
                    data                           = '',
                    content_type                   = '',
                    HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_key(self.DIFFERENT_REQUESTOR_PUBLIC_KEY),
                )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(MessageAuth.objects.count(), 2)
        self.assertEqual(len(response.content),       0)

        with mock.patch('core.views.get_file_status', get_file_status_false_mock):
            with freeze_time("2017-12-01 11:00:21"):
                response = self.client.post(
                    reverse('core:receive'),
                    data                           = '',
                    content_type                   = '',
                    HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_provider_public_key(),
                )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(MessageAuth.objects.count(), 2)
        self.assertEqual(len(response.content),       0)

        # STEP 5: Requestor receives force get task result failed due to lack of provider submit with correct key.
        with mock.patch('core.views.get_file_status', get_file_status_true_mock):
            with freeze_time("2017-12-01 11:00:21"):
                response = self.client.post(
                    reverse('core:receive'),
                    data                           = '',
                    content_type                   = '',
                    HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
                )

        self.assertEqual(response.status_code,      200)
        self.assertEqual(MessageAuth.objects.count(), 3)

        message_auth = MessageAuth.objects.last()
        self.assertEqual(message_auth.message.type,               message.concents.ForceGetTaskResultUpload.TYPE)
        self.assertEqual(message_auth.provider_public_key_bytes,  self.PROVIDER_PUBLIC_KEY)
        self.assertEqual(message_auth.requestor_public_key_bytes, self.REQUESTOR_PUBLIC_KEY)

        message_from_concent = load(
            response.content,
            self.REQUESTOR_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY,
            check_time = False
        )

        self.assertIsInstance(message_from_concent,      message.concents.ForceGetTaskResultUpload)
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
