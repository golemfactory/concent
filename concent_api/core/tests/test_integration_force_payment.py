import mock

from django.test            import override_settings
from django.urls            import reverse
from freezegun              import freeze_time
from golem_messages         import message

from core.tests.utils       import ConcentIntegrationTestCase
from utils.helpers          import get_current_utc_timestamp
from utils.testing_helpers  import generate_ecc_key_pair


(CONCENT_PRIVATE_KEY, CONCENT_PUBLIC_KEY) = generate_ecc_key_pair()


def _get_requestor_valid_list_of_transactions(current_time, request):  # pylint: disable=unused-argument
    current_time = get_current_utc_timestamp()
    return [{'timestamp': current_time - 3700}, {'timestamp': current_time - 3800}, {'timestamp': current_time - 3900}]


def _get_requestor_invalid_list_of_transactions(current_time, request):  # pylint: disable=unused-argument
    current_time = get_current_utc_timestamp()
    return [{'timestamp': current_time - 22}, {'timestamp': current_time - 23}, {'timestamp': current_time - 24}]


def _get_payment_summary_negative(request, subtask_results_accepted_list, list_of_transactions, list_of_forced_payments):  # pylint: disable=unused-argument
    return -1


def _get_payment_summary_positive(request, subtask_results_accepted_list, list_of_transactions, list_of_forced_payments):  # pylint: disable=unused-argument
    return 1


