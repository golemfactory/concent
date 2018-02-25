import mock

from django.test            import override_settings
from django.urls            import reverse
from freezegun              import freeze_time
from golem_messages         import message

from core.models            import ReceiveStatus
from core.tests.utils       import ConcentIntegrationTestCase
from utils.testing_helpers  import generate_ecc_key_pair


(CONCENT_PRIVATE_KEY, CONCENT_PUBLIC_KEY) = generate_ecc_key_pair()


def _get_provider_account_status_true_mock(_):
    return True


def _get_provider_account_status_false_mock(_):
    return False


def _get_requestor_account_status(_provider, _requestor):
    pass


@override_settings(
    CONCENT_PRIVATE_KEY       = CONCENT_PRIVATE_KEY,
    CONCENT_PUBLIC_KEY        = CONCENT_PUBLIC_KEY,
    CONCENT_MESSAGING_TIME    = 10,  # seconds
    FORCE_ACCEPTANCE_TIME     = 10,  # seconds
    SUBTASK_VERIFICATION_TIME = 10,  # seconds
)
class GetTaskResultIntegrationTest(ConcentIntegrationTestCase):

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

        with mock.patch('core.views.base.is_provider_account_status_positive', _get_provider_account_status_true_mock):
            with freeze_time("2018-02-05 10:00:25"):
                response = self.client.post(
                    reverse('core:send'),
                    data                                = serialized_force_subtask_results,
                    content_type                        = 'application/octet-stream',
                    HTTP_CONCENT_CLIENT_PUBLIC_KEY      = self._get_encoded_provider_public_key(),
                    HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
                )

        assert len(response.content)  == 0
        assert response.status_code   == 202

        self._test_database_objects(
            last_object_type         = message.concents.ForceSubtaskResults,
            task_id                  = '2',
            receive_delivered_status = False,
        )
        self._assert_auth_message_counter_increased()
        self._assert_auth_message_last(
            related_message      = message.concents.ForceSubtaskResults,
            provider_public_key  = self._get_encoded_provider_public_key(),
            requestor_public_key = self._get_encoded_requestor_public_key(),
        )

        # STEP 2: Different provider forces subtask results via Concent with message with the same task_id with different keys.
        # Request is processed correctly.
        different_serialized_force_subtask_results = self._get_serialized_force_subtask_results(
            timestamp                = "2018-02-05 10:00:15",
            ack_report_computed_task = self._get_deserialized_ack_report_computed_task(
                timestamp       = "2018-02-05 10:00:15",
                subtask_id      = "xxyyzz",
                task_to_compute = self._get_deserialized_task_to_compute(
                    timestamp = "2018-02-05 10:00:00",
                    deadline  = "2018-02-05 10:00:10",
                    task_id   = '2',
                )
            ),
            provider_private_key = self.DIFFERENT_PROVIDER_PRIVATE_KEY,
        )

        with mock.patch('core.views.base.is_provider_account_status_positive', _get_provider_account_status_true_mock):
            with freeze_time("2018-02-05 10:00:31"):
                response = self.client.post(
                    reverse('core:send'),
                    data                                = different_serialized_force_subtask_results,
                    content_type                        = 'application/octet-stream',
                    HTTP_CONCENT_CLIENT_PUBLIC_KEY      = self._get_encoded_key(self.DIFFERENT_PROVIDER_PUBLIC_KEY),
                    HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
                )

        assert len(response.content)  == 0
        assert response.status_code   == 202

        self._test_database_objects(
            last_object_type         = message.concents.ForceSubtaskResults,
            task_id                  = '2',
            receive_delivered_status = False,
        )
        self._assert_auth_message_counter_increased()
        self._assert_auth_message_last(
            related_message      = message.concents.ForceSubtaskResults,
            provider_public_key  = self._get_encoded_key(self.DIFFERENT_PROVIDER_PUBLIC_KEY),
            requestor_public_key = self._get_encoded_requestor_public_key(),
        )

        # STEP 3: Provider again forces subtask results via Concent with message with the same task_id with correct keys.
        # Request is refused.
        with mock.patch('core.views.base.is_provider_account_status_positive', _get_provider_account_status_true_mock):
            with freeze_time("2018-02-05 10:00:31"):
                response = self.client.post(
                    reverse('core:send'),
                    data                                = serialized_force_subtask_results,
                    content_type                        = 'application/octet-stream',
                    HTTP_CONCENT_CLIENT_PUBLIC_KEY      = self._get_encoded_provider_public_key(),
                    HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
                )

        self._test_response(
            response,
            status       = 200,
            key          = self.PROVIDER_PRIVATE_KEY,
            message_type = message.concents.ServiceRefused,
            fields       = {
                'reason':    message.concents.ServiceRefused.REASON.DuplicateRequest,
                'timestamp': self._parse_iso_date_to_timestamp("2018-02-05 10:00:31"),
            }
        )
        self._assert_auth_message_counter_not_increased()

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

        # STEP 1: Provider forces subtask results via Concent.
        # Request is processed correctly.
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

        with mock.patch('core.views.base.is_provider_account_status_positive', _get_provider_account_status_true_mock):
            with freeze_time("2018-02-05 10:00:31"):
                response = self.client.post(
                    reverse('core:send'),
                    data                                = serialized_force_subtask_results,
                    content_type                        = 'application/octet-stream',
                    HTTP_CONCENT_CLIENT_PUBLIC_KEY      = self._get_encoded_provider_public_key(),
                    HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
                )

        assert len(response.content) == 0
        assert response.status_code  == 202

        self._test_database_objects(
            last_object_type         = message.concents.ForceSubtaskResults,
            task_id                  = '2',
            receive_delivered_status = False,
        )
        self._assert_auth_message_counter_increased()
        self._assert_auth_message_last(
            related_message      = message.concents.ForceSubtaskResults,
            provider_public_key  = self._get_encoded_provider_public_key(),
            requestor_public_key = self._get_encoded_requestor_public_key(),
        )

        # STEP 2: Different requestor or provider does not receive forces subtask results via Concent with different or mixed key.
        with freeze_time("2018-02-05 10:00:29"):
            response = self.client.post(
                reverse('core:receive'),
                data                            = '',
                content_type                    = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY  = self._get_encoded_key(self.DIFFERENT_REQUESTOR_PUBLIC_KEY),
            )

        self._test_204_response(response)
        self._assert_auth_message_counter_not_increased()

        with freeze_time("2018-02-05 10:00:29"):
            response = self.client.post(
                reverse('core:receive'),
                data                            = '',
                content_type                    = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY  = self._get_encoded_provider_public_key(),
            )

        self._test_204_response(response)
        self._assert_auth_message_counter_not_increased()

        # STEP 3: Requestor receives forces subtask results via Concent with correct key.
        with freeze_time("2018-02-05 10:00:29"):
            response = self.client.post(
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
            response,
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

        with mock.patch('core.views.base.is_provider_account_status_positive', _get_provider_account_status_true_mock):
            with freeze_time("2018-02-05 10:00:30"):
                response = self.client.post(
                    reverse('core:send'),
                    data                                = serialized_force_subtask_results,
                    content_type                        = 'application/octet-stream',
                    HTTP_CONCENT_CLIENT_PUBLIC_KEY      = self._get_encoded_provider_public_key(),
                    HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
                )

        assert len(response.content)  == 0
        assert response.status_code   == 202

        self._assert_auth_message_counter_increased()
        self._assert_auth_message_last(
            related_message      = message.concents.ForceSubtaskResults,
            provider_public_key  = self._get_encoded_provider_public_key(),
            requestor_public_key = self._get_encoded_requestor_public_key(),
        )

        # STEP 2: Different requestor or provider does not receive forces subtask results via Concent with different or mixed key.
        with freeze_time("2018-02-05 10:00:24"):
            response = self.client.post(
                reverse('core:receive'),
                data                            = '',
                content_type                    = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY  = self._get_encoded_key(self.DIFFERENT_REQUESTOR_PUBLIC_KEY),
            )

        self._test_204_response(response)
        self._assert_auth_message_counter_not_increased()

        with freeze_time("2018-02-05 10:00:24"):
            response = self.client.post(
                reverse('core:receive'),
                data                            = '',
                content_type                    = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY  = self._get_encoded_provider_public_key(),
            )

        self._test_204_response(response)
        self._assert_auth_message_counter_not_increased()

        # STEP 3: Requestor receives forces subtask results via Concent with correct key.
        with freeze_time("2018-02-05 10:00:24"):
            response = self.client.post(
                reverse('core:receive'),
                data                            = '',
                content_type                    = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY  = self._get_encoded_requestor_public_key(),
            )

        self._test_response(
            response,
            status          = 200,
            key             = self.REQUESTOR_PRIVATE_KEY,
            message_type    = message.concents.ForceSubtaskResults,
            fields          = {
                'timestamp':                            self._parse_iso_date_to_timestamp("2018-02-05 10:00:24"),
                'ack_report_computed_task.timestamp':   self._parse_iso_date_to_timestamp("2018-02-05 10:00:15"),
                'ack_report_computed_task.subtask_id':  'xxyyzz',
            }
        )
        self._assert_auth_message_counter_increased()
        self._assert_auth_message_last(
            related_message      = message.concents.ForceSubtaskResults,
            provider_public_key  = self._get_encoded_provider_public_key(),
            requestor_public_key = self._get_encoded_requestor_public_key(),
        )

        # STEP 4: Different requestor or provider sends forces subtask results response via Concent with different or mixed key.
        # Request is rejected.
        compute_task_def = self._get_deserialized_compute_task_def(
            task_id  = '2',
            deadline = "2018-02-05 11:00:00",
        )

        serialized_force_subtask_results_response = self._get_serialized_force_subtask_results_response(
            requestor_private_key   = self.DIFFERENT_REQUESTOR_PRIVATE_KEY,
            timestamp               = "2018-02-05 10:00:43",
            subtask_results_accepted = self._get_deserialized_subtask_results_accepted(
                timestamp               = "2018-02-05 10:00:43",
                payment_ts              = "2018-02-05 10:00:44",
                task_to_compute         = self._get_deserialized_task_to_compute(
                    timestamp        = "2018-02-05 10:00:00",
                    compute_task_def = compute_task_def,
                ),
            )
        )

        with mock.patch('core.views.base.is_provider_account_status_positive', _get_provider_account_status_true_mock):
            with freeze_time("2018-02-05 10:00:44"):
                response = self.client.post(
                    reverse('core:send'),
                    data                            = serialized_force_subtask_results_response,
                    content_type                    = 'application/octet-stream',
                    HTTP_CONCENT_CLIENT_PUBLIC_KEY  = self._get_encoded_key(self.DIFFERENT_REQUESTOR_PUBLIC_KEY),
                )

        self._test_400_response(response)
        self._assert_auth_message_counter_not_increased()

        serialized_force_subtask_results_response = self._get_serialized_force_subtask_results_response(
            requestor_private_key   = self.PROVIDER_PRIVATE_KEY,
            timestamp               = "2018-02-05 10:00:43",
            subtask_results_accepted = self._get_deserialized_subtask_results_accepted(
                timestamp               = "2018-02-05 10:00:43",
                payment_ts              = "2018-02-05 10:00:44",
                task_to_compute=self._get_deserialized_task_to_compute(
                    timestamp="2018-02-05 10:00:00",
                    compute_task_def=compute_task_def,
                ),
            )
        )

        with mock.patch('core.views.base.is_provider_account_status_positive', _get_provider_account_status_true_mock):
            with freeze_time("2018-02-05 10:00:44"):
                response = self.client.post(
                    reverse('core:send'),
                    data                            = serialized_force_subtask_results_response,
                    content_type                    = 'application/octet-stream',
                    HTTP_CONCENT_CLIENT_PUBLIC_KEY  = self._get_encoded_provider_public_key(),
                )

        self._test_400_response(response)
        self._assert_auth_message_counter_not_increased()

        # STEP 5: Requestor sends forces subtask results response via Concent with correct keys.
        # Request is processed correctly.
        serialized_force_subtask_results_response = self._get_serialized_force_subtask_results_response(
            requestor_private_key = self.REQUESTOR_PRIVATE_KEY,
            timestamp             = "2018-02-05 10:00:43",
            subtask_results_accepted = self._get_deserialized_subtask_results_accepted(
                timestamp       = "2018-02-05 10:00:43",
                payment_ts      = "2018-02-05 10:00:44",
                task_to_compute = self._get_deserialized_task_to_compute(
                    timestamp        = "2018-02-05 10:00:00",
                    compute_task_def = compute_task_def,
                ),
            )
        )

        with mock.patch('core.views.base.is_provider_account_status_positive', _get_provider_account_status_true_mock):
            with freeze_time("2018-02-05 10:00:44"):
                self.client.post(
                    reverse('core:send'),
                    data                           = serialized_force_subtask_results_response,
                    content_type                   = 'application/octet-stream',
                    HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
                )

        self._test_database_objects(
            last_object_type         = message.concents.ForceSubtaskResultsResponse,
            task_id                  = '2',
            receive_delivered_status = False,
        )
        self._assert_auth_message_counter_increased()
        self._assert_auth_message_last(
            related_message      = message.concents.ForceSubtaskResultsResponse,
            provider_public_key  = self._get_encoded_provider_public_key(),
            requestor_public_key = self._get_encoded_requestor_public_key(),
        )

        # STEP 6: Different provider or requestor does not receive forces subtask results via Concent with different or mixed key.
        with freeze_time("2018-02-05 11:00:02"):
            response = self.client.post(
                reverse('core:receive'),
                data                            = '',
                content_type                    = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY  = self._get_encoded_key(self.DIFFERENT_PROVIDER_PUBLIC_KEY),
            )

        self._test_204_response(response)
        self._assert_auth_message_counter_not_increased()

        with freeze_time("2018-02-05 11:00:02"):
            response = self.client.post(
                reverse('core:receive'),
                data                            = '',
                content_type                    = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY  = self._get_encoded_requestor_public_key(),
            )

        self._test_204_response(response)
        self._assert_auth_message_counter_not_increased()

        # STEP 7: Provider does receives forces subtask results via Concent with correct key.
        with freeze_time("2018-02-05 11:00:02"):
            response = self.client.post(
                reverse('core:receive'),
                data                            = '',
                content_type                    = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY  = self._get_encoded_provider_public_key(),
            )

        self._test_response(
            response,
            status          = 200,
            key             = self.PROVIDER_PRIVATE_KEY,
            message_type    = message.concents.ForceSubtaskResultsResponse,
            fields          = {
                'timestamp':                                                 self._parse_iso_date_to_timestamp("2018-02-05 11:00:02"),
                'subtask_results_accepted.timestamp':                        self._parse_iso_date_to_timestamp("2018-02-05 10:00:43"),
                'subtask_results_accepted.task_to_compute.compute_task_def': compute_task_def,
                'subtask_results_accepted.payment_ts':                       self._parse_iso_date_to_timestamp("2018-02-05 10:00:44")
            }
        )

        self._test_database_objects(
            last_object_type         = message.concents.ForceSubtaskResultsResponse,
            task_id                  = '2',
            receive_delivered_status = True,
        )
        self._assert_auth_message_counter_increased()
        self._assert_auth_message_last(
            related_message      = message.concents.ForceSubtaskResultsResponse,
            provider_public_key  = self._get_encoded_provider_public_key(),
            requestor_public_key = self._get_encoded_requestor_public_key(),
        )

    def test_requestor_sends_subtask_results_rejected_and_concent_should_return_it_to_provider_with_correct_keys(self):
        """
        Test if Requestor wants submit SubtaskResultsAccepted message,
        Provider should receive it from Concent if correct keys are used.

        Exptected message exchange:
        Provider                  -> Concent:                   ForceSubtaskResults
        Concent                   -> Provider:                  HTTP 202
        Concent                   -> WrongRequestor/Provider:   HTTP 204
        Concent                   -> Requestor:                 ForceSubtaskResults
        WrongRequestor/Provider   -> Concent:                   SubtaskResultsRejected
        Concent                   -> Requestor:                 HTTP 202
        Concent                   -> WrongProvider/Requestor:   HTTP 204
        Concent                   -> Provider:                  SubtaskResultsRejected
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

        with mock.patch('core.views.base.is_provider_account_status_positive', _get_provider_account_status_true_mock):
            with freeze_time("2018-02-05 10:00:30"):
                response = self.client.post(
                    reverse('core:send'),
                    data                                = serialized_force_subtask_results,
                    content_type                        = 'application/octet-stream',
                    HTTP_CONCENT_CLIENT_PUBLIC_KEY      = self._get_encoded_provider_public_key(),
                    HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
                )

        assert len(response.content)  == 0
        assert response.status_code   == 202

        self._assert_auth_message_counter_increased()
        self._assert_auth_message_last(
            related_message      = message.concents.ForceSubtaskResults,
            provider_public_key  = self._get_encoded_provider_public_key(),
            requestor_public_key = self._get_encoded_requestor_public_key(),
        )

        # STEP 2: Different requestor or provider does not receive forces subtask results via Concent with different or mixed key.
        with freeze_time("2018-02-05 10:00:24"):
            response = self.client.post(
                reverse('core:receive'),
                data='',
                content_type='application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY=self._get_encoded_key(self.DIFFERENT_REQUESTOR_PUBLIC_KEY),
            )

        self._test_204_response(response)
        self._assert_auth_message_counter_not_increased()

        with freeze_time("2018-02-05 10:00:24"):
            response = self.client.post(
                reverse('core:receive'),
                data                           = '',
                content_type                   = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY = self._get_encoded_provider_public_key(),
            )

        self._test_204_response(response)
        self._assert_auth_message_counter_not_increased()

        # STEP 3: Requestor receives forces subtask results via Concent with correct key.
        with freeze_time("2018-02-05 10:00:24"):
            response = self.client.post(
                reverse('core:receive'),
                data                            = '',
                content_type                    = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY  = self._get_encoded_requestor_public_key(),
            )

        self._test_response(
            response,
            status          = 200,
            key             = self.REQUESTOR_PRIVATE_KEY,
            message_type    = message.concents.ForceSubtaskResults,
            fields          = {
                'timestamp':                            self._parse_iso_date_to_timestamp("2018-02-05 10:00:24"),
                'ack_report_computed_task.timestamp':   self._parse_iso_date_to_timestamp("2018-02-05 10:00:15"),
                'ack_report_computed_task.subtask_id':  'xxyyzz',
            }
        )
        self._assert_auth_message_counter_increased()
        self._assert_auth_message_last(
            related_message      = message.concents.ForceSubtaskResults,
            provider_public_key  = self._get_encoded_provider_public_key(),
            requestor_public_key = self._get_encoded_requestor_public_key(),
        )

        # STEP 4: Different requestor or provider sends forces subtask results response via Concent with different or mixed key.
        # Request is rejected.
        serialized_force_subtask_results_response = self._get_serialized_force_subtask_results_response(
            requestor_private_key = self.DIFFERENT_REQUESTOR_PRIVATE_KEY,
            timestamp             = "2018-02-05 10:00:43",
            subtask_results_rejected = self._get_deserialized_subtask_results_rejected(
                timestamp            = "2018-02-05 10:00:43",
                reason               = message.tasks.SubtaskResultsRejected.REASON.VerificationNegative,
                report_computed_task = self._get_deserialized_report_computed_task(
                    timestamp       = "2018-02-05 10:00:43",
                    subtask_id      = '2',
                    task_to_compute = self._get_deserialized_task_to_compute(
                        timestamp = "2018-02-05 10:00:43",
                        deadline  = "2018-02-05 10:00:44",
                        task_id   = '2',
                    )
                )
            )
        )

        with mock.patch('core.views.base.is_provider_account_status_positive', _get_provider_account_status_true_mock):
            with freeze_time("2018-02-05 10:00:44"):
                response = self.client.post(
                    reverse('core:send'),
                    data                            = serialized_force_subtask_results_response,
                    content_type                    = 'application/octet-stream',
                    HTTP_CONCENT_CLIENT_PUBLIC_KEY  = self._get_encoded_key(self.DIFFERENT_REQUESTOR_PUBLIC_KEY),
                )

        self._test_400_response(response)
        self._assert_auth_message_counter_not_increased()

        serialized_force_subtask_results_response = self._get_serialized_force_subtask_results_response(
            requestor_private_key    = self.PROVIDER_PRIVATE_KEY,
            timestamp                = "2018-02-05 10:00:43",
            subtask_results_rejected = self._get_deserialized_subtask_results_rejected(
                timestamp            = "2018-02-05 10:00:43",
                reason               = message.tasks.SubtaskResultsRejected.REASON.VerificationNegative,
                report_computed_task = self._get_deserialized_report_computed_task(
                    timestamp       = "2018-02-05 10:00:43",
                    subtask_id      = '2',
                    task_to_compute = self._get_deserialized_task_to_compute(
                        timestamp = "2018-02-05 10:00:43",
                        deadline  = "2018-02-05 10:00:44",
                        task_id   = '2',
                    )
                )
            )
        )

        with mock.patch('core.views.base.is_provider_account_status_positive', _get_provider_account_status_true_mock):
            with freeze_time("2018-02-05 10:00:44"):
                response = self.client.post(
                    reverse('core:send'),
                    data                            = serialized_force_subtask_results_response,
                    content_type                    = 'application/octet-stream',
                    HTTP_CONCENT_CLIENT_PUBLIC_KEY  = self._get_encoded_provider_public_key(),
                )

        self._test_400_response(response)
        self._assert_auth_message_counter_not_increased()

        # STEP 5: Requestor sends forces subtask results response via Concent with correct keys.
        # Request is processed correctly.
        serialized_force_subtask_results_response = self._get_serialized_force_subtask_results_response(
            requestor_private_key   = self.REQUESTOR_PRIVATE_KEY,
            timestamp               = "2018-02-05 10:00:43",
            subtask_results_rejected = self._get_deserialized_subtask_results_rejected(
                timestamp               = "2018-02-05 10:00:43",
                reason                  = message.tasks.SubtaskResultsRejected.REASON.VerificationNegative,
                report_computed_task    = self._get_deserialized_report_computed_task(
                    timestamp   = "2018-02-05 10:00:43",
                    subtask_id  = '2',
                    task_to_compute = self._get_deserialized_task_to_compute(
                        timestamp   = "2018-02-05 10:00:43",
                        deadline    = "2018-02-05 10:00:44",
                        task_id     = '2',
                    )
                )
            )
        )

        with mock.patch('core.views.base.is_provider_account_status_positive', _get_provider_account_status_true_mock):
            with freeze_time("2018-02-05 10:00:44"):
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
        self._assert_auth_message_counter_increased()
        self._assert_auth_message_last(
            related_message      = message.concents.ForceSubtaskResultsResponse,
            provider_public_key  = self._get_encoded_provider_public_key(),
            requestor_public_key = self._get_encoded_requestor_public_key(),
        )

        # STEP 6: Different provider or requestor does not receive forces subtask results via Concent with different or mixed key.
        with freeze_time("2018-02-05 11:00:02"):
            response = self.client.post(
                reverse('core:receive'),
                data                            = '',
                content_type                    = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY  = self._get_encoded_key(self.DIFFERENT_PROVIDER_PUBLIC_KEY),
            )

        self._test_204_response(response)
        self._assert_auth_message_counter_not_increased()

        with freeze_time("2018-02-05 11:00:02"):
            response = self.client.post(
                reverse('core:receive'),
                data                            = '',
                content_type                    = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY  = self._get_encoded_requestor_public_key(),
            )

        self._test_204_response(response)
        self._assert_auth_message_counter_not_increased()

        # STEP 7: Provider does receives forces subtask results via Concent with correct key.
        with freeze_time("2018-02-05 11:00:02"):
            response = self.client.post(
                reverse('core:receive'),
                data                            = '',
                content_type                    = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY  = self._get_encoded_provider_public_key(),
            )

        self._test_response(
            response,
            status          = 200,
            key             = self.PROVIDER_PRIVATE_KEY,
            message_type    = message.concents.ForceSubtaskResultsResponse,
            fields          = {
                'timestamp':                                                self._parse_iso_date_to_timestamp("2018-02-05 11:00:02"),
                'subtask_results_rejected.timestamp':                       self._parse_iso_date_to_timestamp("2018-02-05 10:00:43"),
                'subtask_results_rejected.reason':                          message.tasks.SubtaskResultsRejected.REASON.VerificationNegative,
                'subtask_results_rejected.report_computed_task.timestamp':  self._parse_iso_date_to_timestamp("2018-02-05 10:00:43"),
                'subtask_results_rejected.report_computed_task.subtask_id': '2'
            }
        )

        self._test_database_objects(
            last_object_type         = message.concents.ForceSubtaskResultsResponse,
            task_id                  = '2',
            receive_delivered_status = True,
        )
        self._assert_auth_message_counter_increased()
        self._assert_auth_message_last(
            related_message      = message.concents.ForceSubtaskResultsResponse,
            provider_public_key  = self._get_encoded_provider_public_key(),
            requestor_public_key = self._get_encoded_requestor_public_key(),
        )

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

        # STEP 1: Provider forces subtask results via Concent.
        # Request is processed correctly.
        serialized_force_subtask_results = self._get_serialized_force_subtask_results(
            timestamp                   = "2018-02-05 10:00:20",
            ack_report_computed_task    = self._get_deserialized_ack_report_computed_task(
                timestamp       = "2018-02-05 10:00:20",
                subtask_id      = "xxyyzz",
                task_to_compute = self._get_deserialized_task_to_compute(
                    timestamp   = "2018-02-05 10:00:00",
                    deadline    = "2018-02-05 10:00:10",
                    task_id     = '1',
                )
            )
        )

        with mock.patch('core.views.base.is_provider_account_status_positive', _get_provider_account_status_true_mock):
            with freeze_time("2018-02-05 10:00:30"):
                response = self.client.post(
                    reverse('core:send'),
                    data                                = serialized_force_subtask_results,
                    content_type                        = 'application/octet-stream',
                    HTTP_CONCENT_CLIENT_PUBLIC_KEY      = self._get_encoded_provider_public_key(),
                    HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
                )

        assert len(response.content) == 0
        assert response.status_code  == 202

        self._test_database_objects(
            last_object_type         = message.concents.ForceSubtaskResults,
            task_id                  = '1',
            receive_delivered_status = False,
        )
        self._assert_auth_message_counter_increased()
        self._assert_auth_message_last(
            related_message         = message.concents.ForceSubtaskResults,
            provider_public_key     = self._get_encoded_provider_public_key(),
            requestor_public_key    = self._get_encoded_requestor_public_key(),
        )

        # STEP 2: Different requestor or provider does not receive forces subtask results via Concent with different or mixed key.
        with freeze_time("2018-02-05 10:00:24"):
            response = self.client.post(
                reverse('core:receive'),
                data                            = '',
                content_type                    = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY  = self._get_encoded_key(self.DIFFERENT_REQUESTOR_PUBLIC_KEY),
            )

        self._test_204_response(response)
        self._assert_auth_message_counter_not_increased()

        with freeze_time("2018-02-05 10:00:24"):
            response = self.client.post(
                reverse('core:receive'),
                data                            = '',
                content_type                    = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY  = self._get_encoded_provider_public_key(),
            )

        self._test_204_response(response)
        self._assert_auth_message_counter_not_increased()

        # STEP 3: Requestor receives forces subtask results via Concent with correct key.
        with freeze_time("2018-02-05 10:00:24"):
            response = self.client.post(
                reverse('core:receive'),
                data                            = '',
                content_type                    = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY  = self._get_encoded_requestor_public_key(),
            )
        deserialized_compute_task_def = self._get_deserialized_compute_task_def(
            deadline    = "2018-02-05 10:00:10",
            task_id     = '1',
        )
        self._test_response(
            response,
            status       = 200,
            key          = self.REQUESTOR_PRIVATE_KEY,
            message_type = message.concents.ForceSubtaskResults,
            fields       = {
                'timestamp':                                                 self._parse_iso_date_to_timestamp("2018-02-05 10:00:24"),
                'ack_report_computed_task.subtask_id':                       'xxyyzz',
                'ack_report_computed_task.task_to_compute.compute_task_def': deserialized_compute_task_def,
            }
        )
        self._assert_auth_message_counter_increased()
        self._assert_auth_message_last(
            related_message         = message.concents.ForceSubtaskResults,
            provider_public_key     = self._get_encoded_provider_public_key(),
            requestor_public_key    = self._get_encoded_requestor_public_key(),
        )

        # STEP 4: Different requestor does not receive subtask result settled via Concent with different key.
        with mock.patch('core.views.base.make_forced_payment', _get_requestor_account_status):
            with freeze_time("2018-02-05 10:00:51"):
                response = self.client.post(
                    reverse('core:receive'),
                    data                            = '',
                    content_type                    = 'application/octet-stream',
                    HTTP_CONCENT_CLIENT_PUBLIC_KEY  = self._get_encoded_key(self.DIFFERENT_REQUESTOR_PUBLIC_KEY),
                )

        self._test_204_response(response)
        self._assert_auth_message_counter_not_increased()

        # STEP 5: Requestor receives subtask result settled via Concent with correct key.
        with mock.patch('core.views.base.make_forced_payment', _get_requestor_account_status):
            with freeze_time("2018-02-05 10:00:51"):
                response = self.client.post(
                    reverse('core:receive'),
                    data                            = '',
                    content_type                    = 'application/octet-stream',
                    HTTP_CONCENT_CLIENT_PUBLIC_KEY  = self._get_encoded_provider_public_key(),
                )
        self._test_response(
            response,
            status       = 200,
            key          = self.PROVIDER_PRIVATE_KEY,
            message_type = message.concents.SubtaskResultsSettled,
            fields       = {
                'timestamp':                        self._parse_iso_date_to_timestamp("2018-02-05 10:00:51"),
                'task_to_compute.compute_task_def': deserialized_compute_task_def,
            }
        )
        self._assert_auth_message_counter_increased()
        self._assert_auth_message_last(
            related_message      = message.concents.SubtaskResultsSettled,
            provider_public_key  = self._get_encoded_provider_public_key(),
            requestor_public_key = self._get_encoded_requestor_public_key(),
        )

        # STEP 6: Different provider does not receive subtask result settled via Concent with different key.
        with freeze_time("2018-02-05 10:00:51"):
            response = self.client.post(
                reverse('core:receive_out_of_band'),
                data                            = '',
                content_type                    = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY  = self._get_encoded_key(self.DIFFERENT_PROVIDER_PUBLIC_KEY),
            )
        self._test_204_response(response)
        self._assert_auth_message_counter_not_increased()

        # STEP 7: Provider receives subtask result settled via Concent with correct key.
        with freeze_time("2018-02-05 10:00:51"):
            response = self.client.post(
                reverse('core:receive_out_of_band'),
                data                            = '',
                content_type                    = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY  = self._get_encoded_requestor_public_key(),
            )
        self._test_response(
            response,
            status       = 200,
            key          = self.REQUESTOR_PRIVATE_KEY,
            message_type = message.concents.SubtaskResultsSettled,
            fields       = {
                'timestamp':                        self._parse_iso_date_to_timestamp("2018-02-05 10:00:51"),
                'task_to_compute.compute_task_def': deserialized_compute_task_def,
            }
        )
        self._assert_auth_message_counter_increased()
        self._assert_auth_message_last(
            related_message      = message.concents.SubtaskResultsSettled,
            provider_public_key  = self._get_encoded_provider_public_key(),
            requestor_public_key = self._get_encoded_requestor_public_key(),
        )

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

        # STEP 1: Provider forces subtask results via Concent.
        # Request is processed correctly.
        serialized_force_subtask_results = self._get_serialized_force_subtask_results(
            timestamp                   = "2018-02-05 10:00:20",
            ack_report_computed_task    = self._get_deserialized_ack_report_computed_task(
                timestamp       = "2018-02-05 10:00:20",
                subtask_id      = "xxyyzz",
                task_to_compute = self._get_deserialized_task_to_compute(
                    timestamp   = "2018-02-05 10:00:00",
                    deadline    = "2018-02-05 10:00:10",
                    task_id     = '1',
                )
            )
        )

        with mock.patch('core.views.base.is_provider_account_status_positive', _get_provider_account_status_true_mock):
            with freeze_time("2018-02-05 10:00:30"):
                response = self.client.post(
                    reverse('core:send'),
                    data                                = serialized_force_subtask_results,
                    content_type                        = 'application/octet-stream',
                    HTTP_CONCENT_CLIENT_PUBLIC_KEY      = self._get_encoded_provider_public_key(),
                    HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
                )

        assert len(response.content) == 0
        assert response.status_code  == 202

        self._test_database_objects(
            last_object_type         = message.concents.ForceSubtaskResults,
            task_id                  = '1',
            receive_delivered_status = False,
        )
        self._assert_auth_message_counter_increased()
        self._assert_auth_message_last(
            related_message         = message.concents.ForceSubtaskResults,
            provider_public_key     = self._get_encoded_provider_public_key(),
            requestor_public_key    = self._get_encoded_requestor_public_key(),
        )

        # STEP 2: Different requestor or provider does not receive forces subtask results via Concent with different or mixed key.
        with freeze_time("2018-02-05 10:00:24"):
            response = self.client.post(
                reverse('core:receive'),
                data                            = '',
                content_type                    = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY  = self._get_encoded_key(self.DIFFERENT_REQUESTOR_PUBLIC_KEY),
            )

        self._test_204_response(response)
        self._assert_auth_message_counter_not_increased()

        with freeze_time("2018-02-05 10:00:24"):
            response = self.client.post(
                reverse('core:receive'),
                data                            = '',
                content_type                    = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY  = self._get_encoded_provider_public_key(),
            )

        self._test_204_response(response)
        self._assert_auth_message_counter_not_increased()

        # STEP 3: Requestor receives forces subtask results via Concent with correct key.
        with freeze_time("2018-02-05 10:00:24"):
            response = self.client.post(
                reverse('core:receive'),
                data                            = '',
                content_type                    = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY  = self._get_encoded_requestor_public_key(),
            )
        deserialized_compute_task_def = self._get_deserialized_compute_task_def(
            deadline    = "2018-02-05 10:00:10",
            task_id     = '1',
        )
        self._test_response(
            response,
            status       = 200,
            key          = self.REQUESTOR_PRIVATE_KEY,
            message_type = message.concents.ForceSubtaskResults,
            fields       = {
                'timestamp':                                                 self._parse_iso_date_to_timestamp("2018-02-05 10:00:24"),
                'ack_report_computed_task.subtask_id':                       'xxyyzz',
                'ack_report_computed_task.task_to_compute.compute_task_def': deserialized_compute_task_def,
            }
        )
        self._assert_auth_message_counter_increased()
        self._assert_auth_message_last(
            related_message         = message.concents.ForceSubtaskResults,
            provider_public_key     = self._get_encoded_provider_public_key(),
            requestor_public_key    = self._get_encoded_requestor_public_key(),
        )

        # STEP 4: Different provider does not receive subtask result settled via Concent with different key.
        with freeze_time("2018-02-05 10:00:51"):
            response = self.client.post(
                reverse('core:receive_out_of_band'),
                data                            = '',
                content_type                    = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY  = self._get_encoded_key(self.DIFFERENT_PROVIDER_PUBLIC_KEY),
            )
        self._test_204_response(response)
        self._assert_auth_message_counter_not_increased()

        # STEP 5: Provider receives subtask result settled via Concent with correct key.
        with freeze_time("2018-02-05 10:00:51"):
            response = self.client.post(
                reverse('core:receive_out_of_band'),
                data                            = '',
                content_type                    = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY  = self._get_encoded_requestor_public_key(),
            )
        self._test_response(
            response,
            status       = 200,
            key          = self.REQUESTOR_PRIVATE_KEY,
            message_type = message.concents.SubtaskResultsSettled,
            fields       = {
                'timestamp':                        self._parse_iso_date_to_timestamp("2018-02-05 10:00:51"),
                'task_to_compute.compute_task_def': deserialized_compute_task_def,
            }
        )
        self._assert_auth_message_counter_increased()
        self._assert_auth_message_last(
            related_message      = message.concents.SubtaskResultsSettled,
            provider_public_key  = self._get_encoded_provider_public_key(),
            requestor_public_key = self._get_encoded_requestor_public_key(),
        )

        # STEP 6: Different requestor does not receive subtask result settled via Concent with different key.
        with mock.patch('core.views.base.make_forced_payment', _get_requestor_account_status):
            with freeze_time("2018-02-05 10:00:51"):
                response = self.client.post(
                    reverse('core:receive'),
                    data                            = '',
                    content_type                    = 'application/octet-stream',
                    HTTP_CONCENT_CLIENT_PUBLIC_KEY  = self._get_encoded_key(self.DIFFERENT_REQUESTOR_PUBLIC_KEY),
                )

        self._test_204_response(response)
        self._assert_auth_message_counter_not_increased()

        # STEP 7: Requestor receives subtask result settled via Concent with correct key.
        with mock.patch('core.views.base.make_forced_payment', _get_requestor_account_status):
            with freeze_time("2018-02-05 10:00:51"):
                response = self.client.post(
                    reverse('core:receive'),
                    data                            = '',
                    content_type                    = 'application/octet-stream',
                    HTTP_CONCENT_CLIENT_PUBLIC_KEY  = self._get_encoded_provider_public_key(),
                )
        self._test_response(
            response,
            status       = 200,
            key          = self.PROVIDER_PRIVATE_KEY,
            message_type = message.concents.SubtaskResultsSettled,
            fields       = {
                'timestamp':                        self._parse_iso_date_to_timestamp("2018-02-05 10:00:51"),
                'task_to_compute.compute_task_def': deserialized_compute_task_def,
            }
        )
        self._assert_auth_message_counter_increased()
        self._assert_auth_message_last(
            related_message      = message.concents.SubtaskResultsSettled,
            provider_public_key  = self._get_encoded_provider_public_key(),
            requestor_public_key = self._get_encoded_requestor_public_key(),
        )
