import mock
from django.test            import override_settings
from freezegun              import freeze_time
from golem_messages         import message
from golem_messages.utils import decode_hex

from common.testing_helpers import generate_ecc_key_pair
from core.constants import ETHEREUM_PUBLIC_KEY_LENGTH
from core.exceptions import BanksterTimestampError
from core.models import PendingResponse
from core.tests.utils import ConcentIntegrationTestCase
from core.tests.utils import parse_iso_date_to_timestamp
from core.utils import hex_to_bytes_convert


(CONCENT_PRIVATE_KEY, CONCENT_PUBLIC_KEY) = generate_ecc_key_pair()


@override_settings(
    CONCENT_PRIVATE_KEY  = CONCENT_PRIVATE_KEY,
    CONCENT_PUBLIC_KEY   = CONCENT_PUBLIC_KEY,
    PAYMENT_DUE_TIME     = 10,  # seconds
    CONCENT_ETHEREUM_PUBLIC_KEY='x' * ETHEREUM_PUBLIC_KEY_LENGTH,
)
class ForcePaymentIntegrationTest(ConcentIntegrationTestCase):

    def setUp(self):
        super().setUp()
        self.amount_pending = 0
        self.amount_paid = 10

    def test_provider_send_force_payment_with_subtask_results_accepted_signed_by_different_requestors_concent_should_refuse(self):
        """
        Expected message exchange:
        Provider  -> Concent:    ForcePayment
        Concent   -> Provider:   ServiceRefused
        """
        subtask_results_accepted_list = [
            self._get_deserialized_subtask_results_accepted(
                timestamp="2018-02-05 10:00:15",
                payment_ts="2018-02-05 12:00:16",
                task_to_compute=self._get_deserialized_task_to_compute(
                    timestamp="2018-02-05 10:00:00",
                    deadline="2018-02-05 10:00:10",
                    subtask_id=self._get_uuid('1'),
                )
            ),
            self._get_deserialized_subtask_results_accepted(
                timestamp="2018-02-05 9:00:15",
                payment_ts="2018-02-05 11:00:16",
                task_to_compute=self._get_deserialized_task_to_compute(
                    timestamp="2018-02-05 9:00:00",
                    deadline="2018-02-05 9:00:10",
                    subtask_id=self._get_uuid('2'),
                ),
                signer_private_key=self.DIFFERENT_REQUESTOR_PRIVATE_KEY
            )
        ]
        serialized_force_payment = self._get_serialized_force_payment(
            timestamp                     = "2018-02-05 10:00:15",
            subtask_results_accepted_list = subtask_results_accepted_list
        )

        with freeze_time("2018-02-05 10:00:25"):
            response =self.send_request(
                url='core:send',
                data                                = serialized_force_payment,
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
                    subtask_id=self._get_uuid('1'),
                )
            ),
            self._get_deserialized_subtask_results_accepted(
                timestamp       = "2018-02-05 9:00:15",
                payment_ts      = "2018-02-05 11:00:16",
                task_to_compute = self._get_deserialized_task_to_compute(
                    timestamp                       = "2018-02-05 9:00:00",
                    deadline                        = "2018-02-05 9:00:10",
                    requestor_ethereum_public_key   = self._get_requestor_ethereum_hex_public_key_different(),
                    requestor_ethereum_private_key  = self.DIFFERENT_REQUESTOR_PRIV_ETH_KEY,
                    subtask_id=self._get_uuid('2'),
                )
            )
        ]
        serialized_force_payment = self._get_serialized_force_payment(
            timestamp                     = "2018-02-05 10:00:15",
            subtask_results_accepted_list = subtask_results_accepted_list
        )

        with freeze_time("2018-02-05 10:00:25"):
            response =self.send_request(
                url='core:send',
                data                                = serialized_force_payment,
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
            subtask_id=self._get_uuid('1'),
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
                    subtask_id=self._get_uuid('2'),
                )
            )
        ]
        serialized_force_payment = self._get_serialized_force_payment(
            timestamp                     = "2018-02-05 12:00:19",
            subtask_results_accepted_list = subtask_results_accepted_list
        )

        with freeze_time("2018-02-05 12:00:09"):
            response =self.send_request(
                url='core:send',
                data                                = serialized_force_payment,
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
            task_id                         = self._get_uuid('1'),
            subtask_id                      = self._get_uuid('1'),
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
                    task_id                         = self._get_uuid('2'),
                    subtask_id                      = self._get_uuid('2'),
                )
            )
        ]
        serialized_force_payment = self._get_serialized_force_payment(
            timestamp                     = "2018-02-05 12:00:20",
            subtask_results_accepted_list = subtask_results_accepted_list
        )

        with mock.patch(
            'core.message_handlers.bankster.settle_overdue_acceptances',
            side_effect=BanksterTimestampError
        ) as settle_overdue_acceptances:
            with freeze_time("2018-02-05 12:00:20"):
                response =self.send_request(
                    url='core:send',
                    data                                = serialized_force_payment,
                )

        settle_overdue_acceptances.assert_called_with(
            requestor_ethereum_address=task_to_compute.requestor_ethereum_address,
            provider_ethereum_address=task_to_compute.provider_ethereum_address,
            acceptances=subtask_results_accepted_list,
            requestor_public_key=hex_to_bytes_convert(task_to_compute.requestor_public_key),
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
            subtask_id=self._get_uuid('1'),
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
                    subtask_id=self._get_uuid('2'),
                    price                           = 3000,
                )
            )
        ]
        serialized_force_payment = self._get_serialized_force_payment(
            timestamp                     = "2018-02-05 12:00:20",
            subtask_results_accepted_list = subtask_results_accepted_list
        )

        with freeze_time("2018-02-05 12:00:20"):
            with mock.patch(
                'core.message_handlers.bankster.settle_overdue_acceptances',
                return_value=None
            ) as settle_overdue_acceptances:
                response = self.send_request(
                    url='core:send',
                    data                                = serialized_force_payment,
                )

        settle_overdue_acceptances.assert_called_with(
            requestor_ethereum_address=task_to_compute.requestor_ethereum_address,
            provider_ethereum_address=task_to_compute.provider_ethereum_address,
            acceptances=subtask_results_accepted_list,
            requestor_public_key=hex_to_bytes_convert(task_to_compute.requestor_public_key),
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
            subtask_id=self._get_uuid('1'),
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
                    subtask_id=self._get_uuid('2'),
                    price                           = 7000,
                )
            )
        ]

        serialized_force_payment = self._get_serialized_force_payment(
            timestamp                     = "2018-02-05 12:00:20",
            subtask_results_accepted_list = subtask_results_accepted_list
        )

        with freeze_time("2018-02-05 12:00:20"):
            with mock.patch(
                'core.message_handlers.bankster.settle_overdue_acceptances',
                side_effect=self.settle_overdue_acceptances_mock
            ) as settle_overdue_acceptances:
                response_1 =self.send_request(
                    url='core:send',
                    data                                = serialized_force_payment,
                )

        settle_overdue_acceptances.assert_called_with(
            requestor_ethereum_address=task_to_compute.requestor_ethereum_address,
            provider_ethereum_address=task_to_compute.provider_ethereum_address,
            acceptances=subtask_results_accepted_list,
            requestor_public_key=hex_to_bytes_convert(task_to_compute.requestor_public_key),
        )

        self._test_response(
            response_1,
            status       = 200,
            key          = self.PROVIDER_PRIVATE_KEY,
            message_type = message.concents.ForcePaymentCommitted,
            fields       = {
                'recipient_type': message.concents.ForcePaymentCommitted.Actor.Provider,
                'timestamp': parse_iso_date_to_timestamp("2018-02-05 12:00:20"),
                'amount_pending': self.amount_pending,
                'amount_paid': self.amount_paid,
            }
        )
        self._assert_stored_message_counter_not_increased()

        last_pending_message = PendingResponse.objects.filter(delivered = False).order_by('created_at').last()
        self.assertEqual(last_pending_message.response_type,        PendingResponse.ResponseType.ForcePaymentCommitted.name)  # pylint: disable=no-member
        self.assertEqual(last_pending_message.client.public_key_bytes,    self.REQUESTOR_PUBLIC_KEY)

        with freeze_time("2018-02-05 12:00:21"):
            response_2 =self.send_request(
                url='core:receive',
                data                            = self._create_requestor_auth_message(),
            )
        self._test_response(
            response_2,
            status       = 200,
            key          = self.REQUESTOR_PRIVATE_KEY,
            message_type = message.concents.ForcePaymentCommitted,
            fields       = {
                'recipient_type': message.concents.ForcePaymentCommitted.Actor.Requestor,
                'timestamp': parse_iso_date_to_timestamp("2018-02-05 12:00:21"),
                'amount_pending': self.amount_pending,
                'amount_paid': self.amount_paid,
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
                task_id                         = self._get_uuid(),
                price                           = 15000,
            )
        )
        serialized_force_payment = self._get_serialized_force_payment(
            timestamp                     = "2018-02-05 12:00:20",
            subtask_results_accepted_list = subtask_results_accepted_list
        )

        with freeze_time("2018-02-05 12:00:20"):
            response =self.send_request(
                url='core:send',
                data                                = serialized_force_payment,
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
            response =self.send_request(
                url='core:send',
                data                                = serialized_force_payment,
            )

        self._test_400_response(response)
        self._assert_stored_message_counter_not_increased()

    def test_provider_send_force_payment_with_same_subtasks_id_concent_should_refuse(self):
        """
        Expected message exchange:
        Provider  -> Concent:    ForcePayment
        Concent   -> Provider:   ServiceRefused
        """
        task_to_compute = self._get_deserialized_task_to_compute(
            timestamp="2018-02-05 10:00:00",
            deadline="2018-02-05 10:00:10",
            price=15000,
        )

        subtask_results_accepted_list = [
            self._get_deserialized_subtask_results_accepted(
                timestamp="2018-02-05 10:00:15",
                payment_ts="2018-02-05 12:00:00",
                task_to_compute=task_to_compute
            ),
            self._get_deserialized_subtask_results_accepted(
                timestamp="2018-02-05 9:00:15",
                payment_ts="2018-02-05 11:00:00",
                task_to_compute=task_to_compute
            )
        ]
        serialized_force_payment = self._get_serialized_force_payment(
            timestamp                     = "2018-02-05 12:00:20",
            subtask_results_accepted_list = subtask_results_accepted_list
        )

        with freeze_time("2018-02-05 12:00:20"):
            response =self.send_request(
                url='core:send',
                data                                = serialized_force_payment,
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
            subtask_id=self._get_uuid('1'),
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
                    subtask_id=self._get_uuid('2'),
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
                'core.message_handlers.bankster.settle_overdue_acceptances',
                side_effect=self.settle_overdue_acceptances_mock
            ) as settle_overdue_acceptances:
                response_1 =self.send_request(
                    url='core:send',
                    data                                = serialized_force_payment,
                )

        settle_overdue_acceptances.assert_called_with(
            requestor_ethereum_address=task_to_compute.requestor_ethereum_address,
            provider_ethereum_address=task_to_compute.provider_ethereum_address,
            acceptances=subtask_results_accepted_list,
            requestor_public_key=hex_to_bytes_convert(task_to_compute.requestor_public_key),
        )

        self._test_response(
            response_1,
            status       = 200,
            key          = self.PROVIDER_PRIVATE_KEY,
            message_type = message.concents.ForcePaymentCommitted,
            fields       = {
                'recipient_type': message.concents.ForcePaymentCommitted.Actor.Provider,
                'timestamp': parse_iso_date_to_timestamp("2018-02-05 12:00:20"),
                'amount_pending': self.amount_pending,
                'amount_paid': self.amount_paid,
            }
        )
        self._assert_stored_message_counter_not_increased()

        with freeze_time("2018-02-05 12:00:21"):
            response_2 =self.send_request(
                url='core:receive',
                data                            = self._create_requestor_auth_message(),
            )
        self._test_response(
            response_2,
            status       = 200,
            key          = self.REQUESTOR_PRIVATE_KEY,
            message_type = message.concents.ForcePaymentCommitted,
            fields       = {
                'recipient_type': message.concents.ForcePaymentCommitted.Actor.Requestor,
                'timestamp': parse_iso_date_to_timestamp("2018-02-05 12:00:21"),
                'amount_pending': self.amount_pending,
                'amount_paid': self.amount_paid,
                'task_owner_key': decode_hex(task_to_compute.requestor_ethereum_public_key),
            }
        )
        self._assert_stored_message_counter_not_increased()
