import mock
from django.test            import override_settings
from django.urls            import reverse
from freezegun              import freeze_time
from golem_messages         import message
from golem_messages.utils import decode_hex

from core.constants         import ETHEREUM_ADDRESS_LENGTH
from core.models            import PendingResponse
from core.payments.backends.sci_backend import TransactionType
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
class ForcePaymentIntegrationTest(ConcentIntegrationTestCase):
    def test_provider_send_force_payment_with_subtask_results_accepted_signed_by_different_requestors_concent_should_refuse(self):
        """
        Expected message exchange:
        Provider  -> Concent:    ForcePayment
        Concent   -> Provider:   ServiceRefused
        """
        subtask_results_accepted_list = [
            self._get_deserialized_subtask_results_accepted(
                timestamp       = "2018-02-05 10:00:15",
                payment_ts      = "2018-02-05 12:00:16",
                task_to_compute = self._get_deserialized_task_to_compute(
                    timestamp                       = "2018-02-05 10:00:00",
                    deadline                        = "2018-02-05 10:00:10",
                    subtask_id='2',
                )
            ),
            self._get_deserialized_subtask_results_accepted(
                timestamp       = "2018-02-05 9:00:15",
                payment_ts      = "2018-02-05 11:00:16",
                task_to_compute = self._get_deserialized_task_to_compute(
                    timestamp                       = "2018-02-05 9:00:00",
                    deadline                        = "2018-02-05 9:00:10",
                    subtask_id='3',
                ),
                sign_with_private_key=self.DIFFERENT_REQUESTOR_PRIVATE_KEY
            )
        ]
        serialized_force_payment = self._get_serialized_force_payment(
            timestamp                     = "2018-02-05 10:00:15",
            subtask_results_accepted_list = subtask_results_accepted_list
        )

        with freeze_time("2018-02-05 10:00:25"):
            response = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_payment,
                content_type                        = 'application/octet-stream',
            )
        self._test_response(
            response,
            status       = 200,
            key          = self.PROVIDER_PRIVATE_KEY,
            message_type = message.concents.ServiceRefused,
            fields       = {
                'reason':    message.concents.ServiceRefused.REASON.InvalidRequest,
                'timestamp': parse_iso_date_to_timestamp("2018-02-05 10:00:25"),
            }
        )
        self._assert_stored_message_counter_not_increased()

    def test_provider_send_force_payment_with_subtask_results_accepted_where_ethereum_accounts_are_different_concent_should_refuse(self):
        """
        Expected message exchange:
        Provider  -> Concent:    ForcePayment
        Concent   -> Provider:   ServiceRefused
        """
        subtask_results_accepted_list = [
            self._get_deserialized_subtask_results_accepted(
                timestamp       = "2018-02-05 10:00:15",
                payment_ts      = "2018-02-05 12:00:16",
                task_to_compute = self._get_deserialized_task_to_compute(
                    timestamp                       = "2018-02-05 10:00:00",
                    deadline                        = "2018-02-05 10:00:10",
                    subtask_id='2',
                )
            ),
            self._get_deserialized_subtask_results_accepted(
                timestamp       = "2018-02-05 9:00:15",
                payment_ts      = "2018-02-05 11:00:16",
                task_to_compute = self._get_deserialized_task_to_compute(
                    timestamp                       = "2018-02-05 9:00:00",
                    deadline                        = "2018-02-05 9:00:10",
                    requestor_ethereum_public_key   = self._get_requestor_ethereum_hex_public_key_different(),
                    subtask_id='3',
                )
            )
        ]
        serialized_force_payment = self._get_serialized_force_payment(
            timestamp                     = "2018-02-05 10:00:15",
            subtask_results_accepted_list = subtask_results_accepted_list
        )

        with freeze_time("2018-02-05 10:00:25"):
            response = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_payment,
                content_type                        = 'application/octet-stream',
            )
        self._test_response(
            response,
            status       = 200,
            key          = self.PROVIDER_PRIVATE_KEY,
            message_type = message.concents.ServiceRefused,
            fields       = {
                'reason':    message.concents.ServiceRefused.REASON.InvalidRequest,
                'timestamp': parse_iso_date_to_timestamp("2018-02-05 10:00:25"),
            }
        )
        self._assert_stored_message_counter_not_increased()

    def test_provider_send_force_payment_beyond_payment_time_concent_should_reject(self):
        """
        Expected message exchange:
        Provider  -> Concent:    ForcePayment
        Concent   -> Provider:   ForcePaymentRejected
        """
        task_to_compute = self._get_deserialized_task_to_compute(
            timestamp                       = "2018-02-05 10:00:00",
            deadline                        = "2018-02-05 10:00:10",
            subtask_id='2',
        )

        subtask_results_accepted_list = [
            self._get_deserialized_subtask_results_accepted(
                timestamp       = "2018-02-05 10:00:15",
                payment_ts      = "2018-02-05 12:00:00",
                task_to_compute = task_to_compute
            ),
            self._get_deserialized_subtask_results_accepted(
                timestamp       = "2018-02-05 9:00:15",
                payment_ts      = "2018-02-05 11:00:00",
                task_to_compute = self._get_deserialized_task_to_compute(
                    timestamp                       = "2018-02-05 9:00:00",
                    deadline                        = "2018-02-05 9:00:10",
                    subtask_id='3',
                )
            )
        ]
        serialized_force_payment = self._get_serialized_force_payment(
            timestamp                     = "2018-02-05 12:00:19",
            subtask_results_accepted_list = subtask_results_accepted_list
        )

        with mock.patch(
            'core.message_handlers.payments_service.get_list_of_payments',
            side_effect=self._get_list_of_force_transactions
        ) as get_list_of_payments_mock_function:
            with freeze_time("2018-02-05 12:00:09"):
                response = self.client.post(
                    reverse('core:send'),
                    data                                = serialized_force_payment,
                    content_type                        = 'application/octet-stream',
                )

        get_list_of_payments_mock_function.assert_called_with(
            requestor_eth_address=task_to_compute.requestor_ethereum_address,
            provider_eth_address=task_to_compute.provider_ethereum_address,
            payment_ts=parse_iso_date_to_timestamp("2018-02-05 11:00:00"),
            current_time=parse_iso_date_to_timestamp("2018-02-05 12:00:09"),
            transaction_type=TransactionType.BATCH,
        )

        self._test_response(
            response,
            status       = 200,
            key          = self.PROVIDER_PRIVATE_KEY,
            message_type = message.concents.ForcePaymentRejected,
            fields       = {
                'reason': message.concents.ForcePaymentRejected.REASON.TimestampError,
                'timestamp': parse_iso_date_to_timestamp("2018-02-05 12:00:09"),
                'force_payment.timestamp': parse_iso_date_to_timestamp("2018-02-05 12:00:19"),
                'force_payment.subtask_results_accepted_list': subtask_results_accepted_list,
            }
        )
        self._assert_stored_message_counter_not_increased()

    def test_provider_send_force_payment_with_invalid_list_of_ether_transactions_concent_should_reject(self):
        """
        Expected message exchange:
        Provider  -> Concent:    ForcePayment
        Concent   -> Provider:   ForcePaymentRejected
        """
        task_to_compute = self._get_deserialized_task_to_compute(
            timestamp                       = "2018-02-05 10:00:00",
            deadline                        = "2018-02-05 10:00:10",
            task_id                         = '2',
            subtask_id                      = '2',
        )

        subtask_results_accepted_list = [
            self._get_deserialized_subtask_results_accepted(
                timestamp       = "2018-02-05 10:00:15",
                payment_ts      = "2018-02-05 12:00:00",
                task_to_compute = task_to_compute
            ),
            self._get_deserialized_subtask_results_accepted(
                timestamp       = "2018-02-05 9:00:15",
                payment_ts      = "2018-02-05 11:00:00",
                task_to_compute = self._get_deserialized_task_to_compute(
                    timestamp                       = "2018-02-05 9:00:00",
                    deadline                        = "2018-02-05 9:00:10",
                    task_id                         = '3',
                    subtask_id                      = '3',
                )
            )
        ]
        serialized_force_payment = self._get_serialized_force_payment(
            timestamp                     = "2018-02-05 12:00:20",
            subtask_results_accepted_list = subtask_results_accepted_list
        )

        with mock.patch(
            'core.message_handlers.payments_service.get_list_of_payments',
            side_effect=self._get_list_of_force_transactions
        ) as get_list_of_payments_mock_function:
            with freeze_time("2018-02-05 12:00:20"):
                response = self.client.post(
                    reverse('core:send'),
                    data                                = serialized_force_payment,
                    content_type                        = 'application/octet-stream',
                )

        get_list_of_payments_mock_function.assert_called_with(
            requestor_eth_address=task_to_compute.requestor_ethereum_address,
            provider_eth_address=task_to_compute.provider_ethereum_address,
            payment_ts=parse_iso_date_to_timestamp("2018-02-05 11:00:00"),
            current_time=parse_iso_date_to_timestamp("2018-02-05 12:00:20"),
            transaction_type=TransactionType.BATCH,
        )

        self._test_response(
            response,
            status       = 200,
            key          = self.PROVIDER_PRIVATE_KEY,
            message_type = message.concents.ForcePaymentRejected,
            fields       = {
                'reason':    message.concents.ForcePaymentRejected.REASON.TimestampError,
                'timestamp': parse_iso_date_to_timestamp("2018-02-05 12:00:20"),
                'force_payment.timestamp': parse_iso_date_to_timestamp("2018-02-05 12:00:20"),
                'force_payment.subtask_results_accepted_list': subtask_results_accepted_list,
            }
        )
        self._assert_stored_message_counter_not_increased()

    def test_provider_send_force_payment_with_no_value_to_be_paid_concent_should_reject(self):
        """
        Expected message exchange:
        Provider  -> Concent:    ForcePayment
        Concent   -> Provider:   ForcePaymentRejected
        """
        task_to_compute = self._get_deserialized_task_to_compute(
            timestamp                       = "2018-02-05 10:00:00",
            deadline                        = "2018-02-05 10:00:10",
            subtask_id='2',
            price                           = 10000,
        )

        subtask_results_accepted_list = [
            self._get_deserialized_subtask_results_accepted(
                timestamp       = "2018-02-05 10:00:15",
                payment_ts      = "2018-02-05 11:55:00",
                task_to_compute = task_to_compute
            ),
            self._get_deserialized_subtask_results_accepted(
                timestamp       = "2018-02-05 9:00:15",
                payment_ts      = "2018-02-05 11:55:00",
                task_to_compute = self._get_deserialized_task_to_compute(
                    timestamp                       = "2018-02-05 9:00:00",
                    deadline                        = "2018-02-05 9:00:10",
                    subtask_id='3',
                    price                           = 3000,
                )
            )
        ]
        serialized_force_payment = self._get_serialized_force_payment(
            timestamp                     = "2018-02-05 12:00:20",
            subtask_results_accepted_list = subtask_results_accepted_list
        )

        with freeze_time("2018-02-05 12:00:20"):
            fake_responses = [
                self._get_list_of_batch_transactions(),
                self._get_list_of_force_transactions()
            ]
            with mock.patch('core.message_handlers.payments_service.get_list_of_payments', side_effect=fake_responses) as get_list_of_payments_mock_function:
                response = self.client.post(
                    reverse('core:send'),
                    data                                = serialized_force_payment,
                    content_type                        = 'application/octet-stream',
                )

        get_list_of_payments_mock_function.assert_called_with(
            requestor_eth_address=task_to_compute.requestor_ethereum_address,
            provider_eth_address=task_to_compute.provider_ethereum_address,
            payment_ts=parse_iso_date_to_timestamp("2018-02-05 11:55:10"),
            current_time=parse_iso_date_to_timestamp("2018-02-05 12:00:20"),
            transaction_type=TransactionType.FORCE,
        )

        self._test_response(
            response,
            status       = 200,
            key          = self.PROVIDER_PRIVATE_KEY,
            message_type = message.concents.ForcePaymentRejected,
            fields       = {
                'reason':    message.concents.ForcePaymentRejected.REASON.NoUnsettledTasksFound,
                'timestamp': parse_iso_date_to_timestamp("2018-02-05 12:00:20"),
                'force_payment.timestamp': parse_iso_date_to_timestamp("2018-02-05 12:00:20"),
                'force_payment.subtask_results_accepted_list': subtask_results_accepted_list,
            }
        )
        self._assert_stored_message_counter_not_increased()

    def test_provider_send_correct_force_payment_concent_should_accept(self):
        """
        Expected message exchange:
        Provider  -> Concent:    ForcePayment
        Concent   -> Provider:   ForcePaymentCommitted
        Concent   -> Requestor:  ForcePaymentCommitted
        """
        task_to_compute = self._get_deserialized_task_to_compute(
            timestamp                       = "2018-02-05 10:00:00",
            deadline                        = "2018-02-05 10:00:10",
            subtask_id='2',
            price                           = 15000,
        )

        subtask_results_accepted_list = [
            self._get_deserialized_subtask_results_accepted(
                timestamp       = "2018-02-05 10:00:15",
                payment_ts      = "2018-02-05 11:55:00",
                task_to_compute = task_to_compute
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

        with freeze_time("2018-02-05 12:00:20"):
            fake_responses = [
                self._get_list_of_batch_transactions(),
                self._get_list_of_force_transactions()
            ]
            with mock.patch(
                'core.message_handlers.payments_service.make_force_payment_to_provider',
                side_effect=self._make_force_payment_to_provider
            ) as make_force_payment_to_provider_mock_function,\
                mock.patch(
                'core.message_handlers.payments_service.get_list_of_payments',
                side_effect=fake_responses
            ) as get_list_of_payments_mock_function:
                response_1 = self.client.post(
                    reverse('core:send'),
                    data                                = serialized_force_payment,
                    content_type                        = 'application/octet-stream',
                )

        make_force_payment_to_provider_mock_function.assert_called_with(
            requestor_eth_address=task_to_compute.requestor_ethereum_address,
            provider_eth_address=task_to_compute.provider_ethereum_address,
            value=9000,
            payment_ts=parse_iso_date_to_timestamp("2018-02-05 12:00:20"),
        )

        get_list_of_payments_mock_function.assert_called_with(
            requestor_eth_address=task_to_compute.requestor_ethereum_address,
            provider_eth_address=task_to_compute.provider_ethereum_address,
            payment_ts=parse_iso_date_to_timestamp("2018-02-05 11:55:10"),
            current_time=parse_iso_date_to_timestamp("2018-02-05 12:00:20"),
            transaction_type=TransactionType.FORCE,
        )

        # Sum of prices from force and batch lists of transactions which have been paid
        amount_paid = 10000 + 3000
        # Sum of price in all TaskToCompute messages minus amount_paid
        amount_pending = 15000 + 7000 - amount_paid

        self._test_response(
            response_1,
            status       = 200,
            key          = self.PROVIDER_PRIVATE_KEY,
            message_type = message.concents.ForcePaymentCommitted,
            fields       = {
                'recipient_type': message.concents.ForcePaymentCommitted.Actor.Provider,
                'timestamp':      parse_iso_date_to_timestamp("2018-02-05 12:00:20"),
                'amount_pending': amount_pending,
                'amount_paid':    amount_paid,
            }
        )
        self._assert_stored_message_counter_not_increased()

        last_pending_message = PendingResponse.objects.filter(delivered = False).order_by('created_at').last()
        self.assertEqual(last_pending_message.response_type,        PendingResponse.ResponseType.ForcePaymentCommitted.name)  # pylint: disable=no-member
        self.assertEqual(last_pending_message.client.public_key_bytes,    self.REQUESTOR_PUBLIC_KEY)

        with freeze_time("2018-02-05 12:00:21"):
            response_2 = self.client.post(
                reverse('core:receive_out_of_band'),
                data                            = self._create_requestor_auth_message(),
                content_type                    = 'application/octet-stream',
            )
        self._test_response(
            response_2,
            status       = 200,
            key          = self.REQUESTOR_PRIVATE_KEY,
            message_type = message.concents.ForcePaymentCommitted,
            fields       = {
                'recipient_type': message.concents.ForcePaymentCommitted.Actor.Requestor,
                'timestamp':      parse_iso_date_to_timestamp("2018-02-05 12:00:21"),
                'amount_pending': amount_pending,
                'amount_paid':    amount_paid,
                'task_owner_key': decode_hex(task_to_compute.requestor_ethereum_public_key),
            }
        )
        self._assert_stored_message_counter_not_increased()
        last_pending_message = PendingResponse.objects.filter(delivered = False).last()
        self.assertIsNone(last_pending_message)

    def test_provider_send_force_payment_with_subtask_results_accepted_list_as_single_message_concent_should_return_http_400(self):
        """
        Expected message exchange:
        Provider  -> Concent:    ForcePayment
        Concent   -> Provider:   HTTP 400
        """
        subtask_results_accepted_list = self._get_deserialized_subtask_results_accepted(
            timestamp       = "2018-02-05 10:00:15",
            payment_ts      = "2018-02-05 12:00:00",
            task_to_compute = self._get_deserialized_task_to_compute(
                timestamp                       = "2018-02-05 10:00:00",
                deadline                        = "2018-02-05 10:00:10",
                task_id                         = '2',
                price                           = 15000,
            )
        )
        serialized_force_payment = self._get_serialized_force_payment(
            timestamp                     = "2018-02-05 12:00:20",
            subtask_results_accepted_list = subtask_results_accepted_list
        )

        with freeze_time("2018-02-05 12:00:20"):
            response = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_payment,
                content_type                        = 'application/octet-stream',
            )

        self._test_400_response(response)
        self._assert_stored_message_counter_not_increased()

    def test_provider_send_force_payment_with_empty_subtask_results_accepted_list_concent_should_return_http_400(self):
        """
        Expected message exchange:
        Provider  -> Concent:    ForcePayment
        Concent   -> Provider:   HTTP 400
        """
        subtask_results_accepted_list = []

        serialized_force_payment = self._get_serialized_force_payment(
            timestamp                     = "2018-02-05 12:00:20",
            subtask_results_accepted_list = subtask_results_accepted_list
        )

        with freeze_time("2018-02-05 12:00:20"):
            response = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_payment,
                content_type                        = 'application/octet-stream',
            )

        self._test_400_response(response)
        self._assert_stored_message_counter_not_increased()

    def test_provider_send_force_payment_with_empty_requestor_ethereum_public_key_concent_should_refuse(self):
        """
        Expected message exchange:
        Provider  -> Concent:    ForcePayment
        Concent   -> Provider:   ServiceRefused
        """
        subtask_results_accepted_list = [
            self._get_deserialized_subtask_results_accepted(
                timestamp       = "2018-02-05 10:00:15",
                payment_ts      = "2018-02-05 12:00:00",
                task_to_compute = self._get_deserialized_task_to_compute(
                    timestamp                       = "2018-02-05 10:00:00",
                    deadline                        = "2018-02-05 10:00:10",
                    task_id                         = '2',
                    price                           = 15000,
                )
            ),
            self._get_deserialized_subtask_results_accepted(
                timestamp       = "2018-02-05 9:00:15",
                payment_ts      = "2018-02-05 11:00:00",
                task_to_compute = self._get_deserialized_task_to_compute(
                    timestamp                       = "2018-02-05 9:00:00",
                    deadline                        = "2018-02-05 9:00:10",
                    task_id                         = '3',
                    requestor_ethereum_public_key   = '',
                    price                           = 15000,
                )
            )
        ]
        serialized_force_payment = self._get_serialized_force_payment(
            timestamp                     = "2018-02-05 12:00:20",
            subtask_results_accepted_list = subtask_results_accepted_list
        )

        with freeze_time("2018-02-05 12:00:20"):
            response = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_payment,
                content_type                        = 'application/octet-stream',
            )

        self._test_response(
            response,
            status       = 200,
            key          = self.PROVIDER_PRIVATE_KEY,
            message_type = message.concents.ServiceRefused,
            fields       = {
                'reason':    message.concents.ServiceRefused.REASON.InvalidRequest,
                'timestamp': parse_iso_date_to_timestamp("2018-02-05 12:00:20"),
            }
        )
        self._assert_stored_message_counter_not_increased()

    def test_provider_send_force_payment_with_same_subtasks_id_concent_should_refuse(self):
        """
        Expected message exchange:
        Provider  -> Concent:    ForcePayment
        Concent   -> Provider:   ServiceRefused
        """
        subtask_results_accepted_list = [
            self._get_deserialized_subtask_results_accepted(
                timestamp       = "2018-02-05 10:00:15",
                payment_ts      = "2018-02-05 12:00:00",
                task_to_compute = self._get_deserialized_task_to_compute(
                    timestamp                       = "2018-02-05 10:00:00",
                    deadline                        = "2018-02-05 10:00:10",
                    task_id                         = '2',
                    subtask_id                      = '4',
                    price                           = 15000,
                )
            ),
            self._get_deserialized_subtask_results_accepted(
                timestamp       = "2018-02-05 9:00:15",
                payment_ts      = "2018-02-05 11:00:00",
                task_to_compute = self._get_deserialized_task_to_compute(
                    timestamp                       = "2018-02-05 9:00:00",
                    deadline                        = "2018-02-05 9:00:10",
                    task_id                         = '2',
                    subtask_id                      = '4',
                    price                           = 15000,
                )
            )
        ]
        serialized_force_payment = self._get_serialized_force_payment(
            timestamp                     = "2018-02-05 12:00:20",
            subtask_results_accepted_list = subtask_results_accepted_list
        )

        with freeze_time("2018-02-05 12:00:20"):
            response = self.client.post(
                reverse('core:send'),
                data                                = serialized_force_payment,
                content_type                        = 'application/octet-stream',
            )

        self._test_response(
            response,
            status       = 200,
            key          = self.PROVIDER_PRIVATE_KEY,
            message_type = message.concents.ServiceRefused,
            fields       = {
                'reason':    message.concents.ServiceRefused.REASON.DuplicateRequest,
                'timestamp': parse_iso_date_to_timestamp("2018-02-05 12:00:20"),
            }
        )
        self._assert_stored_message_counter_not_increased()

    def test_sum_of_payments_when_lists_of_transactions_from_payment_api_are_empty(self):
        """
       Expected message exchange:
        Provider  -> Concent:    ForcePayment
        Concent   -> Provider:   ForcePaymentCommitted
        Concent   -> Requestor:  ForcePaymentCommitted
        """
        task_to_compute = self._get_deserialized_task_to_compute(
            timestamp                       = "2018-02-05 10:00:00",
            deadline                        = "2018-02-05 10:00:10",
            subtask_id='2',
            price                           = 20000,
        )

        subtask_results_accepted_list = [
            self._get_deserialized_subtask_results_accepted(
                timestamp       = "2018-02-05 10:00:15",
                payment_ts      = "2018-02-05 12:00:00",
                task_to_compute = task_to_compute
            ),
            self._get_deserialized_subtask_results_accepted(
                timestamp       = "2018-02-05 9:00:15",
                payment_ts      = "2018-02-05 11:00:00",
                task_to_compute = self._get_deserialized_task_to_compute(
                    timestamp                       = "2018-02-05 9:00:00",
                    deadline                        = "2018-02-05 9:00:10",
                    subtask_id='3',
                    price                           = 5000,
                )
            )
        ]
        serialized_force_payment = self._get_serialized_force_payment(
            timestamp                     = "2018-02-05 12:00:20",
            subtask_results_accepted_list = subtask_results_accepted_list
        )

        with freeze_time("2018-02-05 12:00:20"):
            with mock.patch(
                'core.message_handlers.payments_service.get_list_of_payments',
                side_effect=self._get_empty_list_of_transactions
            ) as get_list_of_payments_mock_function,\
                mock.patch(
                'core.message_handlers.payments_service.make_force_payment_to_provider',
                side_effect=self._make_force_payment_to_provider
            ) as make_force_payment_to_provider_mock_function:
                response_1 = self.client.post(
                    reverse('core:send'),
                    data                                = serialized_force_payment,
                    content_type                        = 'application/octet-stream',
                )

        make_force_payment_to_provider_mock_function.assert_called_with(
            requestor_eth_address=task_to_compute.requestor_ethereum_address,
            provider_eth_address=task_to_compute.provider_ethereum_address,
            value=25000,
            payment_ts=parse_iso_date_to_timestamp("2018-02-05 12:00:20"),
        )

        get_list_of_payments_mock_function.assert_called_with(
            requestor_eth_address=task_to_compute.requestor_ethereum_address,
            provider_eth_address=task_to_compute.provider_ethereum_address,
            payment_ts=parse_iso_date_to_timestamp("2018-02-05 11:00:10"),
            current_time=parse_iso_date_to_timestamp("2018-02-05 12:00:20"),
            transaction_type=TransactionType.FORCE,
        )

        self._test_response(
            response_1,
            status       = 200,
            key          = self.PROVIDER_PRIVATE_KEY,
            message_type = message.concents.ForcePaymentCommitted,
            fields       = {
                'recipient_type': message.concents.ForcePaymentCommitted.Actor.Provider,
                'timestamp':      parse_iso_date_to_timestamp("2018-02-05 12:00:20"),
                'amount_pending': 25000,
                'amount_paid':    0,
            }
        )
        self._assert_stored_message_counter_not_increased()

        with freeze_time("2018-02-05 12:00:21"):
            response_2 = self.client.post(
                reverse('core:receive_out_of_band'),
                data                            = self._create_requestor_auth_message(),
                content_type                    = 'application/octet-stream',
            )
        self._test_response(
            response_2,
            status       = 200,
            key          = self.REQUESTOR_PRIVATE_KEY,
            message_type = message.concents.ForcePaymentCommitted,
            fields       = {
                'recipient_type': message.concents.ForcePaymentCommitted.Actor.Requestor,
                'timestamp':      parse_iso_date_to_timestamp("2018-02-05 12:00:21"),
                'amount_pending': 25000,
                'amount_paid':    0,
                'task_owner_key': decode_hex(task_to_compute.requestor_ethereum_public_key),
            }
        )
        self._assert_stored_message_counter_not_increased()
