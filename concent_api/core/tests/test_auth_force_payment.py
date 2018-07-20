import mock

from django.test            import override_settings
from django.urls            import reverse
from freezegun              import freeze_time
from golem_messages         import message

from core.constants         import ETHEREUM_ADDRESS_LENGTH
from core.models            import PendingResponse
from core.tests.utils       import ConcentIntegrationTestCase
from core.tests.utils import parse_iso_date_to_timestamp
from common.testing_helpers  import generate_ecc_key_pair


(CONCENT_PRIVATE_KEY, CONCENT_PUBLIC_KEY) = generate_ecc_key_pair()


@override_settings(
    CONCENT_PRIVATE_KEY  = CONCENT_PRIVATE_KEY,
    CONCENT_PUBLIC_KEY   = CONCENT_PUBLIC_KEY,
    PAYMENT_DUE_TIME     = 10,  # seconds
    CONCENT_ETHEREUM_ADDRESS = 'x' * ETHEREUM_ADDRESS_LENGTH
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
                payment_ts      = "2018-02-05 11:55:00",
                task_to_compute = self._get_deserialized_task_to_compute(
                    timestamp                       = "2018-02-05 10:00:00",
                    deadline                        = "2018-02-05 10:00:10",
                    subtask_id='2',
                    price                           = 15000,
                )
            ),
            self._get_deserialized_subtask_results_accepted(
                timestamp       = "2018-02-05 9:00:15",
                payment_ts      = "2018-02-05 11:55:00",
                task_to_compute = self._get_deserialized_task_to_compute(
                    timestamp                       = "2018-02-05 9:00:00",
                    deadline                        = "2018-02-05 9:00:10",
                    subtask_id='3',
                    price                           = 7000,
                )
            )
        ]
        serialized_force_payment = self._get_serialized_force_payment(
            timestamp                     = "2018-02-05 12:00:20",
            subtask_results_accepted_list = subtask_results_accepted_list
        )

        with mock.patch(
            'core.message_handlers.payments_service.make_force_payment_to_provider',
            side_effect=self._make_force_payment_to_provider
        ) as make_force_payment_to_provider_mock:
            with freeze_time("2018-02-05 12:00:20"):
                fake_responses = [
                    self._get_list_of_batch_transactions(),
                    self._get_list_of_force_transactions(),
                ]
                with mock.patch(
                    'core.message_handlers.payments_service.get_list_of_payments',
                    side_effect=fake_responses
                ) as get_list_of_payments_mock:
                    response_1 = self.client.post(
                        reverse('core:send'),
                        data                                = serialized_force_payment,
                        content_type                        = 'application/octet-stream',
                    )

        make_force_payment_to_provider_mock.assert_called_once()
        self.assertEqual(get_list_of_payments_mock.call_count, 2)

        self._test_response(
            response_1,
            status       = 200,
            key          = self.PROVIDER_PRIVATE_KEY,
            message_type = message.concents.ForcePaymentCommitted,
            fields       = {
                'recipient_type': message.concents.ForcePaymentCommitted.Actor.Provider,
                'timestamp': parse_iso_date_to_timestamp("2018-02-05 12:00:20"),
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
                'timestamp': parse_iso_date_to_timestamp("2018-02-05 12:00:23"),
            }
        )

        self._assert_stored_message_counter_not_increased()

        self._assert_client_count_is_equal(1)

        last_pending_message = PendingResponse.objects.filter(delivered = False).last()
        self.assertIsNone(last_pending_message)
