from base64                 import b64encode
import dateutil.parser

from django.test            import override_settings
from django.urls            import reverse
from freezegun              import freeze_time
from golem_messages         import dump
from golem_messages         import load
from golem_messages         import message

from core.tests.utils import ConcentIntegrationTestCase
from core.tests.utils import parse_iso_date_to_timestamp
from core.models            import PendingResponse
from core.models            import Subtask
from common.constants        import ErrorCode
from common.testing_helpers  import generate_ecc_key_pair


(CONCENT_PRIVATE_KEY, CONCENT_PUBLIC_KEY) = generate_ecc_key_pair()


@override_settings(
    CONCENT_PRIVATE_KEY    = CONCENT_PRIVATE_KEY,
    CONCENT_PUBLIC_KEY     = CONCENT_PUBLIC_KEY,
    CONCENT_MESSAGING_TIME = 10,  # seconds
)
class AuthReportComputedTaskIntegrationTest(ConcentIntegrationTestCase):

    def setUp(self):
        super().setUp()
        self.compute_task_def = self._get_deserialized_compute_task_def(
            task_id='1',
            subtask_id='8',
            deadline=int(dateutil.parser.parse("2017-12-01 11:00:00").timestamp())
        )

        with freeze_time("2017-12-01 10:00:00"):
            self.deserialized_task_to_compute = self._get_deserialized_task_to_compute(
                compute_task_def      = self.compute_task_def,
                signer_private_key=self.REQUESTOR_PRIVATE_KEY,
            )

        with freeze_time("2017-12-01 10:59:00"):
            self.report_computed_task = self._get_deserialized_report_computed_task(
                task_to_compute = self.deserialized_task_to_compute
            )
            self.force_report_computed_task = self._get_deserialized_force_report_computed_task(
                report_computed_task=self.report_computed_task
            )

        self.serialized_force_report_computed_task = self._get_serialized_force_report_computed_task(
            timestamp="2017-12-01 11:01:00",
            force_report_computed_task=self.force_report_computed_task,
            provider_private_key=self.PROVIDER_PRIVATE_KEY
        )

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
                data=self.serialized_force_report_computed_task,
                content_type='application/octet-stream',
            )

        self.assertEqual(response.status_code,        202)
        self.assertEqual(len(response.content),       0)

        self._test_subtask_state(
            task_id                  = '1',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.FORCING_REPORT,
            provider_key             = b64encode(self.PROVIDER_PUBLIC_KEY).decode('ascii'),
            requestor_key            = b64encode(self.REQUESTOR_PUBLIC_KEY).decode('ascii'),
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
            client_public_key                  = self._get_encoded_key(self.REQUESTOR_PUBLIC_KEY),
            expected_pending_responses_receive = [
                PendingResponse.ResponseType.ForceReportComputedTask,
            ]
        )

        # STEP 2: Concent do not forces computed task report on the requestor with different or mixed key

        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = self._create_diff_requestor_auth_message(),
                content_type                   = 'application/octet-stream',
            )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(len(response.content),       0)

        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = self._create_provider_auth_message(),
                content_type                   = 'application/octet-stream',
            )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(len(response.content),       0)

        # STEP 3: Concent forces computed task report on the requestor with correct key

        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = self._create_requestor_auth_message(),
                content_type                   = 'application/octet-stream',
            )

        force_report_computed_task_from_view = load(
            response.content,
            self.REQUESTOR_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY,
            check_time = False,
        )

        self.assertEqual(response.status_code,                                                                  200)
        self.assertEqual(force_report_computed_task_from_view.timestamp, parse_iso_date_to_timestamp("2017-12-01 11:00:05"))
        self.assertEqual(force_report_computed_task_from_view.report_computed_task.task_to_compute.timestamp,   self.force_report_computed_task.report_computed_task.task_to_compute.timestamp)     # pylint: disable=no-member
        self.assertEqual(force_report_computed_task_from_view.report_computed_task.task_to_compute,             self.force_report_computed_task.report_computed_task.task_to_compute)               # pylint: disable=no-member

        # STEP 4:
        # 4.1. TaskToCompute is send signed with different key, request is rejected with proper error message.
        # 4.2. TaskToCompute is send with different requestor public key, request is rejected with proper error message.
        # 4.3. TaskToCompute is send with different data, request is rejected with proper error message.

        # 4.1.
        self.deserialized_task_to_compute.sig = None
        task_to_compute = self._sign_message(
            self.deserialized_task_to_compute,
            self.DIFFERENT_REQUESTOR_PRIVATE_KEY,
        )

        with freeze_time("2017-12-01 11:00:05"):
            ack_report_computed_task = message.AckReportComputedTask(
                report_computed_task=self._get_deserialized_report_computed_task(
                    task_to_compute=self.deserialized_task_to_compute,
                )
            )
        serialized_ack_report_computed_task = dump(ack_report_computed_task, self.REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:send'),
                data                           = serialized_ack_report_computed_task,
                content_type                   = 'application/octet-stream',
            )

        self._test_400_response(
            response,
            error_message='There was an exception when validating if golem_message {} is signed with public key {}'.format(
                message.TaskToCompute.__name__,
                self.REQUESTOR_PUBLIC_KEY,
            ),
            error_code=ErrorCode.MESSAGE_SIGNATURE_WRONG,
        )

        # 4.2.
        task_to_compute.sig = None
        task_to_compute.requestor_public_key = self._get_diffrent_requestor_hex_public_key()
        task_to_compute = self._sign_message(
            task_to_compute,
            self.REQUESTOR_PRIVATE_KEY,
        )

        with freeze_time("2017-12-01 11:00:05"):
            ack_report_computed_task = message.AckReportComputedTask(
                report_computed_task=self._get_deserialized_report_computed_task(
                    task_to_compute=task_to_compute,
                )
            )
        serialized_ack_report_computed_task = dump(ack_report_computed_task, self.REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:send'),
                data                           = serialized_ack_report_computed_task,
                content_type                   = 'application/octet-stream',
            )

        self._test_400_response(
            response,
            error_message='There was an exception when validating if golem_message {} is signed with public key {}'.format(
                message.TaskToCompute.__name__,
                self.DIFFERENT_REQUESTOR_PUBLIC_KEY,
            ),
            error_code=ErrorCode.MESSAGE_SIGNATURE_WRONG,
        )

        # 4.3.
        task_to_compute.sig = None
        task_to_compute.requestor_public_key = self._get_requestor_hex_public_key()
        task_to_compute.provider_id = 'different_id'
        task_to_compute = self._sign_message(
            task_to_compute,
            self.REQUESTOR_PRIVATE_KEY,
        )

        report_computed_task_from_provider = self._get_deserialized_report_computed_task(
            timestamp="2017-12-01 10:55:00",
            task_to_compute=task_to_compute,
        )
        with freeze_time("2017-12-01 11:00:05"):
            ack_report_computed_task = message.AckReportComputedTask(
                report_computed_task=report_computed_task_from_provider,
            )
        serialized_ack_report_computed_task = dump(ack_report_computed_task, self.REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:send'),
                data                           = serialized_ack_report_computed_task,
                content_type                   = 'application/octet-stream',
            )

        self._test_400_response(
            response,
            error_message = 'TaskToCompute messages are not identical. '
                'There is a difference between messages with index 0 on passed list and with index {}'
                'The difference is on field {}: {} is not equal {}'.format(
                    1,
                    'provider_id',
                    'different_id',
                    self.deserialized_task_to_compute.provider_id
                ),
            error_code=ErrorCode.MESSAGES_NOT_IDENTICAL,
        )

        # STEP 5: Requestor accepts computed task via Concent with correct key
        self.deserialized_task_to_compute.sig = None
        self.deserialized_task_to_compute = self._sign_message(
            self.deserialized_task_to_compute,
            self.REQUESTOR_PRIVATE_KEY,
        )

        report_computed_task_from_provider = self._get_deserialized_report_computed_task(
            timestamp="2017-12-01 10:55:00",
            task_to_compute=self.deserialized_task_to_compute,
        )
        with freeze_time("2017-12-01 11:00:05"):
            ack_report_computed_task = message.AckReportComputedTask(
                report_computed_task=report_computed_task_from_provider
            )
        serialized_ack_report_computed_task = dump(ack_report_computed_task, self.REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:send'),
                data                           = serialized_ack_report_computed_task,
                content_type                   = 'application/octet-stream',
            )

        self.assertEqual(response.status_code,        202)

        self._test_subtask_state(
            task_id                  = '1',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.REPORTED,
            provider_key             = b64encode(self.PROVIDER_PUBLIC_KEY).decode('ascii'),
            requestor_key            = b64encode(self.REQUESTOR_PUBLIC_KEY).decode('ascii'),
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
            client_public_key                  = self._get_encoded_key(self.PROVIDER_PUBLIC_KEY),
            expected_pending_responses_receive = [
                PendingResponse.ResponseType.ForceReportComputedTaskResponse,
            ]
        )

        # STEP 6: Concent do not passes computed task acceptance to the provider with different or mixed key

        with freeze_time("2017-12-01 11:00:15"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = self._create_diff_provider_auth_message(),
                content_type                   = 'application/octet-stream',
            )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(len(response.content),       0)

        with freeze_time("2017-12-01 11:00:15"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = self._create_requestor_auth_message(),
                content_type                   = 'application/octet-stream',
            )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(len(response.content),       0)

        # STEP 7: Concent passes computed task acceptance to the provider with correct key

        with freeze_time("2017-12-01 11:00:15"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = self._create_provider_auth_message(),
                content_type                   = 'application/octet-stream',
            )

        ack_report_computed_task_from_view = load(
            response.content,
            self.PROVIDER_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY,
            check_time = False,
        )

        self.assertEqual(response.status_code,                         200)
        self.assertEqual(ack_report_computed_task_from_view.timestamp, parse_iso_date_to_timestamp("2017-12-01 11:00:15"))

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

        with freeze_time("2017-12-01 10:59:00"):
            response = self.client.post(
                reverse('core:send'),
                data=self.serialized_force_report_computed_task,
                content_type='application/octet-stream',
            )

        self.assertEqual(response.status_code,        202)
        self.assertEqual(len(response.content),       0)

        self._test_subtask_state(
            task_id                  = '1',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.FORCING_REPORT,
            provider_key             = b64encode(self.PROVIDER_PUBLIC_KEY).decode('ascii'),
            requestor_key            = b64encode(self.REQUESTOR_PUBLIC_KEY).decode('ascii'),
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
            client_public_key                  = self._get_encoded_key(self.REQUESTOR_PUBLIC_KEY),
            expected_pending_responses_receive = [
                PendingResponse.ResponseType.ForceReportComputedTask,
            ]
        )

        # STEP 2: Concent do not forces computed task report on the requestor with different or mixed key

        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = self._create_diff_requestor_auth_message(),
                content_type                   = 'application/octet-stream',
            )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(len(response.content),       0)

        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = self._create_provider_auth_message(),
                content_type                   = 'application/octet-stream',
            )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(len(response.content),       0)

        # STEP 3: Concent forces computed task report on the requestor with correct key

        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = self._create_requestor_auth_message(),
                content_type                   = 'application/octet-stream',
            )

        force_report_computed_task_from_view = load(
            response.content,
            self.REQUESTOR_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY,
            check_time = False,
        )

        self.assertEqual(response.status_code,                                                                  200)
        self.assertEqual(force_report_computed_task_from_view.timestamp, parse_iso_date_to_timestamp("2017-12-01 11:00:05"))
        self.assertEqual(force_report_computed_task_from_view.report_computed_task.task_to_compute.timestamp,   self.force_report_computed_task.report_computed_task.task_to_compute.timestamp)  # pylint: disable=no-member
        self.assertEqual(force_report_computed_task_from_view.report_computed_task.task_to_compute,             self.force_report_computed_task.report_computed_task.task_to_compute)            # pylint: disable=no-member

        # STEP 4:
        # 4.1. TaskToCompute is send signed with different key, request is rejected with proper error message.
        # 4.2. TaskToCompute is send with different requestor public key, request is rejected with proper error message.
        # 4.3. TaskToCompute is send with different data, request is rejected with proper error message.

        # 4.1.
        self.deserialized_task_to_compute.sig = None
        task_to_compute = self._sign_message(
            self.deserialized_task_to_compute,
            self.DIFFERENT_REQUESTOR_PRIVATE_KEY,
        )

        with freeze_time("2017-12-01 11:00:05"):
            reject_report_computed_task = message.RejectReportComputedTask(
                reason=message.RejectReportComputedTask.REASON.SubtaskTimeLimitExceeded,
                attached_task_to_compute=task_to_compute,
            )

        serialized_reject_report_computed_task = dump(reject_report_computed_task, self.REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:send'),
                data                           = serialized_reject_report_computed_task,
                content_type                   = 'application/octet-stream',
            )

        self._test_400_response(
            response,
            error_message='There was an exception when validating if golem_message {} is signed with public key {}'.format(
                message.TaskToCompute.__name__,
                self.REQUESTOR_PUBLIC_KEY,
            ),
            error_code=ErrorCode.MESSAGE_SIGNATURE_WRONG,
        )

        # 4.2.
        task_to_compute.sig = None
        task_to_compute.requestor_public_key = self._get_diffrent_requestor_hex_public_key()
        task_to_compute = self._sign_message(
            task_to_compute,
            self.DIFFERENT_REQUESTOR_PRIVATE_KEY,
        )

        with freeze_time("2017-12-01 11:00:05"):
            reject_report_computed_task = message.RejectReportComputedTask(
                reason=message.RejectReportComputedTask.REASON.SubtaskTimeLimitExceeded,
                attached_task_to_compute=task_to_compute,
            )
        serialized_reject_report_computed_task = dump(reject_report_computed_task, self.REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:send'),
                data                           = serialized_reject_report_computed_task,
                content_type                   = 'application/octet-stream',
            )

        self._test_400_response(
            response,
            error_message = "Subtask requestor key does not match current client key. Can't accept your 'RejectReportComputedTask'.",
            error_code=ErrorCode.QUEUE_REQUESTOR_PUBLIC_KEY_MISMATCH,
        )

        # 4.3.
        task_to_compute.sig = None
        task_to_compute.requestor_public_key = self._get_requestor_hex_public_key()
        task_to_compute.provider_id = 'different_id'
        task_to_compute = self._sign_message(
            task_to_compute,
            self.REQUESTOR_PRIVATE_KEY,
        )

        with freeze_time("2017-12-01 11:00:05"):
            reject_report_computed_task = message.RejectReportComputedTask(
                reason=message.RejectReportComputedTask.REASON.SubtaskTimeLimitExceeded,
                attached_task_to_compute=task_to_compute,
            )
        serialized_reject_report_computed_task = dump(reject_report_computed_task, self.REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:send'),
                data                           = serialized_reject_report_computed_task,
                content_type                   = 'application/octet-stream',
            )

        self._test_400_response(
            response,
            error_message = 'TaskToCompute messages are not identical. '
                'There is a difference between messages with index 0 on passed list and with index {}'
                'The difference is on field {}: {} is not equal {}'.format(
                    1,
                    'provider_id',
                    'different_id',
                    self.deserialized_task_to_compute.provider_id
                ),
            error_code=ErrorCode.MESSAGES_NOT_IDENTICAL,
        )

        self._test_subtask_state(
            task_id                  = '1',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.FORCING_REPORT,
            provider_key             = b64encode(self.PROVIDER_PUBLIC_KEY).decode('ascii'),
            requestor_key            = b64encode(self.REQUESTOR_PUBLIC_KEY).decode('ascii'),
            expected_nested_messages = {'task_to_compute', 'report_computed_task'},
            next_deadline=parse_iso_date_to_timestamp("2017-12-01 11:00:10"),
        )

        # STEP 5: Requestor rejects computed task due to CannotComputeTask or TaskFailure with correct key
        self.deserialized_task_to_compute.sig = None
        self.deserialized_task_to_compute = self._sign_message(
            self.deserialized_task_to_compute,
            self.REQUESTOR_PRIVATE_KEY,
        )

        with freeze_time("2017-12-01 10:00:00"):
            cannot_compute_task = message.CannotComputeTask()
        cannot_compute_task.task_to_compute = self.deserialized_task_to_compute
        cannot_compute_task.reason = message.CannotComputeTask.REASON.WrongKey

        serialized_cannot_compute_task   = dump(cannot_compute_task,            self.PROVIDER_PRIVATE_KEY,  self.REQUESTOR_PUBLIC_KEY)
        deserialized_cannot_compute_task = load(serialized_cannot_compute_task, self.REQUESTOR_PRIVATE_KEY, self.PROVIDER_PUBLIC_KEY, check_time = False)

        with freeze_time("2017-12-01 11:00:05"):
            reject_report_computed_task = message.RejectReportComputedTask(
                cannot_compute_task = deserialized_cannot_compute_task,
                reason              = message.RejectReportComputedTask.REASON.GotMessageCannotComputeTask,
                attached_task_to_compute=self.deserialized_task_to_compute,
            )
        serialized_reject_report_computed_task = dump(reject_report_computed_task, self.REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:send'),
                data                           = serialized_reject_report_computed_task,
                content_type                   = 'application/octet-stream',
            )

        self.assertEqual(response.status_code,        202)
        self.assertEqual(len(response.content),       0)

        self._test_subtask_state(
            task_id                  = '1',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.FAILED,
            provider_key             = b64encode(self.PROVIDER_PUBLIC_KEY).decode('ascii'),
            requestor_key            = b64encode(self.REQUESTOR_PUBLIC_KEY).decode('ascii'),
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
            client_public_key                  = self._get_encoded_key(self.PROVIDER_PUBLIC_KEY),
            expected_pending_responses_receive = [
                PendingResponse.ResponseType.ForceReportComputedTaskResponse,
            ]
        )

        # STEP 6: Concent do not passes computed task rejection to the provider with different or mixed key

        with freeze_time("2017-12-01 11:00:15"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = self._create_diff_provider_auth_message(),
                content_type                   = 'application/octet-stream',
            )

        self.assertEqual(response.status_code,        204)

        with freeze_time("2017-12-01 11:00:15"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = self._create_requestor_auth_message(),
                content_type                   = 'application/octet-stream',
            )

        self.assertEqual(response.status_code, 204)

        # STEP 7: Concent passes computed task rejection to the provider with correct key

        with freeze_time("2017-12-01 11:00:15"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = self._create_provider_auth_message(),
                content_type                   = 'application/octet-stream',
            )

        force_report_computed_task_response = load(
            response.content,
            self.PROVIDER_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY,
            check_time = False,
        )

        self.assertEqual(response.status_code,                                                                                          200)
        self.assertEqual(force_report_computed_task_response.timestamp, parse_iso_date_to_timestamp("2017-12-01 11:00:15"))
        self.assertEqual(force_report_computed_task_response.reject_report_computed_task.timestamp, parse_iso_date_to_timestamp("2017-12-01 11:00:05"))
        self.assertEqual(force_report_computed_task_response.reject_report_computed_task.cannot_compute_task.timestamp,                 reject_report_computed_task.cannot_compute_task.timestamp)  # pylint: disable=no-member
        self.assertEqual(force_report_computed_task_response.reject_report_computed_task.cannot_compute_task.task_to_compute.timestamp, reject_report_computed_task.cannot_compute_task.task_to_compute.timestamp)  # pylint: disable=no-member

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

        with freeze_time("2017-12-01 10:59:00"):
            response = self.client.post(
                reverse('core:send'),
                data=self.serialized_force_report_computed_task,
                content_type='application/octet-stream',
            )

        self.assertEqual(response.status_code,        202)
        self.assertEqual(len(response.content),       0)

        self._test_subtask_state(
            task_id                  = '1',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.FORCING_REPORT,
            provider_key             = b64encode(self.PROVIDER_PUBLIC_KEY).decode('ascii'),
            requestor_key            = b64encode(self.REQUESTOR_PUBLIC_KEY).decode('ascii'),
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
            client_public_key                  = self._get_encoded_key(self.REQUESTOR_PUBLIC_KEY),
            expected_pending_responses_receive = [
                PendingResponse.ResponseType.ForceReportComputedTask,
            ]
        )

        # STEP 2: Concent do not forces computed task report on the requestor with different or mixed key

        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = self._create_diff_requestor_auth_message(),
                content_type                   = 'application/octet-stream',
            )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(len(response.content),       0)

        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = self._create_provider_auth_message(),
                content_type                   = 'application/octet-stream',
            )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(len(response.content),       0)

        # STEP 3: Concent forces computed task report on the requestor with correct key

        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = self._create_requestor_auth_message(),
                content_type                   = 'application/octet-stream',
            )

        force_report_computed_task_from_view = load(
            response.content,
            self.REQUESTOR_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY,
            check_time = False,
        )

        self.assertEqual(response.status_code,                                                                  200)
        self.assertEqual(force_report_computed_task_from_view.timestamp, parse_iso_date_to_timestamp("2017-12-01 11:00:05"))
        self.assertEqual(force_report_computed_task_from_view.report_computed_task.task_to_compute.timestamp,   self.force_report_computed_task.report_computed_task.task_to_compute.timestamp)  # pylint: disable=no-member
        self.assertEqual(force_report_computed_task_from_view.report_computed_task.task_to_compute,             self.force_report_computed_task.report_computed_task.task_to_compute)            # pylint: disable=no-member

        # STEP 4:
        # 4.1. TaskToCompute is send signed with different key, request is rejected with proper error message.
        # 4.2. TaskToCompute is send with different requestor public key, request is rejected with proper error message.
        # 4.3. TaskToCompute is send with different data, request is rejected with proper error message.

        # 4.1.
        self.deserialized_task_to_compute.sig = None
        task_to_compute = self._sign_message(
            self.deserialized_task_to_compute,
            self.DIFFERENT_REQUESTOR_PRIVATE_KEY,
        )

        with freeze_time("2017-12-01 11:00:05"):
            reject_report_computed_task = message.RejectReportComputedTask(
                reason=message.RejectReportComputedTask.REASON.SubtaskTimeLimitExceeded,
                attached_task_to_compute=task_to_compute,
            )
        serialized_reject_report_computed_task = dump(reject_report_computed_task, self.REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:send'),
                data                           = serialized_reject_report_computed_task,
                content_type                   = 'application/octet-stream',
            )

        self._test_400_response(
            response,
            error_message='There was an exception when validating if golem_message {} is signed with public key {}'.format(
                message.TaskToCompute.__name__,
                self.REQUESTOR_PUBLIC_KEY,
            ),
            error_code=ErrorCode.MESSAGE_SIGNATURE_WRONG,
        )

        # 4.2.
        task_to_compute.sig = None
        task_to_compute.requestor_public_key = self._get_diffrent_requestor_hex_public_key()
        task_to_compute = self._sign_message(
            task_to_compute,
            self.DIFFERENT_REQUESTOR_PRIVATE_KEY,
        )

        with freeze_time("2017-12-01 11:00:05"):
            reject_report_computed_task = message.RejectReportComputedTask(
                reason=message.RejectReportComputedTask.REASON.SubtaskTimeLimitExceeded,
                attached_task_to_compute=task_to_compute,
            )
        serialized_reject_report_computed_task = dump(reject_report_computed_task, self.REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:send'),
                data                           = serialized_reject_report_computed_task,
                content_type                   = 'application/octet-stream',
            )

        self._test_400_response(
            response,
            error_message = "Subtask requestor key does not match current client key. Can't accept your 'RejectReportComputedTask'.",
            error_code=ErrorCode.QUEUE_REQUESTOR_PUBLIC_KEY_MISMATCH,
        )

        # 4.3.
        task_to_compute.sig = None
        task_to_compute.requestor_public_key = self._get_requestor_hex_public_key()
        task_to_compute.provider_id = 'different_id'
        task_to_compute = self._sign_message(
            task_to_compute,
            self.REQUESTOR_PRIVATE_KEY,
        )

        with freeze_time("2017-12-01 11:00:05"):
            reject_report_computed_task = message.RejectReportComputedTask(
                reason=message.RejectReportComputedTask.REASON.SubtaskTimeLimitExceeded,
                attached_task_to_compute=task_to_compute,
            )
        serialized_reject_report_computed_task = dump(reject_report_computed_task, self.REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY)
        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:send'),
                data                           = serialized_reject_report_computed_task,
                content_type                   = 'application/octet-stream',
            )

        self._test_400_response(
            response,
            error_message = 'TaskToCompute messages are not identical. '
                'There is a difference between messages with index 0 on passed list and with index {}'
                'The difference is on field {}: {} is not equal {}'.format(
                    1,
                    'provider_id',
                    'different_id',
                    self.deserialized_task_to_compute.provider_id
                ),
            error_code=ErrorCode.MESSAGES_NOT_IDENTICAL,
        )

        self._test_subtask_state(
            task_id                  = '1',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.FORCING_REPORT,
            provider_key             = b64encode(self.PROVIDER_PUBLIC_KEY).decode('ascii'),
            requestor_key            = b64encode(self.REQUESTOR_PUBLIC_KEY).decode('ascii'),
            expected_nested_messages = {'task_to_compute', 'report_computed_task'},
            next_deadline=parse_iso_date_to_timestamp("2017-12-01 11:00:10"),
        )

        # STEP 5: Requestor rejects computed task due to CannotComputeTask or TaskFailure with correct key
        self.deserialized_task_to_compute.sig = None
        self.deserialized_task_to_compute = self._sign_message(
            self.deserialized_task_to_compute,
            self.REQUESTOR_PRIVATE_KEY,
        )

        with freeze_time("2017-12-01 11:00:05"):
            reject_report_computed_task = message.RejectReportComputedTask(
                reason=message.RejectReportComputedTask.REASON.SubtaskTimeLimitExceeded,
                attached_task_to_compute=self.deserialized_task_to_compute,
            )
        serialized_reject_report_computed_task = dump(reject_report_computed_task, self.REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY)

        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:send'),
                data                           = serialized_reject_report_computed_task,
                content_type                   = 'application/octet-stream',
            )

        self.assertEqual(response.status_code,        202)
        self.assertEqual(len(response.content),       0)

        self._test_subtask_state(
            task_id                  = '1',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.REPORTED,
            provider_key             = b64encode(self.PROVIDER_PUBLIC_KEY).decode('ascii'),
            requestor_key            = b64encode(self.REQUESTOR_PUBLIC_KEY).decode('ascii'),
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
            subtask_id                          = '8',
            client_public_key                   = self._get_encoded_key(self.PROVIDER_PUBLIC_KEY),
            client_public_key_out_of_band       = self._get_encoded_key(self.REQUESTOR_PUBLIC_KEY),
            expected_pending_responses_receive = [
                PendingResponse.ResponseType.ForceReportComputedTaskResponse,
            ],
            expected_pending_responses_receive_out_of_band = [
                PendingResponse.ResponseType.VerdictReportComputedTask,
            ]
        )

        # STEP 6: Concent do not overrides computed task rejection and sends acceptance message to the provider with different or mixed key

        with freeze_time("2017-12-01 11:00:15"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = self._create_diff_provider_auth_message(),
                content_type                   = 'application/octet-stream',
            )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(len(response.content),       0)

        with freeze_time("2017-12-01 11:00:15"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = self._create_requestor_auth_message(),
                content_type                   = 'application/octet-stream',
            )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(len(response.content),       0)

        # STEP 7: Concent overrides computed task rejection and sends acceptance message to the provider with correct key

        with freeze_time("2017-12-01 11:00:15"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = self._create_provider_auth_message(),
                content_type                   = 'application/octet-stream',
            )

        self.assertEqual(response.status_code,        200)

        serialized_message_from_concent_to_provider = response.content
        message_from_concent_to_provider            = load(
            serialized_message_from_concent_to_provider,
            self.PROVIDER_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY,
            check_time = False
        )

        self.assertIsInstance(message_from_concent_to_provider,                                     message.concents.ForceReportComputedTaskResponse)
        self.assertEqual(message_from_concent_to_provider.timestamp, parse_iso_date_to_timestamp("2017-12-01 11:00:15"))
        self.assertEqual(message_from_concent_to_provider.ack_report_computed_task.report_computed_task.task_to_compute, self.deserialized_task_to_compute)

        # STEP 8: Requestor do not receives computed task report verdict out of band due to an overridden decision with different or mixed key

        with freeze_time("2017-12-01 11:00:15"):
            response = self.client.post(
                reverse('core:receive_out_of_band'),
                data                           = self._create_diff_requestor_auth_message(),
                content_type                   = 'application/octet-stream',
            )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(len(response.content),       0)

        with freeze_time("2017-12-01 11:00:15"):
            response = self.client.post(
                reverse('core:receive_out_of_band'),
                data                           = self._create_provider_auth_message(),
                content_type                   = 'application/octet-stream',
            )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(len(response.content),       0)

        # STEP 9: Requestor receives computed task report verdict out of band due to an overridden decision with correct key

        with freeze_time("2017-12-01 11:00:15"):
            response = self.client.post(
                reverse('core:receive_out_of_band'),
                data                           = self._create_requestor_auth_message(),
                content_type                   = 'application/octet-stream',
            )

        self.assertEqual(response.status_code,        200)

        message_from_concent_to_requestor = load(response.content, self.REQUESTOR_PRIVATE_KEY, CONCENT_PUBLIC_KEY, check_time = False)

        self.assertIsInstance(message_from_concent_to_requestor,                                message.VerdictReportComputedTask)
        self.assertGreaterEqual(message_from_concent_to_requestor.timestamp,                    int(dateutil.parser.parse("2017-12-01 11:00:05").timestamp()))
        self.assertLessEqual(   message_from_concent_to_requestor.timestamp,                    int(dateutil.parser.parse("2017-12-01 11:00:15").timestamp()))
        self.assertEqual(message_from_concent_to_requestor.ack_report_computed_task.subtask_id, message_from_concent_to_provider.ack_report_computed_task.subtask_id)

        self._test_subtask_state(
            task_id                  = '1',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.REPORTED,
            provider_key             = b64encode(self.PROVIDER_PUBLIC_KEY).decode('ascii'),
            requestor_key            = b64encode(self.REQUESTOR_PUBLIC_KEY).decode('ascii'),
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
                data=self.serialized_force_report_computed_task,
                content_type='application/octet-stream',
            )

        self.assertEqual(response.status_code,        202)
        self.assertEqual(len(response.content),       0)

        self._test_subtask_state(
            task_id                  = '1',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.FORCING_REPORT,
            provider_key             = b64encode(self.PROVIDER_PUBLIC_KEY).decode('ascii'),
            requestor_key            = b64encode(self.REQUESTOR_PUBLIC_KEY).decode('ascii'),
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
            client_public_key                  = self._get_encoded_key(self.REQUESTOR_PUBLIC_KEY),
            expected_pending_responses_receive = [
                PendingResponse.ResponseType.ForceReportComputedTask,
            ]
        )

        # STEP 2: Concent do not forces computed task report on the requestor with different or mixed key

        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = self._create_diff_requestor_auth_message(),
                content_type                   = 'application/octet-stream',
            )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(len(response.content),       0)

        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = self._create_provider_auth_message(),
                content_type                   = 'application/octet-stream',
            )

        self.assertEqual(response.status_code,        204)
        self.assertEqual(len(response.content),       0)

        # STEP 3: Concent forces computed task report on the requestor with correct key

        with freeze_time("2017-12-01 11:00:05"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = self._create_requestor_auth_message(),
                content_type                   = 'application/octet-stream',
            )

        force_report_computed_task_from_view = load(
            response.content,
            self.REQUESTOR_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY,
            check_time = False,
        )

        self.assertEqual(response.status_code,                                                                  200)
        self.assertEqual(force_report_computed_task_from_view.timestamp, parse_iso_date_to_timestamp("2017-12-01 11:00:05"))
        self.assertEqual(force_report_computed_task_from_view.report_computed_task.task_to_compute.timestamp,   self.force_report_computed_task.report_computed_task.task_to_compute.timestamp)     # pylint: disable=no-member
        self.assertEqual(force_report_computed_task_from_view.report_computed_task.task_to_compute,             self.force_report_computed_task.report_computed_task.task_to_compute)               # pylint: disable=no-member

        # STEP 4: Concent do not accepts computed task due to lack of response from the requestor with different or mixed key

        with freeze_time("2017-12-01 11:00:15"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = self._create_diff_requestor_auth_message(),
                content_type                   = 'application/octet-stream',
            )

        self.assertEqual(response.status_code,        204)

        with freeze_time("2017-12-01 11:00:15"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = self._create_requestor_auth_message(),
                content_type                   = 'application/octet-stream',
            )

        self.assertEqual(response.status_code,        204)

        # STEP 5: Concent accepts computed task due to lack of response from the requestor with correct key

        with freeze_time("2017-12-01 11:00:15"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = self._create_provider_auth_message(),
                content_type                   = 'application/octet-stream',
            )

        self.assertEqual(response.status_code,        200)

        message_from_concent_to_provider = load(response.content, self.PROVIDER_PRIVATE_KEY, CONCENT_PUBLIC_KEY, check_time=False)
        self.assertIsInstance(message_from_concent_to_provider,                                     message.concents.ForceReportComputedTaskResponse)
        self.assertEqual(message_from_concent_to_provider.timestamp,                                int(dateutil.parser.parse("2017-12-01 11:00:15").timestamp()))
        self.assertEqual(message_from_concent_to_provider.ack_report_computed_task.report_computed_task.task_to_compute, self.deserialized_task_to_compute)

        self._test_subtask_state(
            task_id                  = '1',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.REPORTED,
            provider_key             = b64encode(self.PROVIDER_PUBLIC_KEY).decode('ascii'),
            requestor_key            = b64encode(self.REQUESTOR_PUBLIC_KEY).decode('ascii'),
            expected_nested_messages = {'task_to_compute', 'report_computed_task'},
            next_deadline            = None,
        )
        self._test_undelivered_pending_responses(
            subtask_id                         = '8',
            client_public_key                  = self._get_encoded_key(self.PROVIDER_PUBLIC_KEY),
            client_public_key_out_of_band      = self._get_encoded_key(self.REQUESTOR_PUBLIC_KEY),
            expected_pending_responses_receive_out_of_band = [
                PendingResponse.ResponseType.VerdictReportComputedTask,
            ]
        )
        # STEP 6: Requestor do not receives task computation report verdict out of band due to lack of response with different or mixed key

        with freeze_time("2017-12-01 11:00:15"):
            response = self.client.post(
                reverse('core:receive_out_of_band'),
                data                           = self._create_diff_requestor_auth_message(),
                content_type                   = 'application/octet-stream',
            )

        self.assertEqual(response.status_code,        204)

        with freeze_time("2017-12-01 11:00:15"):
            response = self.client.post(
                reverse('core:receive_out_of_band'),
                data                           = self._create_provider_auth_message(),
                content_type                   = 'application/octet-stream',
            )

        self.assertEqual(response.status_code,        204)

        # STEP 7: Requestor receives task computation report verdict out of band due to lack of response with correct key

        with freeze_time("2017-12-01 11:00:15"):
            response = self.client.post(
                reverse('core:receive_out_of_band'),
                data                           = self._create_requestor_auth_message(),
                content_type                   = 'application/octet-stream',
            )

        self.assertEqual(response.status_code,        200)

        message_from_concent_to_requestor = load(
            response.content,
            self.REQUESTOR_PRIVATE_KEY,
            CONCENT_PUBLIC_KEY,
            check_time = False
        )

        self.assertIsInstance(message_from_concent_to_requestor,                                message.VerdictReportComputedTask)
        self.assertGreaterEqual(message_from_concent_to_requestor.timestamp,                    int(dateutil.parser.parse("2017-12-01 11:00:05").timestamp()))
        self.assertLessEqual(message_from_concent_to_requestor.timestamp,                       int(dateutil.parser.parse("2017-12-01 11:00:15").timestamp()))
        self.assertEqual(message_from_concent_to_requestor.ack_report_computed_task.subtask_id, message_from_concent_to_provider.ack_report_computed_task.subtask_id)

        self._test_subtask_state(
            task_id                  = '1',
            subtask_id               = '8',
            subtask_state            = Subtask.SubtaskState.REPORTED,
            provider_key             = b64encode(self.PROVIDER_PUBLIC_KEY).decode('ascii'),
            requestor_key            = b64encode(self.REQUESTOR_PUBLIC_KEY).decode('ascii'),
            expected_nested_messages = {'task_to_compute', 'report_computed_task'},
            next_deadline            = None,
        )
        self._assert_client_count_is_equal(2)
