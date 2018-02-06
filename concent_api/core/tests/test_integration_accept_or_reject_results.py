import mock

from django.test            import override_settings
from django.urls            import reverse
from freezegun              import freeze_time
from golem_messages         import message

from core.models            import Message
from core.models            import ReceiveStatus
from core.tests.utils       import ConcentIntegrationTestCase
from utils.testing_helpers  import generate_ecc_key_pair


(CONCENT_PRIVATE_KEY, CONCENT_PUBLIC_KEY) = generate_ecc_key_pair()


def _get_provider_account_status_true_mock(_):
    return True


def _get_provider_account_status_false_mock(_):
    return False


@override_settings(
    CONCENT_PRIVATE_KEY    = CONCENT_PRIVATE_KEY,
    CONCENT_PUBLIC_KEY     = CONCENT_PUBLIC_KEY,
    CONCENT_MESSAGING_TIME = 10,  # seconds
    FORCE_ACCEPTANCE_TIME  = 10,  # seconds
)
class GetTaskResultIntegrationTest(ConcentIntegrationTestCase):

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

        # STEP 1: Provider forces subtask results via Concent.
        # Request is processed correctly.
        serialized_force_subtask_results = self._get_serialized_force_subtask_results(
            timestamp                   = "2018-02-05 10:00:15",
            ack_report_computed_task    = self._get_deserialized_ack_report_computed_task(
                timestamp       = "2018-02-05 10:00:15",
                subtask_id      = "xxyyzz",
                task_to_compute = self._get_deserialized_task_to_compute(
                    timestamp   = "2018-02-05 10:00:00",
                    deadline    = "2018-02-05 10:00:10",
                    task_id     = '2',
                )
            )
        )

        with mock.patch('core.views.is_provider_account_status_positive', _get_provider_account_status_true_mock):
            with freeze_time("2018-02-05 10:00:25"):
                response_1 = self.client.post(
                    reverse('core:send'),
                    data                                = serialized_force_subtask_results,
                    content_type                        = 'application/octet-stream',
                    HTTP_CONCENT_CLIENT_PUBLIC_KEY      = self._get_encoded_provider_public_key(),
                )

        assert len(response_1.content)  == 0
        assert response_1.status_code   == 202

        self._test_database_objects(
            last_object_type         = message.concents.ForceSubtaskResults,
            task_id                  = '2',
            receive_delivered_status = False,
        )

        # STEP 2: Provider again forces subtask results via Concent with message with the same task_id.
        # Request is refused.
        with mock.patch('core.views.is_provider_account_status_positive', _get_provider_account_status_true_mock):
            with freeze_time("2018-02-05 10:00:31"):
                response_2 = self.client.post(
                    reverse('core:send'),
                    data                                = serialized_force_subtask_results,
                    content_type                        = 'application/octet-stream',
                    HTTP_CONCENT_CLIENT_PUBLIC_KEY      = self._get_encoded_provider_public_key(),
                )

        self._test_response(
            response_2,
            status       = 200,
            key          = self.PROVIDER_PRIVATE_KEY,
            message_type = message.concents.ServiceRefused,
            fields       = {
                'reason':    message.concents.ServiceRefused.REASON.DuplicateRequest,
                'timestamp': self._parse_iso_date_to_timestamp("2018-02-05 10:00:31"),
            }
        )

    def test_provider_forces_subtask_results_with_not_enough_funds_on_this_account_concent_should_refuse(self):
        """
        Test if on provider ForceSubtaskResult message Concent will return ServiceRefused
        if provider doesn't have enough funds on his account.

        Expected message exchange:
        Provider    -> Concent:     ForceSubtaskResults
        Concent     -> Provider:    ServiceRefused
        """

        # STEP 1: Provider forces subtask results via Concent.
        # Concent returns ServiceRefused.
        serialized_force_subtask_results = self._get_serialized_force_subtask_results(
            timestamp = "2018-02-05 10:00:25"
        )

        with mock.patch('core.views.is_provider_account_status_positive', _get_provider_account_status_false_mock):
            with freeze_time("2018-02-05 10:00:35"):
                response_1 = self.client.post(
                    reverse('core:send'),
                    data                            = serialized_force_subtask_results,
                    content_type                    = 'application/octet-stream',
                    HTTP_CONCENT_CLIENT_PUBLIC_KEY  = self._get_encoded_provider_public_key(),
                )

        self.assertEqual(Message.objects.last(), None)

        self._test_response(
            response_1,
            status       = 200,
            key          = self.PROVIDER_PRIVATE_KEY,
            message_type = message.concents.ServiceRefused,
            fields       = {
                'reason':       message.concents.ServiceRefused.REASON.TooSmallProviderDeposit,
                'timestamp':    self._parse_iso_date_to_timestamp("2018-02-05 10:00:35")
            }
        )

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

        # STEP 1: Provider forces subtask results via Concent.
        # Concent return ForceSubtaskResultRejected because message from Provider was sent too soon.

        serialized_force_subtask_results = self._get_serialized_force_subtask_results(
            timestamp                   = "2018-03-05 10:00:15",
            ack_report_computed_task    = self._get_deserialized_ack_report_computed_task(
                timestamp       = "2018-03-05 10:00:15",
                subtask_id      = "2",
                task_to_compute = self._get_deserialized_task_to_compute(
                    timestamp   = "2018-02-05 10:00:00",
                    deadline    = "2018-02-05 10:00:10",
                    task_id     = '2',
                )
            )
        )

        with mock.patch('core.views.is_provider_account_status_positive', _get_provider_account_status_true_mock):
            with freeze_time("2018-03-05 10:00:24"):
                response_1 = self.client.post(
                    reverse('core:send'),
                    data                                = serialized_force_subtask_results,
                    content_type                        = 'application/octet-stream',
                    HTTP_CONCENT_CLIENT_PUBLIC_KEY      = self._get_encoded_provider_public_key(),
                )

        self._test_response(
            response_1,
            status       = 200,
            key          = self.PROVIDER_PRIVATE_KEY,
            message_type = message.concents.ForceSubtaskResultsRejected,
            fields       = {
                'reason':       message.concents.ForceSubtaskResultsRejected.REASON.RequestPremature,
                'timestamp':    self._parse_iso_date_to_timestamp("2018-03-05 10:00:24"),
            }
        )

        serialized_force_subtask_results = self._get_serialized_force_subtask_results(
            timestamp                   = "2018-03-05 10:00:15",
            ack_report_computed_task    = self._get_deserialized_ack_report_computed_task(
                timestamp       = "2018-03-05 10:00:15",
                subtask_id      = '2',
                task_to_compute = self._get_deserialized_task_to_compute(
                    timestamp   = "2018-03-05 10:00:00",
                    deadline    = "2018-03-05 10:00:10",
                    task_id     = '2',
                )
            )
        )

        with mock.patch('core.views.is_provider_account_status_positive', _get_provider_account_status_true_mock):
            with freeze_time("2018-03-05 10:00:40"):
                response_2 = self.client.post(
                    reverse('core:send'),
                    data                                = serialized_force_subtask_results,
                    content_type                        = 'application/octet-stream',
                    HTTP_CONCENT_CLIENT_PUBLIC_KEY      = self._get_encoded_provider_public_key(),
                )

        self._test_response(
            response_2,
            status       = 200,
            key          = self.PROVIDER_PRIVATE_KEY,
            message_type = message.concents.ForceSubtaskResultsRejected,
            fields       = {
                'reason':       message.concents.ForceSubtaskResultsRejected.REASON.RequestTooLate,
                'timestamp':    self._parse_iso_date_to_timestamp("2018-03-05 10:00:40"),
            }
        )

    def test_requestor_should_receive_subtask_results_from_concent(self):
        """
        Test if Provider submitted ForceSubtaskResults, Concent will return message to Requestor with new timestamp
        if Requestor ask Concent before deadline

        Expected message exchange:
        Provider    -> Concent:     ForceSubtaskResults
        Concent     -> Provider:    HTTP 202
        Concent     -> Requestor:   ForceSubtaskResults (new timestamp)
        """

        serialized_force_subtask_results = self._get_serialized_force_subtask_results(
            timestamp                   = "2018-02-05 10:00:20",
            ack_report_computed_task    = self._get_deserialized_ack_report_computed_task(
                timestamp       = "2018-02-05 10:00:20",
                subtask_id      = "xxyyzz",
                task_to_compute = self._get_deserialized_task_to_compute(
                    timestamp   = "2018-02-05 10:00:00",
                    deadline    = "2018-02-05 10:00:10",
                    task_id     = '2',
                )
            )
        )

        with mock.patch('core.views.is_provider_account_status_positive', _get_provider_account_status_true_mock):
            with freeze_time("2018-02-05 10:00:31"):
                response_1 = self.client.post(
                    reverse('core:send'),
                    data                                = serialized_force_subtask_results,
                    content_type                        = 'application/octet-stream',
                    HTTP_CONCENT_CLIENT_PUBLIC_KEY      = self._get_encoded_provider_public_key(),
                )

        assert len(response_1.content) == 0
        assert response_1.status_code  == 202

        self._test_database_objects(
            last_object_type         = message.concents.ForceSubtaskResults,
            task_id                  = '2',
            receive_delivered_status = False,
        )

        with freeze_time("2018-02-05 10:00:29"):
            response_2 = self.client.post(
                reverse('core:receive'),
                data                            = '',
                content_type                    = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY  = self._get_encoded_requestor_public_key(),
            )

        deserialized_compute_task_def = self._get_deserialized_compute_task_def(
            deadline    = "2018-02-05 10:00:10",
            task_id     = '2',
        )
        self._test_response(
            response_2,
            status       = 200,
            key          = self.REQUESTOR_PRIVATE_KEY,
            message_type = message.concents.ForceSubtaskResults,
            fields       = {
                'timestamp':                                                    self._parse_iso_date_to_timestamp("2018-02-05 10:00:29"),
                'ack_report_computed_task.subtask_id':                          'xxyyzz',
                "ack_report_computed_task.task_to_compute.compute_task_def":    deserialized_compute_task_def,
            }
        )
        self.assertEqual(ReceiveStatus.objects.last().delivered, True)

    def test_requestor_should_not_receive_correct_subtask_results_from_concent_if_asked_concent_after_deadline(self):
        """
        Test if Provider submitted ForceSubtaskResults, Requestor won't receive from Concent
        message with correct timestamp if Requestor ask Concent after deadline

        Exptected message exchange:
        Provider    -> Concent:     ForceSubtaskResults
        Concent     -> Provider:    HTTP 202
        Concent     -> Requestor:   ForceSubtaskResults (old timestamp)
        """

        serialized_force_subtask_results = self._get_serialized_force_subtask_results(
            timestamp                   = "2018-02-05 10:00:20",
            ack_report_computed_task    = self._get_deserialized_ack_report_computed_task(
                timestamp       = "2018-02-05 10:00:20",
                subtask_id      = "xxyyzz",
                task_to_compute = self._get_deserialized_task_to_compute(
                    timestamp   = "2018-02-05 10:00:00",
                    deadline    = "2018-02-05 10:00:10",
                    task_id     = '2',
                )
            )
        )

        with mock.patch('core.views.is_provider_account_status_positive', _get_provider_account_status_true_mock):
            with freeze_time("2018-02-05 10:00:31"):
                response_1 = self.client.post(
                    reverse('core:send'),
                    data                                = serialized_force_subtask_results,
                    content_type                        = 'application/octet-stream',
                    HTTP_CONCENT_CLIENT_PUBLIC_KEY      = self._get_encoded_provider_public_key(),
                )

        assert len(response_1.content) == 0
        assert response_1.status_code  == 202

        self._test_database_objects(
            last_object_type         = message.concents.ForceSubtaskResults,
            task_id                  = '2',
            receive_delivered_status = False,
        )

        with freeze_time("2018-02-05 11:00:00"):
            response_2 = self.client.post(
                reverse('core:receive'),
                data                            = '',
                content_type                    = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY  = self._get_encoded_requestor_public_key(),
            )
        deserialized_compute_task_def = self._get_deserialized_compute_task_def(
            deadline    = "2018-02-05 10:00:10",
            task_id     = '2',
        )
        self._test_response(
            response_2,
            status       = 200,
            key          = self.REQUESTOR_PRIVATE_KEY,
            message_type = message.concents.ForceSubtaskResults,
            fields       = {
                'timestamp':                                            self._parse_iso_date_to_timestamp("2018-02-05 10:00:20"),
                'ack_report_computed_task.subtask_id':                  'xxyyzz',
                'ack_report_computed_task.task_to_compute.compute_task_def': deserialized_compute_task_def,
            }
        )
        self.assertEqual(ReceiveStatus.objects.last().delivered, True)

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

        serialized_force_subtask_results = self._get_serialized_force_subtask_results(
            timestamp                   = "2018-02-05 10:00:15",
            ack_report_computed_task    = self._get_deserialized_ack_report_computed_task(
                timestamp       = "2018-02-05 10:00:15",
                subtask_id      = "xxyyzz",
                task_to_compute = self._get_deserialized_task_to_compute(
                    timestamp   = "2018-02-05 10:00:00",
                    deadline    = "2018-02-05 10:00:10",
                    task_id     = '2',
                )
            )
        )

        with mock.patch('core.views.is_provider_account_status_positive', _get_provider_account_status_true_mock):
            with freeze_time("2018-02-05 10:00:30"):
                response_1 = self.client.post(
                    reverse('core:send'),
                    data                                = serialized_force_subtask_results,
                    content_type                        = 'application/octet-stream',
                    HTTP_CONCENT_CLIENT_PUBLIC_KEY      = self._get_encoded_provider_public_key(),
                )

        assert len(response_1.content)  == 0
        assert response_1.status_code   == 202

        with freeze_time("2018-02-05 11:00:02"):
            response_2 = self.client.post(
                reverse('core:receive'),
                data                            = '',
                content_type                    = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY  = self._get_encoded_requestor_public_key(),
            )

        self._test_response(
            response_2,
            status          = 200,
            key             = self.REQUESTOR_PRIVATE_KEY,
            message_type    = message.concents.ForceSubtaskResults,
            fields          = {
                'timestamp':                            self._parse_iso_date_to_timestamp("2018-02-05 10:00:15"),
                'ack_report_computed_task.timestamp':   self._parse_iso_date_to_timestamp("2018-02-05 10:00:15"),
                'ack_report_computed_task.subtask_id':  'xxyyzz',
            }
        )

        serialized_force_subtask_results_response = self._get_serialized_force_subtask_results_response(
            requestor_private_key   = self.REQUESTOR_PRIVATE_KEY,
            timestamp               = "2018-02-05 11:00:00",
            subtask_results_accepted = self._get_deserialized_subtask_results_accepted(
                timestamp               = "2018-02-05 11:00:00",
                subtask_id              = '2',
                payment_ts              = "2018-02-05 11:00:01",
            )
        )

        with mock.patch('core.views.is_provider_account_status_positive', _get_provider_account_status_true_mock):
            with freeze_time("2018-02-05 11:00:01"):
                self.client.post(
                    reverse('core:send'),
                    data                            = serialized_force_subtask_results_response,
                    content_type                    = 'application/octet-stream',
                    HTTP_CONCENT_CLIENT_PUBLIC_KEY  = self._get_encoded_requestor_public_key(),
                )

        self._test_database_objects(
            last_object_type         = message.concents.ForceSubtaskResultsResponse,
            task_id                  = '2',
            receive_delivered_status = False,
        )

        with freeze_time("2018-02-05 11:00:02"):
            response_3 = self.client.post(
                reverse('core:receive'),
                data                            = '',
                content_type                    = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY  = self._get_encoded_requestor_public_key(),
            )

        self._test_response(
            response_3,
            status          = 200,
            key             = self.PROVIDER_PRIVATE_KEY,
            message_type    = message.concents.ForceSubtaskResultsResponse,
            fields          = {
                'timestamp':                            self._parse_iso_date_to_timestamp("2018-02-05 11:00:00"),
                'subtask_results_accepted.timestamp':   self._parse_iso_date_to_timestamp("2018-02-05 11:00:00"),
                'subtask_results_accepted.subtask_id':  '2',
                'subtask_results_accepted.payment_ts':  self._parse_iso_date_to_timestamp("2018-02-05 11:00:01")
            }
        )

        self._test_database_objects(
            last_object_type         = message.concents.ForceSubtaskResultsResponse,
            task_id                  = '2',
            receive_delivered_status = True,
        )

    def test_requestor_sends_subtask_results_rejected_and_concent_should_return_it_to_provider(self):
        """
        Test if Requestor wants submit SubtaskResultsAccepted message,
        Provider should receive it from Concent

        Exptected message exchange:
        Provider    -> Concent:     ForceSubtaskResults
        Concent     -> Requestor:   ForceSubtaskResults
        Requestor   -> Concent:     SubtaskResultsRejected
        Concent     -> Requestor:   HTTP 202
        Concent     -> Provider:    SubtaskResultsRejected
        """

        serialized_force_subtask_results = self._get_serialized_force_subtask_results(
            timestamp                   = "2018-02-05 10:00:15",
            ack_report_computed_task    = self._get_deserialized_ack_report_computed_task(
                timestamp       = "2018-02-05 10:00:15",
                subtask_id      = "xxyyzz",
                task_to_compute = self._get_deserialized_task_to_compute(
                    timestamp   = "2018-02-05 10:00:00",
                    deadline    = "2018-02-05 10:00:10",
                    task_id     = '2',
                )
            )
        )

        with mock.patch('core.views.is_provider_account_status_positive', _get_provider_account_status_true_mock):
            with freeze_time("2018-02-05 10:00:30"):
                response_1 = self.client.post(
                    reverse('core:send'),
                    data                                = serialized_force_subtask_results,
                    content_type                        = 'application/octet-stream',
                    HTTP_CONCENT_CLIENT_PUBLIC_KEY      = self._get_encoded_provider_public_key(),
                    HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY=self._get_encoded_requestor_public_key(),
                )

        assert len(response_1.content)  == 0
        assert response_1.status_code   == 202

        with freeze_time("2018-02-05 11:00:02"):
            response_2 = self.client.post(
                reverse('core:receive'),
                data                            = '',
                content_type                    = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY  = self._get_encoded_requestor_public_key(),
            )

        self._test_response(
            response_2,
            status          = 200,
            key             = self.REQUESTOR_PRIVATE_KEY,
            message_type    = message.concents.ForceSubtaskResults,
            fields          = {
                'timestamp':                            self._parse_iso_date_to_timestamp("2018-02-05 10:00:15"),
                'ack_report_computed_task.timestamp':   self._parse_iso_date_to_timestamp("2018-02-05 10:00:15"),
                'ack_report_computed_task.subtask_id':  'xxyyzz',
            }
        )

        serialized_force_subtask_results_response = self._get_serialized_force_subtask_results_response(
            requestor_private_key   = self.REQUESTOR_PRIVATE_KEY,
            timestamp               = "2018-02-05 11:00:00",
            subtask_results_rejected = self._get_deserialized_subtask_results_rejected(
                timestamp               = "2018-02-05 11:00:00",
                reason                  = message.tasks.SubtaskResultsRejected.REASON.VerificationNegative,
                report_computed_task    = self._get_deserialized_report_computed_task(
                    timestamp   = "2018-02-05 11:00:00",
                    subtask_id  = '2',
                    task_to_compute = self._get_deserialized_task_to_compute(
                        timestamp   = "2018-02-05 11:00:00",
                        deadline    = "2018-02-05 11:00:01",
                        task_id     = '2',
                    )
                )
            )
        )

        with mock.patch('core.views.is_provider_account_status_positive', _get_provider_account_status_true_mock):
            with freeze_time("2018-02-05 11:00:01"):
                self.client.post(
                    reverse('core:send'),
                    data                            = serialized_force_subtask_results_response,
                    content_type                    = 'application/octet-stream',
                    HTTP_CONCENT_CLIENT_PUBLIC_KEY  = self._get_encoded_requestor_public_key(),
                )

        self._test_database_objects(
            last_object_type         = message.concents.ForceSubtaskResultsResponse,
            task_id                  = '2',
            receive_delivered_status = False,
        )

        with freeze_time("2018-02-05 11:00:02"):
            response_3 = self.client.post(
                reverse('core:receive'),
                data                            = '',
                content_type                    = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY  = self._get_encoded_provider_public_key(),
            )

        self._test_response(
            response_3,
            status          = 200,
            key             = self.PROVIDER_PRIVATE_KEY,
            message_type    = message.concents.ForceSubtaskResultsResponse,
            fields          = {
                'timestamp':                                                self._parse_iso_date_to_timestamp("2018-02-05 11:00:00"),
                'subtask_results_rejected.timestamp':                       self._parse_iso_date_to_timestamp("2018-02-05 11:00:00"),
                'subtask_results_rejected.reason':                          message.tasks.SubtaskResultsRejected.REASON.VerificationNegative,
                'subtask_results_rejected.report_computed_task.timestamp':  self._parse_iso_date_to_timestamp("2018-02-05 11:00:00"),
                'subtask_results_rejected.report_computed_task.subtask_id': '2'
            }
        )

        self._test_database_objects(
            last_object_type         = message.concents.ForceSubtaskResultsResponse,
            task_id                  = '2',
            receive_delivered_status = True,
        )
