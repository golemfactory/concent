import mock

from django.test            import override_settings
from django.urls            import reverse
from freezegun              import freeze_time
from golem_messages         import message

from core.models            import PendingResponse
from core.tests.utils       import ConcentIntegrationTestCase
from utils.helpers          import get_current_utc_timestamp
from utils.testing_helpers  import generate_ecc_key_pair


(CONCENT_PRIVATE_KEY, CONCENT_PUBLIC_KEY) = generate_ecc_key_pair()


def _get_requestor_valid_list_of_transactions(current_time, request):  # pylint: disable=unused-argument
    current_time = get_current_utc_timestamp()
    return [{'timestamp': current_time - 3700}, {'timestamp': current_time - 3800}, {'timestamp': current_time - 3900}]


def _get_payment_summary_positive(request, subtask_results_accepted_list, list_of_transactions, list_of_forced_payments):  # pylint: disable=unused-argument
    return 1


@override_settings(
    CONCENT_PRIVATE_KEY  = CONCENT_PRIVATE_KEY,
    CONCENT_PUBLIC_KEY   = CONCENT_PUBLIC_KEY,
    PAYMENT_DUE_TIME     = 10,  # seconds
)
class AuthForcePaymentIntegrationTest(ConcentIntegrationTestCase):
    def test_provider_send_force_payment_and_concent_should_return_it_to_requestor_with_correct_keys(self):
        """
        Expected message exchange:
        Provider  -> Concent:                   ForcePayment
        Concent   -> Provider:                  ForcePaymentCommitted
        Concent   -> WrongRequestor/Provider:   HTTP 204
        Concent   -> Requestor:                 ForcePaymentCommitted
        """
        subtask_results_accepted_list = [
            self._get_deserialized_subtask_results_accepted(
                timestamp       = "2018-02-05 10:00:15",
                payment_ts      = "2018-02-05 12:00:00",
                task_to_compute = self._get_deserialized_task_to_compute(
                    timestamp                       = "2018-02-05 10:00:00",
                    deadline                        = "2018-02-05 10:00:10",
                    task_id                         = '2',
                    requestor_ethereum_public_key   = self._get_encoded_requestor_ethereum_public_key(),
                )
            ),
            self._get_deserialized_subtask_results_accepted(
                timestamp       = "2018-02-05 9:00:15",
                payment_ts      = "2018-02-05 11:00:00",
                task_to_compute = self._get_deserialized_task_to_compute(
                    timestamp                       = "2018-02-05 9:00:00",
                    deadline                        = "2018-02-05 9:00:10",
                    task_id                         = '3',
                    requestor_ethereum_public_key   = self._get_encoded_requestor_ethereum_public_key(),
                )
            )
        ]
        serialized_force_payment = self._get_serialized_force_payment(
            timestamp                     = "2018-02-05 12:00:20",
            subtask_results_accepted_list = subtask_results_accepted_list
        )

        with freeze_time("2018-02-05 12:00:20"):
            with mock.patch('core.message_handlers.base.get_list_of_transactions', _get_requestor_valid_list_of_transactions):
                with mock.patch('core.message_handlers.base.payment_summary', _get_payment_summary_positive):
                    response_1 = self.client.post(
                        reverse('core:send'),
                        data                                = serialized_force_payment,
                        content_type                        = 'application/octet-stream',
                        HTTP_CONCENT_CLIENT_PUBLIC_KEY      = self._get_encoded_provider_public_key(),
                        HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
                    )
        self._test_response(
            response_1,
            status       = 200,
            key          = self.PROVIDER_PRIVATE_KEY,
            message_type = message.concents.ForcePaymentCommitted,
            fields       = {
                'recipient_type': message.concents.ForcePaymentCommitted.Actor.Provider,
                'timestamp':      self._parse_iso_date_to_timestamp("2018-02-05 12:00:20"),
            }
        )
        self._assert_stored_message_counter_not_increased()

        last_pending_message = PendingResponse.objects.filter(delivered = False).order_by('created_at').last()
        self.assertEqual(last_pending_message.response_type,        PendingResponse.ResponseType.ForcePaymentCommitted.name)  # pylint: disable=no-member
        self.assertEqual(last_pending_message.client.public_key,    self._get_encoded_requestor_public_key())

        with freeze_time("2018-02-05 12:00:21"):
            response_2 = self.client.post(
                reverse('core:receive_out_of_band'),
                data                            = self._create_provider_auth_message(),
                content_type                    = 'application/octet-stream',
            )

        self._test_204_response(response_2)
        self._assert_stored_message_counter_not_increased()

        with freeze_time("2018-02-05 12:00:22"):
            response_3 = self.client.post(
                reverse('core:receive_out_of_band'),
                data                            = self._create_diff_requestor_auth_message(),
                content_type                    = 'application/octet-stream',
            )

        self._test_204_response(response_3)
        self._assert_stored_message_counter_not_increased()

        with freeze_time("2018-02-05 12:00:23"):
            response_4 = self.client.post(
                reverse('core:receive_out_of_band'),
                data                            = self._create_requestor_auth_message(),
                content_type                    = 'application/octet-stream',
            )
        self._test_response(
            response_4,
            status       = 200,
            key          = self.REQUESTOR_PRIVATE_KEY,
            message_type = message.concents.ForcePaymentCommitted,
            fields       = {
                'recipient_type': message.concents.ForcePaymentCommitted.Actor.Requestor,
                'timestamp':      self._parse_iso_date_to_timestamp("2018-02-05 12:00:23"),
            }
        )

        self._assert_stored_message_counter_not_increased()

        self._assert_client_count_is_equal(1)

        last_pending_message = PendingResponse.objects.filter(delivered = False).last()
        self.assertIsNone(last_pending_message)
