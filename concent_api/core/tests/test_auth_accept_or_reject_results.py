import mock

from django.test            import override_settings
from django.urls            import reverse
from freezegun              import freeze_time
from golem_messages         import message

from core.constants         import ETHEREUM_ADDRESS_LENGTH
from core.models            import Subtask
from core.models            import PendingResponse
from core.tests.utils import ConcentIntegrationTestCase
from core.tests.utils import parse_iso_date_to_timestamp
from common.constants        import ErrorCode
from common.testing_helpers  import generate_ecc_key_pair


(CONCENT_PRIVATE_KEY, CONCENT_PUBLIC_KEY) = generate_ecc_key_pair()


@override_settings(
    CONCENT_PRIVATE_KEY       = CONCENT_PRIVATE_KEY,
    CONCENT_PUBLIC_KEY        = CONCENT_PUBLIC_KEY,
    CONCENT_MESSAGING_TIME    = 10,  # seconds
    FORCE_ACCEPTANCE_TIME     = 10,  # seconds
    CONCENT_ETHEREUM_ADDRESS  = 'x' * ETHEREUM_ADDRESS_LENGTH
)
class AuthAcceptOrRejectIntegrationTest(ConcentIntegrationTestCase):

    def setUp(self):
        super().setUp()
        self.patcher = mock.patch('core.message_handlers.calculate_subtask_verification_time', return_value=10)
        self.addCleanup(self.patcher.stop)
        self.patcher.start()

    def test_provider_forces_subtask_results_for_task_which_was_already_submitted_concent_should_refuse_with_correct_keys(self):
        """
        Tests if on provider ForceSubtaskResults message Concent will return ServiceRefused
        if ForceSubtaskResults with same task_id was already submitted but different provider can submit.

        Expected message exchange:
        Provider            -> Concent:    ForceSubtaskResults
        Concent             -> Provider:   HTTP 202
        Different Provider  -> Concent:    ForceSubtaskResults
        Concent             -> Provider:   HTTP 202
        Provider            -> Concent:    ForceSubtaskResults
        Concent             -> Provider:   ServiceRefused
        """

        task_to_compute = self._get_deserialized_task_to_compute(
            timestamp   = "2018-02-05 10:00:00",
            deadline    = "2018-02-05 10:00:15",
            task_id     = "2",
            subtask_id  = "xxyyzz",
        )

        # STEP 1: Provider forces subtask results via Concent.
        # Request is processed correctly.
        serialized_force_subtask_results = self._get_serialized_force_subtask_results(
            timestamp="2018-02-05 10:00:30",
            ack_report_computed_task=self._get_deserialized_ack_report_computed_task(
                timestamp="2018-02-05 10:00:20",
                subtask_id="xxyyzz",
                task_to_compute=task_to_compute,
                signer_private_key=self.REQUESTOR_PRIVATE_KEY,
            )
        )

        with mock.patch(
            'core.message_handlers.payments_service.is_account_status_positive',
            side_effect=self.is_account_status_positive_true_mock
        ) as is_account_status_positive_true_mock_function:
            with freeze_time("2018-02-05 10:00:30"):
                response = self.client.post(
                    reverse('core:send'),
                    data                                = serialized_force_subtask_results,
                    content_type                        = 'application/octet-stream',
                )

        is_account_status_positive_true_mock_function.assert_called_with(
            client_eth_address=task_to_compute.requestor_ethereum_address,
            pending_value=task_to_compute.price,
        )

        assert len(response.content)  == 0
        assert response.status_code   == 202

        self._assert_stored_message_counter_increased(increased_by=3)
        self._test_subtask_state(
            task_id                      = '2',
            subtask_id                   = 'xxyyzz',
            subtask_state                = Subtask.SubtaskState.FORCING_ACCEPTANCE,
            provider_key                 = self._get_encoded_provider_public_key(),
            requestor_key                = self._get_encoded_requestor_public_key(),
            expected_nested_messages     = {'task_to_compute', 'report_computed_task', 'ack_report_computed_task'},
            next_deadline                = parse_iso_date_to_timestamp("2018-02-05 10:00:45"),
        )
        self._test_last_stored_messages(
            expected_messages = [
                message.TaskToCompute,
                message.ReportComputedTask,
                message.AckReportComputedTask,
            ],
            task_id         = '2',
            subtask_id      = 'xxyyzz',
        )
        self._test_undelivered_pending_responses(
            subtask_id                         = 'xxyyzz',
            client_public_key                  = self._get_encoded_requestor_public_key(),
            expected_pending_responses_receive = [
                PendingResponse.ResponseType.ForceSubtaskResults,
            ]
        )

        # STEP 2: Different provider forces subtask results via Concent with message with the same task_id with different keys.
        # Request is refused because same subtask_id is used.
        different_serialized_force_subtask_results = self._get_serialized_force_subtask_results(
            timestamp                = "2018-02-05 10:00:15",
            ack_report_computed_task = self._get_deserialized_ack_report_computed_task(
                timestamp       = "2018-02-05 10:00:15",
                subtask_id      = "xxyyzz",
                report_computed_task=self._get_deserialized_report_computed_task(
                    task_to_compute=self._get_deserialized_task_to_compute(
                        timestamp="2018-02-05 10:00:00",
                        deadline="2018-02-05 10:00:10",
                        task_id="2",
                        subtask_id="xxyyzz",
                        provider_public_key=self._get_diffrent_provider_hex_public_key(),
                        requestor_public_key=self._get_diffrent_requestor_hex_public_key(),
                        signer_private_key=self.DIFFERENT_REQUESTOR_PRIVATE_KEY,
                    ),
                    signer_private_key=self.DIFFERENT_PROVIDER_PRIVATE_KEY,
                ),
                signer_private_key=self.DIFFERENT_REQUESTOR_PRIVATE_KEY,
                task_to_compute=task_to_compute
            ),
            provider_private_key = self.DIFFERENT_PROVIDER_PRIVATE_KEY,
        )

        with freeze_time("2018-02-05 10:00:31"):
            response = self.client.post(
                reverse('core:send'),
                data                                = different_serialized_force_subtask_results,
                content_type                        = 'application/octet-stream',
            )

        self._test_response(
            response,
            status=200,
            key=self.DIFFERENT_PROVIDER_PRIVATE_KEY,
            message_type=message.concents.ServiceRefused,
            fields={
                'reason': message.concents.ServiceRefused.REASON.DuplicateRequest,
                'timestamp': parse_iso_date_to_timestamp("2018-02-05 10:00:31"),
            }
        )

        self._assert_stored_message_counter_not_increased()

        # STEP 3: Provider again forces subtask results via Concent with message with the same task_id with correct keys.
        # Request is refused.
        with freeze_time("2018-02-05 10:00:31"):
            response = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_subtask_results,
                content_type                        = 'application/octet-stream',
            )

        self._test_response(
            response,
            status       = 200,
            key          = self.PROVIDER_PRIVATE_KEY,
            message_type = message.concents.ServiceRefused,
            fields       = {
                'reason':    message.concents.ServiceRefused.REASON.DuplicateRequest,
                'timestamp': parse_iso_date_to_timestamp("2018-02-05 10:00:31"),
            }
        )

        self._assert_stored_message_counter_not_increased()

        self._assert_client_count_is_equal(2)

    def test_requestor_should_receive_subtask_results_from_concent_with_correct_keys(self):
        """
        Test if Provider submitted ForceSubtaskResults, Concent will return message to Requestor with new timestamp
        if Requestor ask Concent before deadline if correct keys are used.

        Expected message exchange:
        Provider    -> Concent:                   ForceSubtaskResults
        Concent     -> Provider:                  HTTP 202
        Concent     -> WrongRequestor/Provider:   HTTP 204
        Concent     -> Requestor:                 ForceSubtaskResults (new timestamp)
        """

        compute_task_def = self._get_deserialized_compute_task_def(
            deadline="2018-02-05 10:00:15",
            task_id='2',
            subtask_id='xxyyzz',
        )

        task_to_compute = self._get_deserialized_task_to_compute(
            timestamp="2018-02-05 10:00:00",
            compute_task_def=compute_task_def,
        )

        # STEP 1: Provider forces subtask results via Concent.
        # Request is processed correctly.
        serialized_force_subtask_results = self._get_serialized_force_subtask_results(
            timestamp="2018-02-05 10:00:30",
            ack_report_computed_task=self._get_deserialized_ack_report_computed_task(
                timestamp="2018-02-05 10:00:20",
                subtask_id="xxyyzz",
                task_to_compute=task_to_compute,
                signer_private_key=self.REQUESTOR_PRIVATE_KEY,
            )
        )

        with mock.patch(
            'core.message_handlers.payments_service.is_account_status_positive',
            side_effect=self.is_account_status_positive_true_mock
        ) as is_account_status_positive_true_mock_function:
            with freeze_time("2018-02-05 10:00:31"):
                response = self.client.post(
                    reverse('core:send'),
                    data                                = serialized_force_subtask_results,
                    content_type                        = 'application/octet-stream',
                )

        is_account_status_positive_true_mock_function.assert_called_with(
            client_eth_address=task_to_compute.requestor_ethereum_address,
            pending_value=task_to_compute.price,
        )

        assert len(response.content) == 0
        assert response.status_code  == 202

        self._assert_stored_message_counter_increased(increased_by=3)
        self._test_subtask_state(
            task_id                      = '2',
            subtask_id                   = 'xxyyzz',
            subtask_state                = Subtask.SubtaskState.FORCING_ACCEPTANCE,
            provider_key                 = self._get_encoded_provider_public_key(),
            requestor_key                = self._get_encoded_requestor_public_key(),
            expected_nested_messages={'task_to_compute', 'report_computed_task', 'ack_report_computed_task'},
            next_deadline                = parse_iso_date_to_timestamp("2018-02-05 10:00:45"),
        )
        self._test_last_stored_messages(
            expected_messages = [
                message.TaskToCompute,
                message.ReportComputedTask,
                message.AckReportComputedTask,
            ],
            task_id         = '2',
            subtask_id      = 'xxyyzz',
        )
        self._test_undelivered_pending_responses(
            subtask_id                         = 'xxyyzz',
            client_public_key                  = self._get_encoded_requestor_public_key(),
            expected_pending_responses_receive = [
                PendingResponse.ResponseType.ForceSubtaskResults,
            ]
        )

        # STEP 2: Different requestor or provider does not receive forces subtask results via Concent with different or mixed key.
        with freeze_time("2018-02-05 10:00:29"):
            response = self.client.post(
                reverse('core:receive'),
                data                            = self._create_diff_requestor_auth_message(),
                content_type                    = 'application/octet-stream',
            )

        self._test_204_response(response)
        self._assert_stored_message_counter_not_increased()

        with freeze_time("2018-02-05 10:00:29"):
            response = self.client.post(
                reverse('core:receive'),
                data                            = self._create_provider_auth_message(),
                content_type                    = 'application/octet-stream',
            )

        self._test_204_response(response)
        self._assert_stored_message_counter_not_increased()

        # STEP 3: Requestor receives forces subtask results via Concent with correct key.
        with freeze_time("2018-02-05 10:00:29"):
            response = self.client.post(
                reverse('core:receive'),
                data                            = self._create_requestor_auth_message(),
                content_type                    = 'application/octet-stream',
            )

        self._test_response(
            response,
            status       = 200,
            key          = self.REQUESTOR_PRIVATE_KEY,
            message_type = message.concents.ForceSubtaskResults,
            fields       = {
                'timestamp':                                                    parse_iso_date_to_timestamp("2018-02-05 10:00:29"),
                'ack_report_computed_task.subtask_id':                          'xxyyzz',
                "ack_report_computed_task.report_computed_task.task_to_compute.compute_task_def": compute_task_def,
            }
        )
        self._assert_stored_message_counter_not_increased()
        self._assert_client_count_is_equal(2)

    def test_requestor_sends_subtask_results_accepted_and_concent_should_return_it_to_provider_with_correct_keys(self):
        """
        Test if Requestor wants submit SubtaskResultsAccepted message,
        Provider should receive it from Concent if correct keys are used.

        Exptected message exchange:
        Provider                  -> Concent:                     ForceSubtaskResults
        Concent                   -> Provider:                    HTTP 202
        Concent                   -> WrongRequestor/Provider:     HTTP 204
        Concent                   -> Requestor:                   ForceSubtaskResults
        WrongRequestor/Provider   -> Concent:                     SubtaskResultsAccepted
        Concent                   -> WrongRequestor/Provider:     HTTP 400
        Requestor                 -> Concent:                     SubtaskResultsAccepted
        Concent                   -> Requestor:                   HTTP 202
        Concent                   -> WrongProvider/Requestor:     HTTP 204
        Concent                   -> Provider:                    SubtaskResultsAccepted
        """

        task_to_compute = self._get_deserialized_task_to_compute(
            timestamp   = "2018-02-05 10:00:00",
            deadline    = "2018-02-05 10:00:15",
            task_id     = "2",
            subtask_id  = "xxyyzz",
        )

        # STEP 1: Provider forces subtask results via Concent.
        # Request is processed correctly.
        serialized_force_subtask_results = self._get_serialized_force_subtask_results(
            timestamp                   = "2018-02-05 10:00:30",
            ack_report_computed_task    = self._get_deserialized_ack_report_computed_task(
                timestamp       = "2018-02-05 10:00:20",
                subtask_id      = "xxyyzz",
                task_to_compute = task_to_compute,
                signer_private_key=self.REQUESTOR_PRIVATE_KEY,
            )
        )

        with mock.patch(
            'core.message_handlers.payments_service.is_account_status_positive',
            side_effect=self.is_account_status_positive_true_mock
        ) as is_account_status_positive_true_mock_function:
            with freeze_time("2018-02-05 10:00:30"):
                response = self.client.post(
                    reverse('core:send'),
                    data                                = serialized_force_subtask_results,
                    content_type                        = 'application/octet-stream',
                )

        is_account_status_positive_true_mock_function.assert_called_with(
            client_eth_address=task_to_compute.requestor_ethereum_address,
            pending_value=task_to_compute.price,
        )

        assert len(response.content)  == 0
        assert response.status_code   == 202

        self._assert_stored_message_counter_increased(increased_by=3)
        self._test_subtask_state(
            task_id                      = '2',
            subtask_id                   = 'xxyyzz',
            subtask_state                = Subtask.SubtaskState.FORCING_ACCEPTANCE,
            provider_key                 = self._get_encoded_provider_public_key(),
            requestor_key                = self._get_encoded_requestor_public_key(),
            expected_nested_messages={'task_to_compute', 'report_computed_task', 'ack_report_computed_task'},
            next_deadline                = parse_iso_date_to_timestamp("2018-02-05 10:00:45"),
        )
        self._test_last_stored_messages(
            expected_messages = [
                message.TaskToCompute,
                message.ReportComputedTask,
                message.AckReportComputedTask,
            ],
            task_id         = '2',
            subtask_id      = 'xxyyzz',
        )
        self._test_undelivered_pending_responses(
            subtask_id                         = 'xxyyzz',
            client_public_key                  = self._get_encoded_requestor_public_key(),
            expected_pending_responses_receive = [
                PendingResponse.ResponseType.ForceSubtaskResults,
            ]
        )

        # STEP 2: Different requestor or provider does not receive forces subtask results via Concent with different or mixed key.
        with freeze_time("2018-02-05 10:00:24"):
            response = self.client.post(
                reverse('core:receive'),
                data                            = self._create_diff_requestor_auth_message(),
                content_type                    = 'application/octet-stream',
            )

        self._test_204_response(response)
        self._assert_stored_message_counter_not_increased()

        with freeze_time("2018-02-05 10:00:24"):
            response = self.client.post(
                reverse('core:receive'),
                data                            = self._create_provider_auth_message(),
                content_type                    = 'application/octet-stream',
            )

        self._test_204_response(response)
        self._assert_stored_message_counter_not_increased()

        # STEP 3: Requestor receives forces subtask results via Concent with correct key.
        with freeze_time("2018-02-05 10:00:24"):
            response = self.client.post(
                reverse('core:receive'),
                data                            = self._create_requestor_auth_message(),
                content_type                    = 'application/octet-stream',
            )

        self._test_response(
            response,
            status          = 200,
            key             = self.REQUESTOR_PRIVATE_KEY,
            message_type    = message.concents.ForceSubtaskResults,
            fields          = {
                'timestamp':                            parse_iso_date_to_timestamp("2018-02-05 10:00:24"),
                'ack_report_computed_task.timestamp':   parse_iso_date_to_timestamp("2018-02-05 10:00:20"),
                'ack_report_computed_task.subtask_id':  'xxyyzz',
            }
        )
        self._assert_stored_message_counter_not_increased()

        # STEP 4:
        # 4.1. TaskToCompute is send signed with different key, request is rejected with proper error message.
        # 4.2. TaskToCompute is send with different requestor public key, request is rejected with proper error message.
        # 4.3. TaskToCompute is send with different data, request is rejected with proper error message.

        # 4.1.
        task_to_compute.sig = None
        task_to_compute = self._sign_message(
            task_to_compute,
            self.DIFFERENT_REQUESTOR_PRIVATE_KEY,
        )

        serialized_force_subtask_results_response = self._get_serialized_force_subtask_results_response(
            requestor_private_key   = self.DIFFERENT_REQUESTOR_PRIVATE_KEY,
            timestamp               = "2018-02-05 10:00:43",
            subtask_results_accepted = self._get_deserialized_subtask_results_accepted(
                timestamp               = "2018-02-05 10:00:43",
                payment_ts              = "2018-02-05 10:00:44",
                task_to_compute         = task_to_compute,
            )
        )

        with freeze_time("2018-02-05 10:00:44"):
            response = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_subtask_results_response,
                content_type                        = 'application/octet-stream',
            )

        self._test_400_response(
            response,
            error_message = 'There was an exception when validating if golem_message {} is signed with public key {}'.format(
                message.TaskToCompute.__name__,
                self.REQUESTOR_PUBLIC_KEY,
            ),
            error_code=ErrorCode.MESSAGE_SIGNATURE_WRONG
        )
        self._assert_stored_message_counter_not_increased()

        # 4.2.
        task_to_compute.sig = None
        task_to_compute.requestor_public_key = self._get_diffrent_requestor_hex_public_key()
        task_to_compute = self._sign_message(
            task_to_compute,
            self.DIFFERENT_REQUESTOR_PRIVATE_KEY,
        )
        serialized_force_subtask_results_response = self._get_serialized_force_subtask_results_response(
            requestor_private_key   = self.PROVIDER_PRIVATE_KEY,
            timestamp               = "2018-02-05 10:00:43",
            subtask_results_accepted = self._get_deserialized_subtask_results_accepted(
                timestamp       = "2018-02-05 10:00:43",
                payment_ts      = "2018-02-05 10:00:44",
                task_to_compute = task_to_compute,
                signer_private_key=self.DIFFERENT_REQUESTOR_PRIVATE_KEY,
            )
        )

        with freeze_time("2018-02-05 10:00:44"):
            response = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_subtask_results_response,
                content_type                        = 'application/octet-stream',
            )

        self._test_400_response(
            response,
            error_message = "Subtask requestor key does not match current client key.  Can't accept your '{}'.".format(
                message.concents.ForceSubtaskResultsResponse.__name__,
            ),
            error_code=ErrorCode.QUEUE_REQUESTOR_PUBLIC_KEY_MISMATCH
        )
        self._assert_stored_message_counter_not_increased()

        # 4.3.
        task_to_compute.sig = None
        task_to_compute.requestor_public_key = self._get_requestor_hex_public_key()
        task_to_compute.provider_id = 'different_id'
        task_to_compute = self._sign_message(
            task_to_compute,
            self.REQUESTOR_PRIVATE_KEY,
        )
        serialized_force_subtask_results_response = self._get_serialized_force_subtask_results_response(
            requestor_private_key   = self.PROVIDER_PRIVATE_KEY,
            timestamp               = "2018-02-05 10:00:43",
            subtask_results_accepted = self._get_deserialized_subtask_results_accepted(
                timestamp       = "2018-02-05 10:00:43",
                payment_ts      = "2018-02-05 10:00:44",
                task_to_compute = task_to_compute,
            )
        )

        with freeze_time("2018-02-05 10:00:44"):
            response = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_subtask_results_response,
                content_type                        = 'application/octet-stream',
            )

        self._test_400_response(
            response,
            error_message = 'TaskToCompute messages are not identical. '
                'There is a difference between messages with index 0 on passed list and with index {}'
                'The difference is on field {}'.format(
                    1,
                    'provider_id',
                ),
            error_code=ErrorCode.MESSAGES_NOT_IDENTICAL
        )
        self._assert_stored_message_counter_not_increased()

        # STEP 5: Requestor sends forces subtask results response via Concent with correct keys.
        # Request is processed correctly.
        task_to_compute.sig = None
        task_to_compute.provider_id = self._get_provider_hex_public_key()
        task_to_compute = self._sign_message(
            task_to_compute,
            self.REQUESTOR_PRIVATE_KEY,
        )

        serialized_force_subtask_results_response = self._get_serialized_force_subtask_results_response(
            requestor_private_key = self.REQUESTOR_PRIVATE_KEY,
            timestamp             = "2018-02-05 10:00:43",
            subtask_results_accepted = self._get_deserialized_subtask_results_accepted(
                timestamp       = "2018-02-05 10:00:43",
                payment_ts      = "2018-02-05 10:00:44",
                task_to_compute = task_to_compute,
            )
        )

        with freeze_time("2018-02-05 10:00:44"):
            self.client.post(
                reverse('core:send'),
                data                                = serialized_force_subtask_results_response,
                content_type                        = 'application/octet-stream',
            )

        self._assert_stored_message_counter_increased()
        self._test_subtask_state(
            task_id                      = '2',
            subtask_id                   = 'xxyyzz',
            subtask_state                = Subtask.SubtaskState.ACCEPTED,
            provider_key                 = self._get_encoded_provider_public_key(),
            requestor_key                = self._get_encoded_requestor_public_key(),
            expected_nested_messages={
                'task_to_compute',
                'report_computed_task',
                'ack_report_computed_task',
                'subtask_results_accepted'
            },
        )
        self._test_last_stored_messages(
            expected_messages = [
                message.tasks.SubtaskResultsAccepted,
            ],
            task_id         = '2',
            subtask_id      = 'xxyyzz',
        )
        self._test_undelivered_pending_responses(
            subtask_id                         = 'xxyyzz',
            client_public_key                  = self._get_encoded_provider_public_key(),
            expected_pending_responses_receive = [
                PendingResponse.ResponseType.ForceSubtaskResultsResponse,
            ]
        )

        # STEP 6: Different provider or requestor does not receive forces subtask results via Concent with different or mixed key.
        with freeze_time("2018-02-05 11:00:02"):
            response = self.client.post(
                reverse('core:receive'),
                data                            = self._create_diff_requestor_auth_message(),
                content_type                    = 'application/octet-stream',
            )

        self._test_204_response(response)
        self._assert_stored_message_counter_not_increased()

        with freeze_time("2018-02-05 11:00:02"):
            response = self.client.post(
                reverse('core:receive'),
                data                            = self._create_requestor_auth_message(),
                content_type                    = 'application/octet-stream',
            )

        self._test_204_response(response)
        self._assert_stored_message_counter_not_increased()

        # STEP 7: Provider does receives forces subtask results via Concent with correct key.
        with freeze_time("2018-02-05 11:00:02"):
            response = self.client.post(
                reverse('core:receive'),
                data                            = self._create_provider_auth_message(),
                content_type                    = 'application/octet-stream',
            )

        self._test_response(
            response,
            status          = 200,
            key             = self.PROVIDER_PRIVATE_KEY,
            message_type    = message.concents.ForceSubtaskResultsResponse,
            fields          = {
                'timestamp':                                                 parse_iso_date_to_timestamp("2018-02-05 11:00:02"),
                'subtask_results_accepted.timestamp':                        parse_iso_date_to_timestamp("2018-02-05 10:00:43"),
                'subtask_results_accepted.task_to_compute.compute_task_def': task_to_compute.compute_task_def,
                'subtask_results_accepted.payment_ts':                       parse_iso_date_to_timestamp("2018-02-05 10:00:44")
            }
        )
        self._assert_stored_message_counter_not_increased()

        self._assert_client_count_is_equal(2)

    def test_requestor_sends_subtask_results_rejected_and_concent_should_return_it_to_provider_with_correct_keys(self):
        """
        Test if Requestor wants submit SubtaskResultsAccepted message,
        Provider should receive it from Concent if correct keys are used.

        Exptected message exchange:
        Provider                  -> Concent:                 ForceSubtaskResults
        Concent                   -> Provider:                HTTP 202
        Concent                   -> WrongRequestor/Provider: HTTP 204
        Concent                   -> Requestor:               ForceSubtaskResults
        WrongRequestor/Provider   -> Concent:                 HTTP 400
        Requestor                 -> Concent:                 ForceSubtaskResultsResponse (with SubtaskResultsRejected)
        Concent                   -> WrongProvider/Requestor: HTTP 204
        Concent                   -> Provider:                ForceSubtaskResultsResponse (with SubtaskResultsRejected)
        """

        task_to_compute = self._get_deserialized_task_to_compute(
            timestamp   = "2018-02-05 10:00:00",
            deadline    = "2018-02-05 10:00:15",
            task_id     = "2",
            subtask_id  = "xxyyzz",
        )

        # STEP 1: Provider forces subtask results via Concent.
        # Request is processed correctly.
        serialized_force_subtask_results = self._get_serialized_force_subtask_results(
            timestamp                   = "2018-02-05 10:00:30",
            ack_report_computed_task    = self._get_deserialized_ack_report_computed_task(
                timestamp       = "2018-02-05 10:00:20",
                subtask_id      = "xxyyzz",
                task_to_compute = task_to_compute,
                signer_private_key=self.REQUESTOR_PRIVATE_KEY,
            )
        )

        with mock.patch(
            'core.message_handlers.payments_service.is_account_status_positive',
            side_effect=self.is_account_status_positive_true_mock
        ) as is_account_status_positive_true_mock_function:
            with freeze_time("2018-02-05 10:00:30"):
                response = self.client.post(
                    reverse('core:send'),
                    data                                = serialized_force_subtask_results,
                    content_type                        = 'application/octet-stream',
                )

        is_account_status_positive_true_mock_function.assert_called_with(
            client_eth_address=task_to_compute.requestor_ethereum_address,
            pending_value=task_to_compute.price,
        )

        assert len(response.content)  == 0
        assert response.status_code   == 202

        self._assert_stored_message_counter_increased(increased_by=3)
        self._test_subtask_state(
            task_id                      = '2',
            subtask_id                   = 'xxyyzz',
            subtask_state                = Subtask.SubtaskState.FORCING_ACCEPTANCE,
            provider_key                 = self._get_encoded_provider_public_key(),
            requestor_key                = self._get_encoded_requestor_public_key(),
            expected_nested_messages={'task_to_compute', 'report_computed_task', 'ack_report_computed_task'},
            next_deadline                = parse_iso_date_to_timestamp("2018-02-05 10:00:45"),
        )
        self._test_last_stored_messages(
            expected_messages = [
                message.TaskToCompute,
                message.ReportComputedTask,
                message.AckReportComputedTask,
            ],
            task_id         = '2',
            subtask_id      = 'xxyyzz',
        )
        self._test_undelivered_pending_responses(
            subtask_id                         = 'xxyyzz',
            client_public_key                  = self._get_encoded_requestor_public_key(),
            expected_pending_responses_receive = [
                PendingResponse.ResponseType.ForceSubtaskResults,
            ]
        )

        # STEP 2: Different requestor or provider does not receive forces subtask results via Concent with different or mixed key.
        with freeze_time("2018-02-05 10:00:24"):
            response = self.client.post(
                reverse('core:receive'),
                data = self._create_diff_requestor_auth_message(),
                content_type='application/octet-stream',
            )

        self._test_204_response(response)
        self._assert_stored_message_counter_not_increased()

        with freeze_time("2018-02-05 10:00:24"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = self._create_provider_auth_message(),
                content_type                   = 'application/octet-stream',
            )

        self._test_204_response(response)
        self._assert_stored_message_counter_not_increased()

        # STEP 3: Requestor receives forces subtask results via Concent with correct key.
        with freeze_time("2018-02-05 10:00:24"):
            response = self.client.post(
                reverse('core:receive'),
                data                            = self._create_requestor_auth_message(),
                content_type                    = 'application/octet-stream',
            )

        self._test_response(
            response,
            status          = 200,
            key             = self.REQUESTOR_PRIVATE_KEY,
            message_type    = message.concents.ForceSubtaskResults,
            fields          = {
                'timestamp':                            parse_iso_date_to_timestamp("2018-02-05 10:00:24"),
                'ack_report_computed_task.timestamp':   parse_iso_date_to_timestamp("2018-02-05 10:00:20"),
                'ack_report_computed_task.subtask_id':  'xxyyzz',
            }
        )
        self._assert_stored_message_counter_not_increased()

        # STEP 4:
        # 4.1. TaskToCompute is send signed with different key, request is rejected with proper error message.
        # 4.2. TaskToCompute is send with different requestor public key, request is rejected with proper error message.
        # 4.3. TaskToCompute is send with different data, request is rejected with proper error message.

        # 4.1.
        task_to_compute.sig = None
        task_to_compute = self._sign_message(
            task_to_compute,
            self.DIFFERENT_REQUESTOR_PRIVATE_KEY,
        )

        serialized_force_subtask_results_response = self._get_serialized_force_subtask_results_response(
            requestor_private_key   = self.DIFFERENT_REQUESTOR_PRIVATE_KEY,
            timestamp               = "2018-02-05 10:00:43",
            subtask_results_accepted = self._get_deserialized_subtask_results_accepted(
                timestamp               = "2018-02-05 10:00:43",
                payment_ts              = "2018-02-05 10:00:44",
                task_to_compute         = task_to_compute,
            )
        )

        with freeze_time("2018-02-05 10:00:44"):
            response = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_subtask_results_response,
                content_type                        = 'application/octet-stream',
            )

        self._test_400_response(
            response,
            error_message = 'There was an exception when validating if golem_message {} is signed with public key {}'.format(
                message.TaskToCompute.__name__,
                self.REQUESTOR_PUBLIC_KEY,
            ),
            error_code=ErrorCode.MESSAGE_SIGNATURE_WRONG
        )
        self._assert_stored_message_counter_not_increased()

        # 4.2.
        task_to_compute.sig = None
        task_to_compute.requestor_public_key = self._get_diffrent_requestor_hex_public_key()
        task_to_compute = self._sign_message(
            task_to_compute,
            self.DIFFERENT_REQUESTOR_PRIVATE_KEY,
        )
        serialized_force_subtask_results_response = self._get_serialized_force_subtask_results_response(
            requestor_private_key   = self.PROVIDER_PRIVATE_KEY,
            timestamp               = "2018-02-05 10:00:43",
            subtask_results_accepted = self._get_deserialized_subtask_results_accepted(
                timestamp       = "2018-02-05 10:00:43",
                payment_ts      = "2018-02-05 10:00:44",
                task_to_compute = task_to_compute,
                signer_private_key=self.DIFFERENT_REQUESTOR_PRIVATE_KEY,
            )
        )

        with freeze_time("2018-02-05 10:00:44"):
            response = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_subtask_results_response,
                content_type                        = 'application/octet-stream',
            )

        self._test_400_response(
            response,
            error_message = "Subtask requestor key does not match current client key.  Can't accept your '{}'.".format(
                message.concents.ForceSubtaskResultsResponse.__name__,
            ),
            error_code=ErrorCode.QUEUE_REQUESTOR_PUBLIC_KEY_MISMATCH
        )
        self._assert_stored_message_counter_not_increased()

        # 4.3.
        task_to_compute.sig = None
        task_to_compute.requestor_public_key = self._get_requestor_hex_public_key()
        task_to_compute.provider_id = 'different_id'
        task_to_compute = self._sign_message(
            task_to_compute,
            self.REQUESTOR_PRIVATE_KEY,
        )
        serialized_force_subtask_results_response = self._get_serialized_force_subtask_results_response(
            requestor_private_key   = self.PROVIDER_PRIVATE_KEY,
            timestamp               = "2018-02-05 10:00:43",
            subtask_results_accepted = self._get_deserialized_subtask_results_accepted(
                timestamp       = "2018-02-05 10:00:43",
                payment_ts      = "2018-02-05 10:00:44",
                task_to_compute = task_to_compute,
            )
        )

        with freeze_time("2018-02-05 10:00:44"):
            response = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_subtask_results_response,
                content_type                        = 'application/octet-stream',
            )

        self._test_400_response(
            response,
            error_message = 'TaskToCompute messages are not identical. '
                'There is a difference between messages with index 0 on passed list and with index {}'
                'The difference is on field {}'.format(
                    1,
                    'provider_id',
                ),
            error_code=ErrorCode.MESSAGES_NOT_IDENTICAL
        )
        self._assert_stored_message_counter_not_increased()

        # STEP 5: Requestor sends forces subtask results response via Concent with correct keys.
        # Request is processed correctly.
        task_to_compute.sig = None
        task_to_compute.provider_id = self._get_provider_hex_public_key()
        task_to_compute = self._sign_message(
            task_to_compute,
            self.REQUESTOR_PRIVATE_KEY,
        )

        serialized_force_subtask_results_response = self._get_serialized_force_subtask_results_response(
            requestor_private_key   = self.REQUESTOR_PRIVATE_KEY,
            timestamp               = "2018-02-05 10:00:43",
            subtask_results_rejected = self._get_deserialized_subtask_results_rejected(
                timestamp               = "2018-02-05 10:00:43",
                reason                  = message.tasks.SubtaskResultsRejected.REASON.VerificationNegative,
                report_computed_task    = self._get_deserialized_report_computed_task(
                    timestamp   = "2018-02-05 10:00:43",
                    subtask_id  = "xxyyzz",
                    task_to_compute = task_to_compute
                )
            )
        )

        with freeze_time("2018-02-05 10:00:44"):
            self.client.post(
                reverse('core:send'),
                data                                = serialized_force_subtask_results_response,
                content_type                        = 'application/octet-stream',
            )

        self._assert_stored_message_counter_increased(increased_by=1)
        self._test_subtask_state(
            task_id='2',
            subtask_id='xxyyzz',
            subtask_state=Subtask.SubtaskState.REJECTED,
            provider_key=self._get_encoded_provider_public_key(),
            requestor_key=self._get_encoded_requestor_public_key(),
            expected_nested_messages={
                'task_to_compute',
                'report_computed_task',
                'ack_report_computed_task',
                'subtask_results_rejected'
            },
        )
        self._test_last_stored_messages(
            expected_messages=[
                message.tasks.SubtaskResultsRejected,
            ],
            task_id='2',
            subtask_id='xxyyzz',
        )
        self._test_undelivered_pending_responses(
            subtask_id='xxyyzz',
            client_public_key=self._get_encoded_provider_public_key(),
            expected_pending_responses_receive=[
                PendingResponse.ResponseType.ForceSubtaskResultsResponse,
            ]
        )

        # STEP 6: Different provider or requestor does not receive forces subtask results via Concent with different or mixed key.
        with freeze_time("2018-02-05 11:00:02"):
            response = self.client.post(
                reverse('core:receive'),
                data                            = self._create_diff_requestor_auth_message(),
                content_type                    = 'application/octet-stream',
            )

        self._test_204_response(response)
        self._assert_stored_message_counter_not_increased()

        with freeze_time("2018-02-05 11:00:02"):
            response = self.client.post(
                reverse('core:receive'),
                data                            = self._create_requestor_auth_message(),
                content_type                    = 'application/octet-stream',
            )

        self._test_204_response(response)
        self._assert_stored_message_counter_not_increased()

        # STEP 7: Provider does receives forces subtask results via Concent with correct key.
        with freeze_time("2018-02-05 11:00:02"):
            response = self.client.post(
                reverse('core:receive'),
                data                            = self._create_provider_auth_message(),
                content_type                    = 'application/octet-stream',
            )

        self._test_response(
            response,
            status          = 200,
            key             = self.PROVIDER_PRIVATE_KEY,
            message_type    = message.concents.ForceSubtaskResultsResponse,
            fields          = {
                'timestamp':                                                parse_iso_date_to_timestamp("2018-02-05 11:00:02"),
                'subtask_results_rejected.timestamp':                       parse_iso_date_to_timestamp("2018-02-05 10:00:43"),
                'subtask_results_rejected.reason':                          message.tasks.SubtaskResultsRejected.REASON.VerificationNegative,
                'subtask_results_rejected.report_computed_task.timestamp':  parse_iso_date_to_timestamp("2018-02-05 10:00:43"),
                'subtask_results_rejected.report_computed_task.subtask_id': 'xxyyzz'
            }
        )
        self._assert_stored_message_counter_not_increased()

        self._assert_client_count_is_equal(2)

    def test_requestor_doesnt_provide_response_should_end_with_subtask_results_settled_received_from_concent_with_correct_keys(self):
        """
        Expected message exchange:
        Provider                  -> Concent:                     ForceSubtaskResults
        Concent                   -> Provider:                    HTTP 202
        Concent                   -> WrongRequestor/Provider:     HTTP 204
        Concent                   -> Requestor:                   ForceSubtaskResults
        Requestor                 -> Concent:                     no response
        Concent                   -> WrongProvider:               HTTP 204
        Concent                   -> Provider:                    SubtaskResultsSettled
        Concent                   -> WrongRequestor               HTTP 204
        Concent                   -> Requestor                    SubtaskResultsSettled
        """

        compute_task_def = self._get_deserialized_compute_task_def(
            deadline="2018-02-05 10:00:15",
            task_id='1',
            subtask_id='xxyyzz',
        )

        task_to_compute = self._get_deserialized_task_to_compute(
            timestamp="2018-02-05 10:00:00",
            compute_task_def=compute_task_def,
        )

        # STEP 1: Provider forces subtask results via Concent.
        # Request is processed correctly.
        serialized_force_subtask_results = self._get_serialized_force_subtask_results(
            timestamp                   = "2018-02-05 10:00:30",
            ack_report_computed_task    = self._get_deserialized_ack_report_computed_task(
                timestamp       = "2018-02-05 10:00:20",
                subtask_id      = "xxyyzz",
                task_to_compute = task_to_compute,
                signer_private_key=self.REQUESTOR_PRIVATE_KEY,
            )
        )

        with mock.patch(
            'core.message_handlers.payments_service.is_account_status_positive',
            side_effect=self.is_account_status_positive_true_mock
        ) as is_account_status_positive_true_mock_function:
            with freeze_time("2018-02-05 10:00:30"):
                response = self.client.post(
                    reverse('core:send'),
                    data                                = serialized_force_subtask_results,
                    content_type                        = 'application/octet-stream',
                )

        is_account_status_positive_true_mock_function.assert_called_with(
            client_eth_address=task_to_compute.requestor_ethereum_address,
            pending_value=task_to_compute.price,
        )

        assert len(response.content) == 0
        assert response.status_code  == 202

        self._assert_stored_message_counter_increased(increased_by=3)
        self._test_subtask_state(
            task_id                      = '1',
            subtask_id                   = 'xxyyzz',
            subtask_state                = Subtask.SubtaskState.FORCING_ACCEPTANCE,
            provider_key                 = self._get_encoded_provider_public_key(),
            requestor_key                = self._get_encoded_requestor_public_key(),
            expected_nested_messages={'task_to_compute', 'report_computed_task', 'ack_report_computed_task'},
            next_deadline                = parse_iso_date_to_timestamp("2018-02-05 10:00:45"),
        )
        self._test_last_stored_messages(
            expected_messages = [
                message.TaskToCompute,
                message.ReportComputedTask,
                message.AckReportComputedTask,
            ],
            task_id         = '1',
            subtask_id      = 'xxyyzz',
        )
        self._test_undelivered_pending_responses(
            subtask_id                         = 'xxyyzz',
            client_public_key                  = self._get_encoded_requestor_public_key(),
            expected_pending_responses_receive = [
                PendingResponse.ResponseType.ForceSubtaskResults,
            ]
        )

        # STEP 2: Different requestor or provider does not receive forces subtask results via Concent with different or mixed key.
        with freeze_time("2018-02-05 10:00:24"):
            response = self.client.post(
                reverse('core:receive'),
                data                            = self._create_diff_requestor_auth_message(),
                content_type                    = 'application/octet-stream',
            )

        self._test_204_response(response)
        self._assert_stored_message_counter_not_increased()

        with freeze_time("2018-02-05 10:00:24"):
            response = self.client.post(
                reverse('core:receive'),
                data                            = self._create_provider_auth_message(),
                content_type                    = 'application/octet-stream',
            )

        self._test_204_response(response)
        self._assert_stored_message_counter_not_increased()

        # STEP 3: Requestor receives forces subtask results via Concent with correct key.
        with freeze_time("2018-02-05 10:00:24"):
            response = self.client.post(
                reverse('core:receive'),
                data                            = self._create_requestor_auth_message(),
                content_type                    = 'application/octet-stream',
            )
        self._test_response(
            response,
            status       = 200,
            key          = self.REQUESTOR_PRIVATE_KEY,
            message_type = message.concents.ForceSubtaskResults,
            fields       = {
                'timestamp':                                                 parse_iso_date_to_timestamp("2018-02-05 10:00:24"),
                'ack_report_computed_task.subtask_id':                       'xxyyzz',
                'ack_report_computed_task.report_computed_task.task_to_compute.compute_task_def': compute_task_def,
            }
        )
        self._assert_stored_message_counter_not_increased()

        # STEP 4: Different provider does not receive subtask result settled via Concent with different key.
        with freeze_time("2018-02-05 10:00:48"):
            response = self.client.post(
                reverse('core:receive'),
                data=self._create_diff_provider_auth_message(),
                content_type='application/octet-stream',
            )

        self._test_204_response(response)
        self._assert_stored_message_counter_not_increased()

        # STEP 5: Provider receives subtask result settled via Concent with correct key.
        with freeze_time("2018-02-05 10:00:50"):
            response = self.client.post(
                reverse('core:receive'),
                data=self._create_provider_auth_message(),
                content_type='application/octet-stream',
            )

        self._test_response(
            response,
            status       = 200,
            key          = self.PROVIDER_PRIVATE_KEY,
            message_type = message.concents.SubtaskResultsSettled,
            fields       = {
                'timestamp':                        parse_iso_date_to_timestamp("2018-02-05 10:00:50"),
                'task_to_compute.compute_task_def': compute_task_def,
            }
        )
        self._assert_stored_message_counter_not_increased()
        self._test_subtask_state(
            task_id                      = '1',
            subtask_id                   = 'xxyyzz',
            subtask_state                = Subtask.SubtaskState.ACCEPTED,
            provider_key                 = self._get_encoded_provider_public_key(),
            requestor_key                = self._get_encoded_requestor_public_key(),
            expected_nested_messages={'task_to_compute', 'report_computed_task', 'ack_report_computed_task'},
        )
        self._test_undelivered_pending_responses(
            subtask_id                         = 'xxyyzz',
            client_public_key                  = self._get_encoded_provider_public_key(),
            client_public_key_out_of_band      = self._get_encoded_requestor_public_key(),
            expected_pending_responses_receive_out_of_band = [
                PendingResponse.ResponseType.SubtaskResultsSettled,
            ]
        )

        # STEP 6: Different requestor does not receive subtask result settled via Concent with different key.
        with freeze_time("2018-02-05 10:00:51"):
            response = self.client.post(
                reverse('core:receive_out_of_band'),
                data                            = self._create_diff_requestor_auth_message(),
                content_type                    = 'application/octet-stream',
            )
        self._test_204_response(response)
        self._assert_stored_message_counter_not_increased()

        # STEP 7: Requestor receives subtask result settled via Concent with correct key.
        with freeze_time("2018-02-05 10:00:51"):
            response = self.client.post(
                reverse('core:receive_out_of_band'),
                data                            = self._create_requestor_auth_message(),
                content_type                    = 'application/octet-stream',
            )
        self._test_response(
            response,
            status       = 200,
            key          = self.REQUESTOR_PRIVATE_KEY,
            message_type = message.concents.SubtaskResultsSettled,
            fields       = {
                'timestamp':                        parse_iso_date_to_timestamp("2018-02-05 10:00:51"),
                'task_to_compute.compute_task_def': compute_task_def,
            }
        )
        self._assert_stored_message_counter_not_increased()

        self._assert_client_count_is_equal(2)

    def test_requestor_doesnt_provide_response_should_end_with_subtask_results_settled_received_from_concent_different_configuration_with_correct_keys(self):
        """
        Expected message exchange:
        Provider                  -> Concent:                     ForceSubtaskResults
        Concent                   -> Provider:                    HTTP 202
        Concent                   -> WrongRequestor/Provider:     HTTP 204
        Concent                   -> Requestor:                   ForceSubtaskResults
        Requestor                 -> Concent:                     no response
        Concent                   -> WrongRequestor               HTTP 204
        Concent                   -> Requestor                    SubtaskResultsSettled
        Concent                   -> WrongProvider:               HTTP 204
        Concent                   -> Provider:                    SubtaskResultsSettled
        """

        compute_task_def = self._get_deserialized_compute_task_def(
            deadline="2018-02-05 10:00:15",
            task_id='1',
            subtask_id='xxyyzz',
        )

        task_to_compute = self._get_deserialized_task_to_compute(
            timestamp="2018-02-05 10:00:00",
            compute_task_def=compute_task_def,
        )

        # STEP 1: Provider forces subtask results via Concent.
        # Request is processed correctly.
        serialized_force_subtask_results = self._get_serialized_force_subtask_results(
            timestamp                   = "2018-02-05 10:00:30",
            ack_report_computed_task    = self._get_deserialized_ack_report_computed_task(
                timestamp       = "2018-02-05 10:00:20",
                subtask_id      = "xxyyzz",
                task_to_compute = task_to_compute,
                signer_private_key=self.REQUESTOR_PRIVATE_KEY,
            )
        )

        with mock.patch(
            'core.message_handlers.payments_service.is_account_status_positive',
            side_effect=self.is_account_status_positive_true_mock
        ) as is_account_status_positive_true_mock_function:
            with freeze_time("2018-02-05 10:00:30"):
                response = self.client.post(
                    reverse('core:send'),
                    data=serialized_force_subtask_results,
                    content_type='application/octet-stream',
                )

        is_account_status_positive_true_mock_function.assert_called_with(
            client_eth_address=task_to_compute.requestor_ethereum_address,
            pending_value=task_to_compute.price,
        )

        assert len(response.content) == 0
        assert response.status_code  == 202

        self._assert_stored_message_counter_increased(increased_by=3)
        self._test_subtask_state(
            task_id                      = '1',
            subtask_id                   = 'xxyyzz',
            subtask_state                = Subtask.SubtaskState.FORCING_ACCEPTANCE,
            provider_key                 = self._get_encoded_provider_public_key(),
            requestor_key                = self._get_encoded_requestor_public_key(),
            expected_nested_messages={'task_to_compute', 'report_computed_task', 'ack_report_computed_task'},
            next_deadline                = parse_iso_date_to_timestamp("2018-02-05 10:00:45"),
        )
        self._test_last_stored_messages(
            expected_messages = [
                message.TaskToCompute,
                message.ReportComputedTask,
                message.AckReportComputedTask,
            ],
            task_id         = '1',
            subtask_id      = 'xxyyzz',
        )
        self._test_undelivered_pending_responses(
            subtask_id                         = 'xxyyzz',
            client_public_key                  = self._get_encoded_requestor_public_key(),
            expected_pending_responses_receive = [
                PendingResponse.ResponseType.ForceSubtaskResults,
            ]
        )

        # STEP 2: Different requestor or provider does not receive forces subtask results via Concent with different or mixed key.
        with freeze_time("2018-02-05 10:00:24"):
            response = self.client.post(
                reverse('core:receive'),
                data                            = self._create_diff_requestor_auth_message(),
                content_type                    = 'application/octet-stream',
            )

        self._test_204_response(response)

        with freeze_time("2018-02-05 10:00:24"):
            response = self.client.post(
                reverse('core:receive'),
                data                            = self._create_provider_auth_message(),
                content_type                    = 'application/octet-stream',
            )

        self._test_204_response(response)
        self._assert_stored_message_counter_not_increased()

        # STEP 3: Requestor receives forces subtask results via Concent with correct key.
        with freeze_time("2018-02-05 10:00:24"):
            response = self.client.post(
                reverse('core:receive'),
                data                            = self._create_requestor_auth_message(),
                content_type                    = 'application/octet-stream',
            )
        self._test_response(
            response,
            status       = 200,
            key          = self.REQUESTOR_PRIVATE_KEY,
            message_type = message.concents.ForceSubtaskResults,
            fields       = {
                'timestamp':                                                 parse_iso_date_to_timestamp("2018-02-05 10:00:24"),
                'ack_report_computed_task.subtask_id':                       'xxyyzz',
                'ack_report_computed_task.report_computed_task.task_to_compute.compute_task_def': compute_task_def,
            }
        )
        self._assert_stored_message_counter_not_increased()

        # STEP 4: Different provider does not receive subtask result settled via Concent with different key.
        with freeze_time("2018-02-05 10:00:51"):
            response = self.client.post(
                reverse('core:receive_out_of_band'),
                data                            = self._create_diff_requestor_auth_message(),
                content_type                    = 'application/octet-stream',
            )
        self._test_204_response(response)
        self._assert_stored_message_counter_not_increased()

        # STEP 5: Provider receives subtask result settled via Concent with correct key.
        with freeze_time("2018-02-05 10:00:51"):
            response = self.client.post(
                reverse('core:receive_out_of_band'),
                data                            = self._create_requestor_auth_message(),
                content_type                    = 'application/octet-stream',
            )
        self._test_response(
            response,
            status       = 200,
            key          = self.REQUESTOR_PRIVATE_KEY,
            message_type = message.concents.SubtaskResultsSettled,
            fields       = {
                'timestamp':                        parse_iso_date_to_timestamp("2018-02-05 10:00:51"),
                'task_to_compute.compute_task_def': compute_task_def,
            }
        )
        self._assert_stored_message_counter_not_increased()
        self._test_subtask_state(
            task_id                      = '1',
            subtask_id                   = 'xxyyzz',
            subtask_state                = Subtask.SubtaskState.ACCEPTED,
            provider_key                 = self._get_encoded_provider_public_key(),
            requestor_key                = self._get_encoded_requestor_public_key(),
            expected_nested_messages={'task_to_compute', 'report_computed_task', 'ack_report_computed_task'},
        )
        self._test_undelivered_pending_responses(
            subtask_id                         = 'xxyyzz',
            client_public_key                  = self._get_encoded_provider_public_key(),
            expected_pending_responses_receive = [
                PendingResponse.ResponseType.SubtaskResultsSettled,
            ]
        )

        # STEP 6: Different requestor does not receive subtask result settled via Concent with different key.
        with freeze_time("2018-02-05 10:00:51"):
            response = self.client.post(
                reverse('core:receive'),
                data=self._create_diff_requestor_auth_message(),
                content_type='application/octet-stream',
            )

        is_account_status_positive_true_mock_function.assert_called_with(
            client_eth_address=task_to_compute.requestor_ethereum_address,
            pending_value=task_to_compute.price,
        )

        self._test_204_response(response)
        self._assert_stored_message_counter_not_increased()

        # STEP 7: Requestor receives subtask result settled via Concent with correct key.
        with freeze_time("2018-02-05 10:00:51"):
            response = self.client.post(
                reverse('core:receive'),
                data=self._create_provider_auth_message(),
                content_type='application/octet-stream',
            )

        self._test_response(
            response,
            status       = 200,
            key          = self.PROVIDER_PRIVATE_KEY,
            message_type = message.concents.SubtaskResultsSettled,
            fields       = {
                'timestamp':                        parse_iso_date_to_timestamp("2018-02-05 10:00:51"),
                'task_to_compute.compute_task_def': compute_task_def,
            }
        )
        self._assert_stored_message_counter_not_increased()

        self._assert_client_count_is_equal(2)
