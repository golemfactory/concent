import mock

from django.test            import override_settings
from django.urls            import reverse
from freezegun              import freeze_time
from golem_messages         import message

from core.constants         import ETHEREUM_ADDRESS_LENGTH
from core.exceptions import Http400
from core.message_handlers import handle_send_force_subtask_results_response
from core.message_handlers import store_or_update_subtask
from core.models            import StoredMessage
from core.models            import Subtask
from core.models            import PendingResponse
from core.tests.utils import ConcentIntegrationTestCase
from core.tests.utils import parse_iso_date_to_timestamp
from common.constants        import ErrorCode
from common.testing_helpers  import generate_ecc_key_pair


(CONCENT_PRIVATE_KEY, CONCENT_PUBLIC_KEY) = generate_ecc_key_pair()


def _get_provider_account_status_true_mock(client_eth_address, pending_value):  # pylint: disable=unused-argument
    return True


def _get_provider_account_status_false_mock(client_eth_address, pending_value):  # pylint: disable=unused-argument
    return False


def _get_requestor_account_status(_provider, _requestor):
    pass


@override_settings(
    CONCENT_PRIVATE_KEY       = CONCENT_PRIVATE_KEY,
    CONCENT_PUBLIC_KEY        = CONCENT_PUBLIC_KEY,
    CONCENT_MESSAGING_TIME    = 10,  # seconds
    FORCE_ACCEPTANCE_TIME     = 10,  # seconds
    CONCENT_ETHEREUM_ADDRESS  = 'x' * ETHEREUM_ADDRESS_LENGTH
)
class AcceptOrRejectIntegrationTest(ConcentIntegrationTestCase):

    def setUp(self):
        super().setUp()
        self.patcher = mock.patch('core.message_handlers.calculate_subtask_verification_time', return_value=10)
        self.addCleanup(self.patcher.stop)
        self.patcher.start()

    def test_provider_forces_subtask_results_for_task_which_was_already_submitted_concent_should_refuse(self):
        """
        Tests if on provider ForceSubtaskResults message Concent will return ServiceRefused
        if ForceSubtaskResults with same task_id was already submitted.

        Expected message exchange:
        Provider  -> Concent:    ForceSubtaskResults
        Concent   -> Provider:   HTTP 202
        Provider  -> Concent:    ForceSubtaskResults
        Concent   -> Provider:   ServiceRefused
        """

        task_to_compute = self._get_deserialized_task_to_compute(
            timestamp   = "2018-02-05 10:00:00",
            deadline    = "2018-02-05 10:00:15",
            task_id     = '2',
            subtask_id  = 'xxyyzz',
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
            side_effect=_get_provider_account_status_true_mock
        ) as is_account_status_positive_true_mock_function:
            with freeze_time("2018-02-05 10:00:30"):
                response_1 = self.client.post(
                    reverse('core:send'),
                    data                                = serialized_force_subtask_results,
                    content_type                        = 'application/octet-stream',
                )

        is_account_status_positive_true_mock_function.assert_called_with(
            client_eth_address=task_to_compute.requestor_ethereum_address,
            pending_value=task_to_compute.price,
        )

        assert len(response_1.content)  == 0
        assert response_1.status_code   == 202

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

        # STEP 2: Provider again forces subtask results via Concent with message with the same task_id.
        # Request is refused.
        with freeze_time("2018-02-05 10:00:31"):
            response_2 = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_subtask_results,
                content_type                        = 'application/octet-stream',
            )

        self._test_response(
            response_2,
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

    def test_provider_forces_subtask_results_with_not_enough_funds_on_this_account_concent_should_refuse(self):
        """
        Test if on provider ForceSubtaskResult message Concent will return ServiceRefused
        if provider doesn't have enough funds on his account.

        Expected message exchange:
        Provider    -> Concent:     ForceSubtaskResults
        Concent     -> Provider:    ServiceRefused
        """

        task_to_compute = self._get_deserialized_task_to_compute(
            timestamp="2018-02-05 10:00:30"
        )

        # STEP 1: Provider forces subtask results via Concent.
        # Concent returns ServiceRefused.
        serialized_force_subtask_results = self._get_serialized_force_subtask_results(
            timestamp = "2018-02-05 10:00:30",
            ack_report_computed_task=self._get_deserialized_ack_report_computed_task(
                task_to_compute=task_to_compute,
                signer_private_key=self.REQUESTOR_PRIVATE_KEY,
            )
        )

        with mock.patch(
            'core.message_handlers.payments_service.is_account_status_positive',
            side_effect=_get_provider_account_status_false_mock
        ) as is_account_status_positive_false_mock_function:
            with freeze_time("2018-02-05 10:00:35"):
                response_1 = self.client.post(
                    reverse('core:send'),
                    data                                = serialized_force_subtask_results,
                    content_type                        = 'application/octet-stream',
                )

        is_account_status_positive_false_mock_function.assert_called_with(
            client_eth_address=task_to_compute.requestor_ethereum_address,
            pending_value=task_to_compute.price,
        )

        self.assertEqual(StoredMessage.objects.last(), None)

        self._test_response(
            response_1,
            status       = 200,
            key          = self.PROVIDER_PRIVATE_KEY,
            message_type = message.concents.ServiceRefused,
            fields       = {
                'reason':       message.concents.ServiceRefused.REASON.TooSmallRequestorDeposit,
                'timestamp':    parse_iso_date_to_timestamp("2018-02-05 10:00:35")
            }
        )
        self._assert_stored_message_counter_not_increased()

        self._assert_client_count_is_equal(0)

    def test_provider_forces_subtask_results_but_it_was_sent_to_too_late_or_too_soon_concent_should_reject(self):
        """
        Test if on provider ForceSubtaskResult message Concent will return ForceSubtaskResultsRejected
        if provider sent ForceSubtaskResults too soon or too late

        Expected message exchange:
        Provider    -> Concent:     ForceSubtaskResults (too soon)
        Concent     -> Provider:    ForceSubtaskResultsRejected
        Provider    -> Concent:     ForceSubtaskResults (too late)
        Concent     -> Provider:    ForceSubtaskResultsRejected
        """

        task_to_compute = self._get_deserialized_task_to_compute(
            timestamp   = "2018-03-05 10:00:00",
            deadline    = "2018-03-05 10:00:15",
            task_id     = '2',
        )

        # STEP 1: Provider forces subtask results via Concent.
        # Concent return ForceSubtaskResultRejected because message from Provider was sent too soon.

        serialized_force_subtask_results = self._get_serialized_force_subtask_results(
            timestamp="2018-03-05 10:00:24",
            ack_report_computed_task=self._get_deserialized_ack_report_computed_task(
                timestamp="2018-03-05 10:00:15",
                subtask_id="2",
                task_to_compute=task_to_compute,
                signer_private_key=self.REQUESTOR_PRIVATE_KEY,
            )
        )

        with mock.patch(
            'core.message_handlers.payments_service.is_account_status_positive',
            side_effect=_get_provider_account_status_true_mock
        ) as is_account_status_positive_true_mock_function:
            with freeze_time("2018-03-05 10:00:24"):
                response_1 = self.client.post(
                    reverse('core:send'),
                    data                                = serialized_force_subtask_results,
                    content_type                        = 'application/octet-stream',
                )

        is_account_status_positive_true_mock_function.assert_called_with(
            client_eth_address=task_to_compute.requestor_ethereum_address,
            pending_value=task_to_compute.price,
        )

        self._test_response(
            response_1,
            status       = 200,
            key          = self.PROVIDER_PRIVATE_KEY,
            message_type = message.concents.ForceSubtaskResultsRejected,
            fields       = {
                'reason':       message.concents.ForceSubtaskResultsRejected.REASON.RequestPremature,
                'force_subtask_results.timestamp': parse_iso_date_to_timestamp("2018-03-05 10:00:24"),
                'force_subtask_results.task_to_compute.timestamp': parse_iso_date_to_timestamp("2018-03-05 10:00:00"),
                'timestamp':    parse_iso_date_to_timestamp("2018-03-05 10:00:24"),
            }
        )
        self._assert_stored_message_counter_not_increased()

        serialized_force_subtask_results = self._get_serialized_force_subtask_results(
            timestamp                   = "2018-03-05 10:00:40",
            ack_report_computed_task    = self._get_deserialized_ack_report_computed_task(
                timestamp       = "2018-03-05 10:00:15",
                subtask_id      = '2',
                task_to_compute = self._get_deserialized_task_to_compute(
                    timestamp   = "2018-03-05 10:00:00",
                    deadline    = "2018-03-05 10:00:10",
                    task_id     = '2',
                ),
                signer_private_key=self.REQUESTOR_PRIVATE_KEY,
            )
        )

        with mock.patch(
            'core.message_handlers.payments_service.is_account_status_positive',
            side_effect=_get_provider_account_status_true_mock
        ) as is_account_status_positive_true_mock_function:
            with freeze_time("2018-03-05 10:00:40"):
                response_2 = self.client.post(
                    reverse('core:send'),
                    data                                = serialized_force_subtask_results,
                    content_type                        = 'application/octet-stream',
                )

        is_account_status_positive_true_mock_function.assert_called_with(
            client_eth_address=task_to_compute.requestor_ethereum_address,
            pending_value=task_to_compute.price,
        )

        self._test_response(
            response_2,
            status       = 200,
            key          = self.PROVIDER_PRIVATE_KEY,
            message_type = message.concents.ForceSubtaskResultsRejected,
            fields       = {
                'reason':       message.concents.ForceSubtaskResultsRejected.REASON.RequestTooLate,
                'force_subtask_results.timestamp': parse_iso_date_to_timestamp("2018-03-05 10:00:40"),
                'force_subtask_results.task_to_compute.timestamp': parse_iso_date_to_timestamp("2018-03-05 10:00:00"),
                'timestamp':    parse_iso_date_to_timestamp("2018-03-05 10:00:40"),
            }
        )
        self._assert_stored_message_counter_not_increased()

        self._assert_client_count_is_equal(0)

    def test_requestor_should_receive_subtask_results_from_concent(self):
        """
        Test if Provider submitted ForceSubtaskResults, Concent will return message to Requestor with new timestamp
        if Requestor ask Concent before deadline

        Expected message exchange:
        Provider    -> Concent:     ForceSubtaskResults
        Concent     -> Provider:    HTTP 202
        Concent     -> Requestor:   ForceSubtaskResults (new timestamp)
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
            side_effect=_get_provider_account_status_true_mock
        ) as is_account_status_positive_true_mock_function:
            with freeze_time("2018-02-05 10:00:31"):
                response_1 = self.client.post(
                    reverse('core:send'),
                    data                                = serialized_force_subtask_results,
                    content_type                        = 'application/octet-stream',
                )

        is_account_status_positive_true_mock_function.assert_called_with(
            client_eth_address=task_to_compute.requestor_ethereum_address,
            pending_value=task_to_compute.price,
        )

        assert len(response_1.content) == 0
        assert response_1.status_code  == 202

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

        with freeze_time("2018-02-05 10:00:29"):
            response_2 = self.client.post(
                reverse('core:receive'),
                data                            = self._create_requestor_auth_message(),
                content_type                    = 'application/octet-stream',
            )
        self._test_response(
            response_2,
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

    def test_requestor_should_not_receive_correct_subtask_results_from_concent_if_asked_concent_after_deadline(self):
        """
        Test if Provider submitted ForceSubtaskResults, Requestor will receive from Concent
        message with correct timestamp if Requestor ask Concent after deadline,
        and then send SubtaskResultsSettled to both Requestor and Provider.

        Exptected message exchange:
        Provider    -> Concent:     ForceSubtaskResults
        Concent     -> Provider:    HTTP 202
        Concent     -> Requestor:   ForceSubtaskResults (new timestamp)
        Concent     -> Provider:    SubtaskResultsSettled
        Concent     -> Requestor:   SubtaskResultsSettled
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
            side_effect=_get_provider_account_status_true_mock
        ) as is_account_status_positive_true_mock_function:
            with freeze_time("2018-02-05 10:00:31"):
                response_1 = self.client.post(
                    reverse('core:send'),
                    data                                = serialized_force_subtask_results,
                    content_type                        = 'application/octet-stream',
                )

        is_account_status_positive_true_mock_function.assert_called_with(
            client_eth_address=task_to_compute.requestor_ethereum_address,
            pending_value=task_to_compute.price,
        )

        assert len(response_1.content) == 0
        assert response_1.status_code  == 202

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

        with freeze_time("2018-02-05 11:00:00"):
            response_2 = self.client.post(
                reverse('core:receive'),
                data                            = self._create_requestor_auth_message(),
                content_type                    = 'application/octet-stream',
            )
        self._test_response(
            response_2,
            status       = 200,
            key          = self.REQUESTOR_PRIVATE_KEY,
            message_type = message.concents.ForceSubtaskResults,
            fields       = {
                'timestamp':                                                 parse_iso_date_to_timestamp("2018-02-05 11:00:00"),
                'ack_report_computed_task.subtask_id':                       'xxyyzz',
                'ack_report_computed_task.report_computed_task.task_to_compute.compute_task_def': compute_task_def,
            }
        )
        self._assert_stored_message_counter_not_increased()

        self._test_undelivered_pending_responses(
            subtask_id                         = 'xxyyzz',
            client_public_key                  = self._get_encoded_provider_public_key(),
            client_public_key_out_of_band      = self._get_encoded_requestor_public_key(),
            expected_pending_responses_receive = [
                PendingResponse.ResponseType.SubtaskResultsSettled,
            ],
            expected_pending_responses_receive_out_of_band = [
                PendingResponse.ResponseType.SubtaskResultsSettled,
            ]
        )

        with freeze_time("2018-02-05 11:00:01"):
            response = self.client.post(
                reverse('core:receive'),
                data                            = self._create_provider_auth_message(),
                content_type                    = 'application/octet-stream',
            )
        self._test_response(
            response,
            status       = 200,
            key          = self.PROVIDER_PRIVATE_KEY,
            message_type = message.concents.SubtaskResultsSettled,
            fields       = {
                'timestamp':                        parse_iso_date_to_timestamp("2018-02-05 11:00:01"),
                'task_to_compute.compute_task_def': compute_task_def,
            }
        )
        self._assert_stored_message_counter_not_increased()

        with freeze_time("2018-02-05 11:00:01"):
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
                'timestamp':                        parse_iso_date_to_timestamp("2018-02-05 11:00:01"),
                'task_to_compute.compute_task_def': compute_task_def,
            }
        )
        self._assert_stored_message_counter_not_increased()

        self._assert_client_count_is_equal(2)

    def test_requestor_sends_subtask_results_accepted_and_concent_should_return_it_to_provider(self):
        """
        Test if Requestor wants submit SubtaskResultsAccepted message,
        Provider should receive it from Concent

        Exptected message exchange:
        Provider    -> Concent:     ForceSubtaskResults
        Concent     -> Requestor:   ForceSubtaskResults
        Requestor   -> Concent:     SubtaskResultsAccepted
        Concent     -> Requestor:   HTTP 202
        Concent     -> Provider:    SubtaskResultsAccepted
        """

        task_to_compute = self._get_deserialized_task_to_compute(
            timestamp   = "2018-02-05 10:00:00",
            deadline    = "2018-02-05 10:00:15",
            task_id     = '2',
            subtask_id  = 'xxyyzz',
        )

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
            side_effect=_get_provider_account_status_true_mock
        ) as is_account_status_positive_true_mock_function:
            with freeze_time("2018-02-05 10:00:30"):
                response_1 = self.client.post(
                    reverse('core:send'),
                    data                                = serialized_force_subtask_results,
                    content_type                        = 'application/octet-stream',
                )

        is_account_status_positive_true_mock_function.assert_called_with(
            client_eth_address=task_to_compute.requestor_ethereum_address,
            pending_value=task_to_compute.price,
        )

        assert len(response_1.content)  == 0
        assert response_1.status_code   == 202
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

        with freeze_time("2018-02-05 10:00:44"):
            response_2 = self.client.post(
                reverse('core:receive'),
                data                            = self._create_requestor_auth_message(),
                content_type                    = 'application/octet-stream',
            )

        self._test_response(
            response_2,
            status          = 200,
            key             = self.REQUESTOR_PRIVATE_KEY,
            message_type    = message.concents.ForceSubtaskResults,
            fields          = {
                'timestamp':                            parse_iso_date_to_timestamp("2018-02-05 10:00:44"),
                'ack_report_computed_task.timestamp':   parse_iso_date_to_timestamp("2018-02-05 10:00:20"),
                'ack_report_computed_task.subtask_id':  'xxyyzz',
            }
        )
        self._assert_stored_message_counter_not_increased()

        serialized_force_subtask_results_response = self._get_serialized_force_subtask_results_response(
            requestor_private_key   = self.REQUESTOR_PRIVATE_KEY,
            timestamp               = "2018-02-05 10:00:43",
            subtask_results_accepted = self._get_deserialized_subtask_results_accepted(
                timestamp               = "2018-02-05 11:00:00",
                payment_ts              = "2018-02-05 11:00:01",
                task_to_compute         = task_to_compute,
            )
        )

        with freeze_time("2018-02-05 10:00:44"):
            self.client.post(
                reverse('core:send'),
                data                                = serialized_force_subtask_results_response,
                content_type                        = 'application/octet-stream',
            )

        self._assert_stored_message_counter_increased(increased_by = 1)
        self._test_subtask_state(
            task_id                      = '2',
            subtask_id                   = 'xxyyzz',
            subtask_state                = Subtask.SubtaskState.ACCEPTED,
            provider_key                 = self._get_encoded_provider_public_key(),
            requestor_key                = self._get_encoded_requestor_public_key(),
            expected_nested_messages={'task_to_compute', 'report_computed_task', 'ack_report_computed_task', 'subtask_results_accepted'},
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

        with freeze_time("2018-02-05 11:00:02"):
            response_3 = self.client.post(
                reverse('core:receive'),
                data                            = self._create_provider_auth_message(),
                content_type                    = 'application/octet-stream',
            )

        self._test_response(
            response_3,
            status          = 200,
            key             = self.PROVIDER_PRIVATE_KEY,
            message_type    = message.concents.ForceSubtaskResultsResponse,
            fields          = {
                'timestamp':                                                    parse_iso_date_to_timestamp("2018-02-05 11:00:02"),
                'subtask_results_accepted.timestamp':                           parse_iso_date_to_timestamp("2018-02-05 11:00:00"),
                'subtask_results_accepted.payment_ts':                          parse_iso_date_to_timestamp("2018-02-05 11:00:01"),
                'subtask_results_accepted.task_to_compute.timestamp':           parse_iso_date_to_timestamp("2018-02-05 10:00:00"),
                'subtask_results_accepted.task_to_compute.compute_task_def':    task_to_compute.compute_task_def,
            }
        )

        self._assert_stored_message_counter_not_increased()

        self._assert_client_count_is_equal(2)

    def test_requestor_sends_subtask_results_rejected_and_concent_should_return_it_to_provider(self):
        """
        Test if Requestor wants submit SubtaskResultsAccepted message,
        Provider should receive it from Concent

        Exptected message exchange:
        Provider    -> Concent:     ForceSubtaskResults
        Concent     -> Requestor:   ForceSubtaskResults
        Requestor   -> Concent:     ForceSubtaskResultsResponse (with SubtaskResultsRejected)
        Concent     -> Requestor:   HTTP 202
        Concent     -> Provider:    ForceSubtaskResultsResponse (with SubtaskResultsRejected)
        """

        task_to_compute = self._get_deserialized_task_to_compute(
            timestamp   = "2018-02-05 10:00:00",
            deadline    = "2018-02-05 10:00:15",
            task_id     = '2',
            subtask_id  = 'xxyyzz',
        )

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
            side_effect=_get_provider_account_status_true_mock
        ) as is_account_status_positive_true_mock_function:
            with freeze_time("2018-02-05 10:00:30"):
                response_1 = self.client.post(
                    reverse('core:send'),
                    data                                = serialized_force_subtask_results,
                    content_type                        = 'application/octet-stream',
                )

        is_account_status_positive_true_mock_function.assert_called_with(
            client_eth_address=task_to_compute.requestor_ethereum_address,
            pending_value=task_to_compute.price,
        )

        assert len(response_1.content)  == 0
        assert response_1.status_code   == 202
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

        with freeze_time("2018-02-05 10:00:44"):
            response_2 = self.client.post(
                reverse('core:receive'),
                data                            = self._create_requestor_auth_message(),
                content_type                    = 'application/octet-stream',
            )

        self._test_response(
            response_2,
            status          = 200,
            key             = self.REQUESTOR_PRIVATE_KEY,
            message_type    = message.concents.ForceSubtaskResults,
            fields          = {
                'timestamp':                            parse_iso_date_to_timestamp("2018-02-05 10:00:44"),
                'ack_report_computed_task.timestamp':   parse_iso_date_to_timestamp("2018-02-05 10:00:20"),
                'ack_report_computed_task.subtask_id':  'xxyyzz',
            }
        )
        self._assert_stored_message_counter_not_increased()

        serialized_force_subtask_results_response = self._get_serialized_force_subtask_results_response(
            requestor_private_key   = self.REQUESTOR_PRIVATE_KEY,
            timestamp               = "2018-02-05 10:00:43",
            subtask_results_rejected = self._get_deserialized_subtask_results_rejected(
                timestamp               = "2018-02-05 10:00:43",
                reason                  = message.tasks.SubtaskResultsRejected.REASON.VerificationNegative,
                report_computed_task    = self._get_deserialized_report_computed_task(
                    timestamp   = "2018-02-05 10:00:44",
                    subtask_id  = 'xxyyzz',
                    task_to_compute = task_to_compute,
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
            task_id                      = '2',
            subtask_id                   = 'xxyyzz',
            subtask_state                = Subtask.SubtaskState.REJECTED,
            provider_key                 = self._get_encoded_provider_public_key(),
            requestor_key                = self._get_encoded_requestor_public_key(),
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

        with freeze_time("2018-02-05 11:00:02"):
            response_3 = self.client.post(
                reverse('core:receive'),
                data                            = self._create_provider_auth_message(),
                content_type                    = 'application/octet-stream',
            )

        self._test_response(
            response_3,
            status          = 200,
            key             = self.PROVIDER_PRIVATE_KEY,
            message_type    = message.concents.ForceSubtaskResultsResponse,
            fields          = {
                'timestamp':                                                parse_iso_date_to_timestamp("2018-02-05 11:00:02"),
                'subtask_results_rejected.timestamp':                       parse_iso_date_to_timestamp("2018-02-05 10:00:43"),
                'subtask_results_rejected.reason':                          message.tasks.SubtaskResultsRejected.REASON.VerificationNegative,
                'subtask_results_rejected.report_computed_task.timestamp':  parse_iso_date_to_timestamp("2018-02-05 10:00:44"),
                'subtask_results_rejected.report_computed_task.subtask_id': 'xxyyzz'
            }
        )
        self._assert_stored_message_counter_not_increased()

        self._assert_client_count_is_equal(2)

    def test_requestor_sends_subtask_results_acceptance_but_provider_does_not_submitted_force_subtask_results_concent_should_reject_it(self):
        """
        Test if Requestor want submit SubtaskResultsAccepted message,
        but Provider doesn't submitted ForceResultsAccepted before

        Exptected message exchange:
        Requestor   -> Concent:     SubtaskResultsAccepted
        Concent     -> Requestor:   HTTP 400
        """

        compute_task_def = self._get_deserialized_compute_task_def(
            task_id     = '2',
            deadline    = "2018-02-05 11:00:00",
        )

        serialized_force_subtask_results_response = self._get_serialized_force_subtask_results_response(
            requestor_private_key   = self.REQUESTOR_PRIVATE_KEY,
            timestamp               = "2018-02-05 11:00:00",
            subtask_results_accepted = self._get_deserialized_subtask_results_accepted(
                timestamp               = "2018-02-05 11:00:00",
                payment_ts              = "2018-02-05 11:00:02",
                task_to_compute         = self._get_deserialized_task_to_compute(
                    timestamp="2018-02-05 10:00:00",
                    compute_task_def=compute_task_def,
                )
            )
        )

        with freeze_time("2018-02-05 11:00:01"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_subtask_results_response,
                content_type                        = 'application/octet-stream',
            )

        self._test_400_response(
            response_1,
            error_code=ErrorCode.QUEUE_COMMUNICATION_NOT_STARTED
        )
        self._assert_stored_message_counter_not_increased()

        self._assert_client_count_is_equal(0)

    def test_requestor_sends_subtask_results_rejection_but_provider_does_not_submitted_force_subtask_results_concent_should_reject_it(self):
        """
        Test if Requestor want submit ForceSubtaskResultsResponse with SubtaskResultsRejected message,
        but Provider doesn't submitted ForceResultsAccepted before


        Exptected message exchange:
        Requestor   -> Concent:     ForceSubtaskResultsResponse with SubtaskResultsRejected
        Concent     -> Requestor:   HTTP 400
        """
        serialized_force_subtask_results_response = self._get_serialized_force_subtask_results_response(
            timestamp               = "2018-02-05 11:00:00",
            requestor_private_key   = self.REQUESTOR_PRIVATE_KEY,
            subtask_results_rejected = self._get_deserialized_subtask_results_rejected(
                timestamp               = "2018-02-05 11:00:00",
                reason                  = message.tasks.SubtaskResultsRejected.REASON.VerificationNegative,
                report_computed_task    = self._get_deserialized_report_computed_task(
                    timestamp   = "2018-02-05 11:00:00",
                    subtask_id  = 'xxyyzz',
                    task_to_compute = self._get_deserialized_task_to_compute(
                        timestamp   = "2018-02-05 11:00:00",
                        deadline    = "2018-02-05 11:00:05",
                        task_id     = 'xxyyzz',
                    )
                )
            )
        )

        with freeze_time("2018-02-05 11:00:01"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                            = serialized_force_subtask_results_response,
                content_type                    = 'application/octet-stream',
            )

        self._test_400_response(
            response_1,
            error_code=ErrorCode.QUEUE_COMMUNICATION_NOT_STARTED
        )
        self._assert_stored_message_counter_not_increased()

        self._assert_client_count_is_equal(0)

    def test_provider_sends_messages_with_wrong_timestamps_concent_should_reject_them(self):
        """
        Test if Provider wants to submit ForceSubtaskResults,
        Concent won't let Provider to submit this message

        Expected message exchange:
        Provider    -> Concent:     ForceSubtaskResults (much too soon)
        Concent     -> Provider:    HTTP 400
        Provider    -> Concent:     ForceSubtaskResults (much too late)
        Concent     -> Provider:    HTTP 400
        """

        serialized_force_subtask_results = self._get_serialized_force_subtask_results(
            timestamp                   = "2018-04-05 10:00:15",
            ack_report_computed_task    = self._get_deserialized_ack_report_computed_task(
                timestamp       = "2018-04-05 10:00:15",
                subtask_id      = "2",
                task_to_compute = self._get_deserialized_task_to_compute(
                    timestamp   = "2018-04-05 10:00:00",
                    deadline    = "2018-04-05 10:00:10",
                    task_id     = '2',
                )
            )
        )

        with freeze_time("2018-03-05 10:00:30"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_subtask_results,
                content_type                        = 'application/octet-stream',
            )

        self._test_400_response(response_1)
        self._assert_stored_message_counter_not_increased()

        serialized_force_subtask_results = self._get_serialized_force_subtask_results(
            timestamp                   = "2018-04-05 10:00:15",
            ack_report_computed_task    = self._get_deserialized_ack_report_computed_task(
                timestamp       = "2018-04-05 10:00:15",
                subtask_id      = '2',
                task_to_compute = self._get_deserialized_task_to_compute(
                    timestamp   = "2018-04-05 10:00:00",
                    deadline    = "2018-04-05 10:00:10",
                    task_id     = '2',
                )
            )
        )

        with freeze_time("2018-03-05 10:00:40"):
            response_2 = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_subtask_results,
                content_type                        = 'application/octet-stream',
            )

        self._test_400_response(response_2)
        self._assert_stored_message_counter_not_increased()

        self._assert_client_count_is_equal(0)

    def test_requestor_sends_messages_with_wrong_timestamps_concent_should_return_http_400(self):
        """
        Test if Requestor want to submit SubtaskResultsAccepted and SubtaskResultsRejected,
        Concent won't let Requestor to submit this messages

        Expected message exchange:
        Provider    -> Concent:     ForceSubtaskResults
        Concent     -> Provider:    HTTP 202
        Requestor   -> Concent:     SubtaskResultsAccepted (future timestamp)
        Concent     -> Requestor:   HTTP 400
        Requestor   -> Concent:     SubtaskResultsAccepted (past timestamp)
        Concent     -> Requestor:   HTTP 400
        Requestor   -> Concent:     SubtaskResultsRejected (future timestamp)
        Concent     -> Requestor:   HTTP 400
        Requestor   -> Concent:     SubtaskResultsRejected (past timestamp)
        Concent     -> Requestor:   HTTP 400
        """

        compute_task_def = self._get_deserialized_compute_task_def(
            task_id     = '2',
            subtask_id  = "xxyyzz",
            deadline    = "2018-02-05 10:00:15",
        )

        task_to_compute = self._get_deserialized_task_to_compute(
            timestamp           = "2018-02-05 10:00:00",
            compute_task_def    = compute_task_def,
        )

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
            side_effect=_get_provider_account_status_true_mock
        ) as is_account_status_positive_true_mock_function:
            with freeze_time("2018-02-05 10:00:30"):
                response_1 = self.client.post(
                    reverse('core:send'),
                    data                                = serialized_force_subtask_results,
                    content_type                        = 'application/octet-stream',
                )

        is_account_status_positive_true_mock_function.assert_called_with(
            client_eth_address=task_to_compute.requestor_ethereum_address,
            pending_value=task_to_compute.price,
        )

        assert len(response_1.content)  == 0
        assert response_1.status_code   == 202
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

        compute_task_def = self._get_deserialized_compute_task_def(
            task_id     = '2',
            deadline    = "2018-02-05 11:00:00",
        )

        task_to_compute = self._get_deserialized_task_to_compute(
            timestamp           = "2018-02-05 10:00:00",
            compute_task_def    = compute_task_def,
        )

        serialized_force_subtask_results_response = self._get_serialized_force_subtask_results_response(
            requestor_private_key   = self.REQUESTOR_PRIVATE_KEY,
            timestamp               = "2018-02-05 12:00:00",
            subtask_results_accepted = self._get_deserialized_subtask_results_accepted(
                timestamp               = "2018-02-05 12:00:00",
                payment_ts              = "2018-02-05 12:00:01",
                task_to_compute         = task_to_compute
            ),
        )

        with freeze_time("2018-02-05 11:00:00"):
            response_2 = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_subtask_results_response,
                content_type                        = 'application/octet-stream',
            )

        self._test_400_response(response_2)
        self._assert_stored_message_counter_not_increased()

        compute_task_def = self._get_deserialized_compute_task_def(
            task_id     = '2',
            deadline    = "2018-02-05 10:00:00",
        )

        task_to_compute = self._get_deserialized_task_to_compute(
            timestamp           = "2018-02-05 9:00:00",
            compute_task_def    = compute_task_def,
        )

        serialized_force_subtask_results_response = self._get_serialized_force_subtask_results_response(
            requestor_private_key   = self.REQUESTOR_PRIVATE_KEY,
            timestamp               = "2018-02-05 10:00:00",
            subtask_results_accepted = self._get_deserialized_subtask_results_accepted(
                timestamp               = "2018-02-05 10:00:00",
                payment_ts              = "2018-02-05 10:00:01",
                task_to_compute         = task_to_compute
            ),
        )

        with freeze_time("2018-02-05 11:00:00"):
            response_3 = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_subtask_results_response,
                content_type                        = 'application/octet-stream',
            )

        self._test_400_response(response_3)
        self._assert_stored_message_counter_not_increased()

        task_to_compute = self._get_deserialized_task_to_compute(
            timestamp   = "2018-02-05 12:00:00",
            deadline    = "2018-02-05 12:00:05",
            task_id     = '2',
        )

        serialized_force_subtask_results_response = self._get_serialized_force_subtask_results_response(
            requestor_private_key   = self.REQUESTOR_PRIVATE_KEY,
            timestamp               = "2018-02-05 12:00:00",
            subtask_results_rejected = self._get_deserialized_subtask_results_rejected(
                timestamp               = "2018-02-05 12:00:00",
                reason                  = message.tasks.SubtaskResultsRejected.REASON.VerificationNegative,
                report_computed_task    = self._get_deserialized_report_computed_task(
                    timestamp   = "2018-02-05 12:00:00",
                    subtask_id  = '2',
                    task_to_compute = task_to_compute
                )
            )
        )

        with freeze_time("2018-02-05 11:00:00"):
            response_4 = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_subtask_results_response,
                content_type                        = 'application/octet-stream',
            )

        self._test_400_response(response_4)
        self._assert_stored_message_counter_not_increased()

        task_to_compute = self._get_deserialized_task_to_compute(
            timestamp   = "2018-02-05 10:00:00",
            deadline    = "2018-02-05 10:00:05",
            task_id     = '2',
        )

        serialized_force_subtask_results_response = self._get_serialized_force_subtask_results_response(
            requestor_private_key   = self.REQUESTOR_PRIVATE_KEY,
            timestamp               = "2018-02-05 10:00:00",
            subtask_results_rejected = self._get_deserialized_subtask_results_rejected(
                timestamp               = "2018-02-05 10:00:00",
                reason                  = message.tasks.SubtaskResultsRejected.REASON.VerificationNegative,
                report_computed_task    = self._get_deserialized_report_computed_task(
                    timestamp   = "2018-02-05 12:00:00",
                    subtask_id  = '2',
                    task_to_compute = task_to_compute
                )
            )
        )

        with freeze_time("2018-02-05 11:00:00"):
            response_5 = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_subtask_results_response,
                content_type                        = 'application/octet-stream',
            )

        self._test_400_response(response_5)
        self._assert_stored_message_counter_not_increased()

        self._assert_client_count_is_equal(2)

    def test_requestor_or_provider_send_message_with_wrong_nested_message_type_concent_should_return_http_400(self):
        """
        Test if Provider want to submit ForceSubtaskResults with AckReportComputedTask with nested
        CannotComputeTask insted of TaskToCompute

        Expected message exchange:
        Provider    -> Concent:     ForceSubtaskResults
        Concent     -> Provider:    HTTP 400
        """

        # This has to be done manually, otherwise will fail when signing ReportComputedTask
        with freeze_time("2018-02-05 10:00:15"):
            serialized_force_subtask_results = self._get_serialized_force_subtask_results(
                ack_report_computed_task = message.AckReportComputedTask(
                    report_computed_task=(
                        message.ReportComputedTask(
                            task_to_compute=message.CannotComputeTask()
                        )
                    )
                )
            )

        with freeze_time("2018-02-05 10:00:30"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_subtask_results,
                content_type                        = 'application/octet-stream',
            )

        self._test_400_response(response_1)
        self._assert_stored_message_counter_not_increased()

        self._assert_client_count_is_equal(0)

    def test_subtask_results_accepted_without_task_to_compute_should_return_http_400(self):
        """
        Test if Provider want to submit ForceSubtaskResults with SubtaskResultsAccepted without TaskToCompute.

        Expected message exchange:
        Requestor   -> Concent:     ForceSubtaskResultsResponse
        Concent     -> Provider:    HTTP 400
        """

        serialized_force_subtask_results_response = self._get_serialized_force_subtask_results_response(
            requestor_private_key=self.REQUESTOR_PRIVATE_KEY,
            subtask_results_accepted=self._get_deserialized_subtask_results_accepted(
                payment_ts="2018-02-05 11:00:01",
                task_to_compute=None
            )
        )

        response_1 = self.client.post(
            reverse('core:send'),
            data= serialized_force_subtask_results_response,
            content_type= 'application/octet-stream',
            HTTP_CONCENT_CLIENT_PUBLIC_KEY= self._get_encoded_requestor_public_key(),
            HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY=self._get_encoded_provider_public_key(),
        )

        self._test_400_response(
            response_1,
            error_code=ErrorCode.MESSAGE_INVALID
        )
        self._assert_stored_message_counter_not_increased()

        self._assert_client_count_is_equal(0)

    def test_subtask_results_rejected_without_task_to_compute_should_return_http_400(self):
        """
        Test if Provider want to submit ForceSubtaskResults with SubtaskResultsRejected without TaskToCompute.

        Expected message exchange:
        Requestor   -> Concent:     ForceSubtaskResultsResponse
        Concent     -> Provider:    HTTP 400
        """

        serialized_force_subtask_results_response = self._get_serialized_force_subtask_results_response(
            requestor_private_key=self.REQUESTOR_PRIVATE_KEY,
            subtask_results_rejected=self._get_deserialized_subtask_results_rejected(
                reason=message.tasks.SubtaskResultsRejected.REASON.VerificationNegative,
                report_computed_task=message.ReportComputedTask()
            )
        )

        response_1 = self.client.post(
            reverse('core:send'),
            data= serialized_force_subtask_results_response,
            content_type= 'application/octet-stream',
            HTTP_CONCENT_CLIENT_PUBLIC_KEY=self._get_encoded_requestor_public_key(),
            HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY=self._get_encoded_provider_public_key(),
        )

        self._test_400_response(
            response_1,
            error_code=ErrorCode.MESSAGE_INVALID
        )
        self._assert_stored_message_counter_not_increased()

        self._assert_client_count_is_equal(0)

    def test_requestor_doesnt_provide_response_should_end_with_subtask_results_settled_received_from_concent(self):
        """
        Expected message exchange:
        Provider    -> Concent:     ForceSubtaskResults
        Concent     -> Provider:    HTTP 202
        Concent     -> Requestor:   ForceSubtaskResults
        Requestor   -> Concent:     no response
        Concent     -> Provider:    SubtaskResultsSettled
        Concent     -> Provider:    HTTP 204
        Concent     -> Requestor:   SubtaskResultsSettled
        Concent     -> Requestor:   HTTP 204
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

        serialized_force_subtask_results = self._get_serialized_force_subtask_results(
            timestamp="2018-02-05 10:00:30",
            ack_report_computed_task=self._get_deserialized_ack_report_computed_task(
                timestamp="2018-02-05 10:00:25",
                subtask_id="xxyyzz",
                task_to_compute=task_to_compute,
                signer_private_key=self.REQUESTOR_PRIVATE_KEY,
            )
        )

        with mock.patch(
            'core.message_handlers.payments_service.is_account_status_positive',
            side_effect=_get_provider_account_status_true_mock
        ) as is_account_status_positive_true_mock_function:
            with freeze_time("2018-02-05 10:00:30"):
                response_1 = self.client.post(
                    reverse('core:send'),
                    data                                = serialized_force_subtask_results,
                    content_type                        = 'application/octet-stream',
                )

        is_account_status_positive_true_mock_function.assert_called_with(
            client_eth_address=task_to_compute.requestor_ethereum_address,
            pending_value=task_to_compute.price,
        )

        assert len(response_1.content) == 0
        assert response_1.status_code  == 202

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

        with freeze_time("2018-02-05 10:00:31"):
            response_2 = self.client.post(
                reverse('core:receive'),
                data                            = self._create_requestor_auth_message(),
                content_type                    = 'application/octet-stream',
            )
        self._test_response(
            response_2,
            status       = 200,
            key          = self.REQUESTOR_PRIVATE_KEY,
            message_type = message.concents.ForceSubtaskResults,
            fields       = {
                'timestamp':                                                 parse_iso_date_to_timestamp("2018-02-05 10:00:31"),
                'ack_report_computed_task.subtask_id':                       'xxyyzz',
                'ack_report_computed_task.report_computed_task.task_to_compute.compute_task_def': compute_task_def,
            }
        )
        self._assert_stored_message_counter_not_increased()

        with freeze_time("2018-02-05 10:00:51"):
            response_3a = self.client.post(
                reverse('core:receive'),
                data=self._create_provider_auth_message(),
                content_type='application/octet-stream',
            )

        is_account_status_positive_true_mock_function.assert_called_with(
            client_eth_address=task_to_compute.requestor_ethereum_address,
            pending_value=task_to_compute.price,
        )

        self._test_response(
            response_3a,
            status       = 200,
            key          = self.PROVIDER_PRIVATE_KEY,
            message_type = message.concents.SubtaskResultsSettled,
            fields       = {
                'timestamp':                        parse_iso_date_to_timestamp("2018-02-05 10:00:51"),
                'task_to_compute.compute_task_def': compute_task_def,
            }
        )
        self._assert_stored_message_counter_not_increased()
        self._test_subtask_state(
            task_id                     = '2',
            subtask_id                  = 'xxyyzz',
            subtask_state               = Subtask.SubtaskState.ACCEPTED,
            provider_key                = self._get_encoded_provider_public_key(),
            requestor_key               = self._get_encoded_requestor_public_key(),
            expected_nested_messages={'task_to_compute', 'report_computed_task', 'ack_report_computed_task'},
            next_deadline               = None,
        )
        self._test_undelivered_pending_responses(
            subtask_id                         = 'xxyyzz',
            client_public_key                  = self._get_encoded_provider_public_key(),
            client_public_key_out_of_band      = self._get_encoded_requestor_public_key(),
            expected_pending_responses_receive_out_of_band = [
                PendingResponse.ResponseType.SubtaskResultsSettled,
            ]
        )

        with freeze_time("2018-02-05 10:00:52"):
            response_3b = self.client.post(
                reverse('core:receive'),
                data=self._create_provider_auth_message(),
                content_type='application/octet-stream',
            )

        self._test_204_response(response_3b)
        self._assert_stored_message_counter_not_increased()

        with freeze_time("2018-02-05 10:00:51"):
            response_4a = self.client.post(
                reverse('core:receive_out_of_band'),
                data                            = self._create_requestor_auth_message(),
                content_type                    = 'application/octet-stream',
            )
        self._test_response(
            response_4a,
            status       = 200,
            key          = self.REQUESTOR_PRIVATE_KEY,
            message_type = message.concents.SubtaskResultsSettled,
            fields       = {
                'timestamp':                        parse_iso_date_to_timestamp("2018-02-05 10:00:51"),
                'task_to_compute.compute_task_def': compute_task_def,
            }
        )
        self._assert_stored_message_counter_not_increased()

        with freeze_time("2018-02-05 10:00:52"):
            response_4b = self.client.post(
                reverse('core:receive_out_of_band'),
                data                            = self._create_requestor_auth_message(),
                content_type                    = 'application/octet-stream',
            )
        self._test_204_response(response_4b)
        self._assert_stored_message_counter_not_increased()

        self._assert_client_count_is_equal(2)

    def test_requestor_doesnt_provide_response_should_end_with_subtask_results_settled_received_from_concent_different_configuration(self):
        """
        Expected message exchange:
        Provider    -> Concent:     ForceSubtaskResults
        Concent     -> Provider:    HTTP 202
        Concent     -> Requestor:   ForceSubtaskResults
        Requestor   -> Concent:     no response
        Concent     -> Requestor:   SubtaskResultsSettled
        Concent     -> Provider:    SubtaskResultsSettled
        Concent     -> Requestor:   HTTP 204
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

        serialized_force_subtask_results = self._get_serialized_force_subtask_results(
            timestamp="2018-02-05 10:00:30",
            ack_report_computed_task=self._get_deserialized_ack_report_computed_task(
                timestamp="2018-02-05 10:00:25",
                subtask_id="xxyyzz",
                task_to_compute=task_to_compute,
                signer_private_key=self.REQUESTOR_PRIVATE_KEY,
            )
        )

        with mock.patch(
            'core.message_handlers.payments_service.is_account_status_positive',
            side_effect=_get_provider_account_status_true_mock
        ) as is_account_status_positive_true_mock_function:
            with freeze_time("2018-02-05 10:00:30"):
                response_1 = self.client.post(
                    reverse('core:send'),
                    data                                = serialized_force_subtask_results,
                    content_type                        = 'application/octet-stream',
                )

        is_account_status_positive_true_mock_function.assert_called_with(
            client_eth_address=task_to_compute.requestor_ethereum_address,
            pending_value=task_to_compute.price,
        )

        assert len(response_1.content) == 0
        assert response_1.status_code  == 202

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

        with freeze_time("2018-02-05 10:00:31"):
            response_2 = self.client.post(
                reverse('core:receive'),
                data                            = self._create_requestor_auth_message(),
                content_type                    = 'application/octet-stream',
            )
        self._test_response(
            response_2,
            status       = 200,
            key          = self.REQUESTOR_PRIVATE_KEY,
            message_type = message.concents.ForceSubtaskResults,
            fields       = {
                'timestamp':                                                 parse_iso_date_to_timestamp("2018-02-05 10:00:31"),
                'ack_report_computed_task.subtask_id':                       'xxyyzz',
                'ack_report_computed_task.report_computed_task.task_to_compute.compute_task_def': compute_task_def,
            }
        )
        self._assert_stored_message_counter_not_increased()

        with freeze_time("2018-02-05 10:00:51"):
            response_3 = self.client.post(
                reverse('core:receive_out_of_band'),
                data                            = self._create_requestor_auth_message(),
                content_type                    = 'application/octet-stream',
            )
        self._test_response(
            response_3,
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
            task_id                      = '2',
            subtask_id                   = 'xxyyzz',
            subtask_state                = Subtask.SubtaskState.ACCEPTED,
            provider_key                 = self._get_encoded_provider_public_key(),
            requestor_key                = self._get_encoded_requestor_public_key(),
            expected_nested_messages={'task_to_compute', 'report_computed_task', 'ack_report_computed_task'},
            next_deadline                = None,
        )
        self._test_undelivered_pending_responses(
            subtask_id                         = 'xxyyzz',
            client_public_key                  = self._get_encoded_provider_public_key(),
            expected_pending_responses_receive = [
                PendingResponse.ResponseType.SubtaskResultsSettled,
            ]
        )

        with freeze_time("2018-02-05 10:00:51"):
            response_4 = self.client.post(
                reverse('core:receive'),
                data=self._create_provider_auth_message(),
                content_type='application/octet-stream',
            )

        self._test_response(
            response_4,
            status       = 200,
            key          = self.PROVIDER_PRIVATE_KEY,
            message_type = message.concents.SubtaskResultsSettled,
            fields       = {
                'timestamp':                        parse_iso_date_to_timestamp("2018-02-05 10:00:51"),
                'task_to_compute.compute_task_def': compute_task_def,
            }
        )
        self._assert_stored_message_counter_not_increased()

        with freeze_time("2018-02-05 10:00:52"):
            response_5 = self.client.post(
                reverse('core:receive_out_of_band'),
                data                            = self._create_requestor_auth_message(),
                content_type                    = 'application/octet-stream',
            )
        self._test_204_response(response_5)
        self._assert_stored_message_counter_not_increased()

        self._assert_client_count_is_equal(2)

    def test_requestor_send_again_subtask_results_accepted_or_rejected_when_message_already_accepted_concent_should_return_http_400(self):
        """
        Test if Requestor wants to send  SubtaskResultsAccepted or SubtaskResultsRejected
        when already SubtaskResultsAccepted was accepted via Concent,
        Concent should return HTTP 400.

        Expected message exchange:
        Requestor   -> Concent: SubtaskResultsAccepted
        Concent     -> Requestor: HTTP 400
        Requestor   -> Concent: SubtaskResultsRejected
        Concent     -> Requestor: HTTP 400
        """

        deserialized_force_subtask_results = self._get_deserialized_force_subtask_results(
            timestamp                   = "2018-02-05 10:00:15",
            ack_report_computed_task    = self._get_deserialized_ack_report_computed_task(
                subtask_id      = "xxyyzz",
                task_to_compute = self._get_deserialized_task_to_compute(
                    timestamp   = "2018-02-05 10:00:00",
                    deadline    = "2018-02-05 10:00:10",
                    task_id     = '2',
                )
            )
        )

        compute_task_def = self._get_deserialized_compute_task_def(
            task_id     = '2',
            deadline    = "2018-02-05 11:00:00",
        )

        task_to_compute = deserialized_force_subtask_results.ack_report_computed_task.report_computed_task.task_to_compute  # pylint: disable=no-member,

        subtask = store_or_update_subtask(
            task_id=task_to_compute.compute_task_def['task_id'],
            subtask_id=task_to_compute.compute_task_def['subtask_id'],
            provider_public_key=self.PROVIDER_PUBLIC_KEY,
            requestor_public_key=self.REQUESTOR_PUBLIC_KEY,
            state=Subtask.SubtaskState.ACCEPTED,
            report_computed_task=deserialized_force_subtask_results.ack_report_computed_task.report_computed_task,  # pylint: disable=no-member,
            task_to_compute=task_to_compute,
            subtask_results_accepted=self._get_deserialized_subtask_results_accepted(
                timestamp   = "2018-02-05 11:00:00",
                payment_ts = "2018-02-05 11:00:01",
                task_to_compute = self._get_deserialized_task_to_compute(
                    timestamp           = "2018-02-05 10:00:00",
                    compute_task_def    = compute_task_def,
                ),
            ),
        )
        subtask.state = Subtask.SubtaskState.FORCING_ACCEPTANCE.name  # pylint: disable=no-member,
        subtask.save()  # full_clean() is omitted here on purpose

        self._assert_stored_message_counter_increased(increased_by=3)

        serialized_force_subtask_results_response = self._get_serialized_force_subtask_results_response(
            requestor_private_key   = self.REQUESTOR_PRIVATE_KEY,
            timestamp               = "2018-02-05 11:00:01",
            subtask_results_accepted = self._get_deserialized_subtask_results_accepted(
                timestamp               = "2018-02-05 11:00:01",
                payment_ts              = "2018-02-05 11:00:02",
                task_to_compute = self._get_deserialized_task_to_compute(
                    timestamp           = "2018-02-05 10:00:00",
                    compute_task_def    = compute_task_def,
                ),
            )
        )

        with freeze_time("2018-02-05 11:00:02"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                            = serialized_force_subtask_results_response,
                content_type                    = 'application/octet-stream',
            )

        self._test_400_response(
            response_1,
            error_code=ErrorCode.SUBTASK_DUPLICATE_REQUEST
        )
        self._assert_stored_message_counter_not_increased()

        serialized_force_subtask_results_response = self._get_serialized_force_subtask_results_response(
            requestor_private_key   = self.REQUESTOR_PRIVATE_KEY,
            timestamp               = "2018-02-05 11:00:01",
            subtask_results_rejected = self._get_deserialized_subtask_results_rejected(
                timestamp               = "2018-02-05 11:00:01",
                reason                  = message.tasks.SubtaskResultsRejected.REASON.VerificationNegative,
                report_computed_task    = self._get_deserialized_report_computed_task(
                    timestamp   = "2018-02-05 11:00:01",
                    subtask_id  = '2',
                    task_to_compute = self._get_deserialized_task_to_compute(
                        timestamp   = "2018-02-05 11:00:01",
                        deadline    = "2018-02-05 11:00:06",
                        task_id     = '2',
                    )
                )
            )
        )

        with freeze_time("2018-02-05 11:00:02"):
            response_2 = self.client.post(
                reverse('core:send'),
                data                            = serialized_force_subtask_results_response,
                content_type                    = 'application/octet-stream',
            )

        self._test_400_response(
            response_2,
            error_code=ErrorCode.SUBTASK_DUPLICATE_REQUEST
        )
        self._assert_stored_message_counter_not_increased()

        self._assert_client_count_is_equal(2)

    def test_requestor_send_again_subtask_results_accepted_or_rejected_when_message_already_rejected_concent_should_return_http_400(self):
        """
        Test if Requestor wants to send SubtaskResultsAccepted or SubtaskResultsRejected
        when already SubtaskResultsAccepted was accepted via Concent,
        Concent should return HTTP 400.

        Expected message exchange:
        Requestor   -> Concent: SubtaskResultsAccepted
        Concent     -> Requestor: HTTP 400
        Requestor   -> Concent: SubtaskResultsRejected
        Concent     -> Requestor: HTTP 400
        """
        deserialized_force_subtask_results = self._get_deserialized_force_subtask_results(
            timestamp                   = "2018-02-05 10:00:15",
            ack_report_computed_task    = self._get_deserialized_ack_report_computed_task(
                subtask_id      = "xxyyzz",
                task_to_compute = self._get_deserialized_task_to_compute(
                    timestamp   = "2018-02-05 10:00:00",
                    deadline    = "2018-02-05 10:00:10",
                    task_id     = '2',
                )
            )
        )

        compute_task_def = self._get_deserialized_compute_task_def(
            task_id     = '2',
            deadline    = "2018-02-05 11:00:00",
        )

        task_to_compute = deserialized_force_subtask_results.ack_report_computed_task.report_computed_task.task_to_compute  # pylint: disable=no-member,

        subtask = store_or_update_subtask(
            task_id=task_to_compute.compute_task_def['task_id'],
            subtask_id=task_to_compute.compute_task_def['subtask_id'],
            provider_public_key=self.PROVIDER_PUBLIC_KEY,
            requestor_public_key=self.REQUESTOR_PUBLIC_KEY,
            state=Subtask.SubtaskState.ACCEPTED,
            report_computed_task=deserialized_force_subtask_results.ack_report_computed_task.report_computed_task,  # pylint: disable=no-member,
            task_to_compute=task_to_compute,
            subtask_results_rejected=self._get_deserialized_subtask_results_rejected(
                timestamp   = "2018-02-05 11:00:00",
                reason=message.tasks.SubtaskResultsRejected.REASON.VerificationNegative
            ),
        )
        subtask.state = Subtask.SubtaskState.FORCING_ACCEPTANCE.name  # pylint: disable=no-member,
        subtask.save()  # full_clean() is omitted here on purpose

        self._assert_stored_message_counter_increased(increased_by=3)
        serialized_force_subtask_results_response = self._get_serialized_force_subtask_results_response(
            requestor_private_key   = self.REQUESTOR_PRIVATE_KEY,
            timestamp               = "2018-02-05 11:00:01",
            subtask_results_accepted = self._get_deserialized_subtask_results_accepted(
                timestamp               = "2018-02-05 11:00:01",
                payment_ts              = "2018-02-05 11:00:02",
                task_to_compute         = self._get_deserialized_task_to_compute(
                    timestamp           = "2018-02-05 10:00:00",
                    compute_task_def    = compute_task_def,
                ),
            )
        )

        with freeze_time("2018-02-05 11:00:02"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                            = serialized_force_subtask_results_response,
                content_type                    = 'application/octet-stream',
            )
        self._test_400_response(
            response_1,
            error_code=ErrorCode.SUBTASK_DUPLICATE_REQUEST
        )
        self._assert_stored_message_counter_not_increased()

        serialized_force_subtask_results_response = self._get_serialized_force_subtask_results_response(
            requestor_private_key   = self.REQUESTOR_PRIVATE_KEY,
            timestamp               = "2018-02-05 11:00:01",
            subtask_results_rejected = self._get_deserialized_subtask_results_rejected(
                timestamp               = "2018-02-05 11:00:01",
                reason                  = message.tasks.SubtaskResultsRejected.REASON.VerificationNegative,
                report_computed_task    = self._get_deserialized_report_computed_task(
                    timestamp   = "2018-02-05 11:00:01",
                    subtask_id  = '2',
                    task_to_compute = self._get_deserialized_task_to_compute(
                        timestamp   = "2018-02-05 11:00:01",
                        deadline    = "2018-02-05 11:00:06",
                        task_id     = '2',
                    )
                )
            )
        )

        with freeze_time("2018-02-05 11:00:02"):
            response_2 = self.client.post(
                reverse('core:send'),
                data                            = serialized_force_subtask_results_response,
                content_type                    = 'application/octet-stream',
            )

        self._test_400_response(
            response_2,
            error_code=ErrorCode.SUBTASK_DUPLICATE_REQUEST
        )
        self._assert_stored_message_counter_not_increased()

        self._assert_client_count_is_equal(2)

    def test_requestor_send_force_subtask_results_response_without_accepted_or_rejected_should_return_http_400(self):
        """
        Test if Requestor wants to send ForceSubtaskResultsResponse without SubtaskResultsAccepted
        or SubtaskResultsRejected then Concent should return HTTP 400 as not supported.

        Expected message exchange:
        Requestor   -> Concent: ForceSubtaskResultsResponse (empty)
        Concent     -> Requestor: HTTP 400
        """
        serialized_force_subtask_results_response = self._get_serialized_force_subtask_results_response(
            requestor_private_key = self.REQUESTOR_PRIVATE_KEY,
            timestamp             = "2018-02-05 11:00:01",
        )

        with freeze_time("2018-02-05 11:00:02"):
            response_1 = self.client.post(
                reverse('core:send'),
                data                           = serialized_force_subtask_results_response,
                content_type                   = 'application/octet-stream',
            )

        self._test_400_response(
            response_1,
            error_code=ErrorCode.MESSAGE_UNEXPECTED
        )
        self._assert_stored_message_counter_not_increased()

        self._assert_client_count_is_equal(0)

    def test_that_force_subtask_results_response_with_no_subtask_results_rejected_or_accepted_should_return_http400(self):
        force_subtask_results_response = self._get_deserialized_force_subtask_results_response()
        with self.assertRaises(Http400):
            handle_send_force_subtask_results_response(force_subtask_results_response)

    def test_that_force_subtask_results_response_with_both_subtask_results_rejected_and_accepted_should_return_http400(self):
        force_subtask_results_response = self._get_deserialized_force_subtask_results_response(
            subtask_results_accepted=self._get_deserialized_subtask_results_accepted(
                task_to_compute=self._get_deserialized_task_to_compute(),
            ),
            subtask_results_rejected=self._get_deserialized_subtask_results_rejected(
                reason=message.tasks.SubtaskResultsRejected.REASON.VerificationNegative),
        )
        with self.assertRaises(Http400):
            handle_send_force_subtask_results_response(force_subtask_results_response)