@override_settings(
    CONCENT_PRIVATE_KEY  = CONCENT_PRIVATE_KEY,
    CONCENT_PUBLIC_KEY   = CONCENT_PUBLIC_KEY,
    PAYMENT_DUE_TIME     = 10,  # seconds
    PAYMENT_GRACE_PERIOD = 10,  # seconds
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
                    task_id                         = '2',
                    requestor_public_key            = self._get_encoded_requestor_public_key(),
                    requestor_ethereum_public_key   = self._get_encoded_requestor_ethereum_public_key(),
                )
            ),
            self._get_deserialized_subtask_results_accepted(
                timestamp       = "2018-02-05 9:00:15",
                payment_ts      = "2018-02-05 11:00:16",
                task_to_compute = self._get_deserialized_task_to_compute(
                    timestamp                       = "2018-02-05 9:00:00",
                    deadline                        = "2018-02-05 9:00:10",
                    task_id                         = '3',
                    requestor_public_key            = self._get_encoded_requestor_different_public_key(),
                    requestor_ethereum_public_key   = None,
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
                HTTP_CONCENT_CLIENT_PUBLIC_KEY      = self._get_encoded_provider_public_key(),
                HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
            )
        self._test_response(
            response,
            status       = 200,
            key          = self.PROVIDER_PRIVATE_KEY,
            message_type = message.concents.ServiceRefused,
            fields       = {
                'reason':    message.concents.ServiceRefused.REASON.InvalidRequest,
                'timestamp': self._parse_iso_date_to_timestamp("2018-02-05 10:00:25"),
            }
        )

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
                    task_id                         = '2',
                    requestor_public_key            = self._get_encoded_requestor_public_key(),
                    requestor_ethereum_public_key   = self._get_encoded_requestor_ethereum_public_key(),
                )
            ),
            self._get_deserialized_subtask_results_accepted(
                timestamp       = "2018-02-05 9:00:15",
                payment_ts      = "2018-02-05 11:00:16",
                task_to_compute = self._get_deserialized_task_to_compute(
                    timestamp                       = "2018-02-05 9:00:00",
                    deadline                        = "2018-02-05 9:00:10",
                    task_id                         = '3',
                    requestor_public_key            = self._get_encoded_requestor_public_key(),
                    requestor_ethereum_public_key   = self._get_encoded_requestor_ethereum_different_public_key(),
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
                HTTP_CONCENT_CLIENT_PUBLIC_KEY      = self._get_encoded_provider_public_key(),
                HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
            )
        self._test_response(
            response,
            status       = 200,
            key          = self.PROVIDER_PRIVATE_KEY,
            message_type = message.concents.ServiceRefused,
            fields       = {
                'reason':    message.concents.ServiceRefused.REASON.InvalidRequest,
                'timestamp': self._parse_iso_date_to_timestamp("2018-02-05 10:00:25"),
            }
        )

    def test_provider_send_force_payment_beyond_payment_time_concent_should_reject(self):
        """
        Expected message exchange:
        Provider  -> Concent:    ForcePayment
        Concent   -> Provider:   ForcePaymentRejected
        """
        subtask_results_accepted_list = [
            self._get_deserialized_subtask_results_accepted(
                timestamp       = "2018-02-05 10:00:15",
                payment_ts      = "2018-02-05 12:00:00",
                task_to_compute = self._get_deserialized_task_to_compute(
                    timestamp                       = "2018-02-05 10:00:00",
                    deadline                        = "2018-02-05 10:00:10",
                    task_id                         = '2',
                    requestor_public_key            = self._get_encoded_requestor_public_key(),
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
                    requestor_public_key            = self._get_encoded_requestor_public_key(),
                    requestor_ethereum_public_key   = self._get_encoded_requestor_ethereum_public_key(),
                )
            )
        ]
        serialized_force_payment = self._get_serialized_force_payment(
            timestamp                     = "2018-02-05 12:00:19",
            subtask_results_accepted_list = subtask_results_accepted_list
        )

        with freeze_time("2018-02-05 12:00:19"):
            with mock.patch('core.views.base.get_list_of_transactions', _get_requestor_valid_list_of_transactions):

                response = self.client.post(
                    reverse('core:send'),
                    data                                = serialized_force_payment,
                    content_type                        = 'application/octet-stream',
                    HTTP_CONCENT_CLIENT_PUBLIC_KEY      = self._get_encoded_provider_public_key(),
                    HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
                )
        self._test_response(
            response,
            status       = 200,
            key          = self.PROVIDER_PRIVATE_KEY,
            message_type = message.concents.ForcePaymentRejected,
            fields       = {
                'reason':    message.concents.ForcePaymentRejected.REASON.TimestampError,
                'timestamp': self._parse_iso_date_to_timestamp("2018-02-05 12:00:19"),
            }
        )

    def test_provider_send_force_payment_with_invalid_list_of_ether_transactions_concent_should_reject(self):
        """
        Expected message exchange:
        Provider  -> Concent:    ForcePayment
        Concent   -> Provider:   ForcePaymentRejected
        """
        subtask_results_accepted_list = [
            self._get_deserialized_subtask_results_accepted(
                timestamp       = "2018-02-05 10:00:15",
                payment_ts      = "2018-02-05 12:00:00",
                task_to_compute = self._get_deserialized_task_to_compute(
                    timestamp                       = "2018-02-05 10:00:00",
                    deadline                        = "2018-02-05 10:00:10",
                    task_id                         = '2',
                    requestor_public_key            = self._get_encoded_requestor_public_key(),
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
                    requestor_public_key            = self._get_encoded_requestor_public_key(),
                    requestor_ethereum_public_key   = self._get_encoded_requestor_ethereum_public_key(),
                )
            )
        ]
        serialized_force_payment = self._get_serialized_force_payment(
            timestamp                     = "2018-02-05 12:00:20",
            subtask_results_accepted_list = subtask_results_accepted_list
        )

        with freeze_time("2018-02-05 12:00:20"):
            with mock.patch('core.views.base.get_list_of_transactions', _get_requestor_invalid_list_of_transactions):

                response = self.client.post(
                    reverse('core:send'),
                    data                                = serialized_force_payment,
                    content_type                        = 'application/octet-stream',
                    HTTP_CONCENT_CLIENT_PUBLIC_KEY      = self._get_encoded_provider_public_key(),
                    HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
                )
        self._test_response(
            response,
            status       = 200,
            key          = self.PROVIDER_PRIVATE_KEY,
            message_type = message.concents.ForcePaymentRejected,
            fields       = {
                'reason':    message.concents.ForcePaymentRejected.REASON.TimestampError,
                'timestamp': self._parse_iso_date_to_timestamp("2018-02-05 12:00:20"),
            }
        )

    def test_provider_send_force_payment_with_no_value_to_be_paid_concent_should_reject(self):
        """
        Expected message exchange:
        Provider  -> Concent:    ForcePayment
        Concent   -> Provider:   ForcePaymentRejected
        """
        subtask_results_accepted_list = [
            self._get_deserialized_subtask_results_accepted(
                timestamp       = "2018-02-05 10:00:15",
                payment_ts      = "2018-02-05 12:00:00",
                task_to_compute = self._get_deserialized_task_to_compute(
                    timestamp                       = "2018-02-05 10:00:00",
                    deadline                        = "2018-02-05 10:00:10",
                    task_id                         = '2',
                    requestor_public_key            = self._get_encoded_requestor_public_key(),
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
                    requestor_public_key            = self._get_encoded_requestor_public_key(),
                    requestor_ethereum_public_key   = self._get_encoded_requestor_ethereum_public_key(),
                )
            )
        ]
        serialized_force_payment = self._get_serialized_force_payment(
            timestamp                     = "2018-02-05 12:00:20",
            subtask_results_accepted_list = subtask_results_accepted_list
        )

        with freeze_time("2018-02-05 12:00:20"):
            with mock.patch('core.views.base.get_list_of_transactions', _get_requestor_valid_list_of_transactions):
                with mock.patch('core.views.base.payment_summary', _get_payment_summary_negative):
                    response = self.client.post(
                        reverse('core:send'),
                        data                                = serialized_force_payment,
                        content_type                        = 'application/octet-stream',
                        HTTP_CONCENT_CLIENT_PUBLIC_KEY      = self._get_encoded_provider_public_key(),
                        HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY = self._get_encoded_requestor_public_key(),
                    )
        self._test_response(
            response,
            status       = 200,
            key          = self.PROVIDER_PRIVATE_KEY,
            message_type = message.concents.ForcePaymentRejected,
            fields       = {
                'reason':    message.concents.ForcePaymentRejected.REASON.NoUnsettledTasksFound,
                'timestamp': self._parse_iso_date_to_timestamp("2018-02-05 12:00:20"),
            }
        )

    def test_provider_send_correct_force_payment_concent_should_accept(self):
        """
        Expected message exchange:
        Provider  -> Concent:    ForcePayment
        Concent   -> Provider:   ForcePaymentCommitted
        Concent   -> Requestor:  ForcePaymentCommitted
        """
        subtask_results_accepted_list = [
            self._get_deserialized_subtask_results_accepted(
                timestamp       = "2018-02-05 10:00:15",
                payment_ts      = "2018-02-05 12:00:00",
                task_to_compute = self._get_deserialized_task_to_compute(
                    timestamp                       = "2018-02-05 10:00:00",
                    deadline                        = "2018-02-05 10:00:10",
                    task_id                         = '2',
                    requestor_public_key            = self._get_encoded_requestor_public_key(),
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
                    requestor_public_key            = self._get_encoded_requestor_public_key(),
                    requestor_ethereum_public_key   = self._get_encoded_requestor_ethereum_public_key(),
                )
            )
        ]
        serialized_force_payment = self._get_serialized_force_payment(
            timestamp                     = "2018-02-05 12:00:20",
            subtask_results_accepted_list = subtask_results_accepted_list
        )

        with freeze_time("2018-02-05 12:00:20"):
            with mock.patch('core.views.base.get_list_of_transactions', _get_requestor_valid_list_of_transactions):
                with mock.patch('core.views.base.payment_summary', _get_payment_summary_positive):
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

        self._test_database_objects(
            last_object_type         = message.concents.ForcePaymentCommitted,
            task_id                  = None,
        )

        with freeze_time("2018-02-05 12:00:21"):
            response_2 = self.client.post(
                reverse('core:receive_out_of_band'),
                data                            = '',
                content_type                    = 'application/octet-stream',
                HTTP_CONCENT_CLIENT_PUBLIC_KEY  = self._get_encoded_requestor_public_key(),
            )
        self._test_response(
            response_2,
            status       = 200,
            key          = self.REQUESTOR_PRIVATE_KEY,
            message_type = message.concents.ForcePaymentCommitted,
            fields       = {
                'recipient_type': message.concents.ForcePaymentCommitted.Actor.Requestor,
                'timestamp':      self._parse_iso_date_to_timestamp("2018-02-05 12:00:21"),
            }
        )
