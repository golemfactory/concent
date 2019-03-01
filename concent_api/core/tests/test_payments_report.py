import base64
import mock

from django.test import override_settings
from golem_messages import message
from golem_messages.cryptography import ECCx

from common.helpers import deserialize_message
from core.message_handlers import store_subtask
from core.models import Client
from core.models import PaymentInfo
from core.models import PendingResponse
from core.models import Subtask
from core.payments.report import create_report
from core.payments.report import get_subtasks_with_distinct_clients_pairs
from core.tests.utils import ConcentIntegrationTestCase
from core.transfer_operations import store_pending_message
from core.utils import get_current_utc_timestamp
from core.utils import hex_to_bytes_convert
from core.utils import parse_timestamp_to_utc_datetime


@override_settings(
    ADDITIONAL_VERIFICATION_COST=1,
)
class PaymentsReportTest(ConcentIntegrationTestCase):

    def setUp(self):
        super().setUp()
        self.providers = []
        self.requestors = []
        self.subtasks = []
        self.get_list_of_payments_mocks = []
        self.get_covered_additional_verification_costs_mocks = []
        self.closure_time = get_current_utc_timestamp()
        self.payment_ts = parse_timestamp_to_utc_datetime(self.closure_time)
        self.default_payment_amount = 10
        self.number_of_clients_per_type = 10
        self.number_of_subtasks = 30
        # The value below is determined by approach of mixing requestors and providers in _prepare_subtasks
        self.number_of_pairs = self.number_of_clients_per_type * 2

        self._prepare_client("providers")
        self._prepare_client("requestors")
        self._prepare_subtasks()
        self._prepare_related_payments_mocks()
        self._prepare_related_pending_responses()

    def test_create_report(self):
        """
        This is complex test to check `create_report` function output.

        This tests assumes there are:
        - 10 different providers.
        - 10 different requestors.
        - 30 Subtasks, and each provider has 3 Subtasks, 2 with same requestor, 1 with different one,
          so each Client is assigned to exactly 3 Subtasks.
        - Each Subtask has related ForcedSubtaskPaymentEvent, ForcedPaymentEvent and two CoverAdditionalVerificationEvent payments.
        - Each Subtask has related ForcePaymentCommitted and either SubtaskResultsSettled or SubtaskResultsRejected.
        """

        with mock.patch(
            'core.payments.report.service.get_list_of_payments',
            side_effect=self.get_list_of_payments_mocks,
        ) as get_list_of_payments_mock:
            with mock.patch(
                'core.payments.report.service.get_covered_additional_verification_costs',
                side_effect=self.get_covered_additional_verification_costs_mocks,
            ) as get_covered_additional_verification_costs_mock:
                report = create_report()

        # Test SCI calls.
        self.assertEqual(get_list_of_payments_mock.call_count, self.number_of_pairs * 3)
        self.assertEqual(get_covered_additional_verification_costs_mock.call_count, self.number_of_pairs * 2)

        # Test Pairs Reports.
        self.assertEqual(len(report.pair_reports), self.number_of_pairs)

        # There should be exactly half of the pairs with two subtasks and half with one,
        # but the order data returned from queryset is not deterministic, so we can't check odds and evens.
        pairs_with_two_subtasks_count = 0

        for pair_report in report.pair_reports:
            self.assertIn(pair_report.provider, self.providers)
            self.assertIn(pair_report.requestor, self.requestors)
            # 2 for each of 2 or 1 Subtasks.
            self.assertIn(len(pair_report.pending_responses.subtask_results_settled), [2, 4])

            if len(pair_report.pending_responses.subtask_results_settled) == 2:
                pairs_with_two_subtasks_count += 1

            self.assertEqual(len(pair_report.pending_responses.subtask_results_rejected), 0)
            # All 3 messages for pair.
            self.assertEqual(len(pair_report.pending_responses.force_payment_committed), 3)
            # 1 for each pair.
            self.assertEqual(len(pair_report.payments.regular_payments), 1)
            # 1 for each pair.
            self.assertEqual(len(pair_report.payments.settlement_payments), 1)
            # 1 for each of 1 or 2 Subtasks.
            self.assertIn(len(pair_report.payments.forced_subtask_payments), [1, 2])
            # 1 for each of 1 or 2 Subtasks.
            self.assertIn(len(pair_report.payments.requestor_additional_verification_payments), [1, 2])
            # 1 for each of 1 or 2 Subtasks.
            self.assertIn(len(pair_report.payments.provider_additional_verification_payments), [1, 2])

        self.assertEqual(pairs_with_two_subtasks_count, self.number_of_pairs / 2)

    def _prepare_client(self, concent_client):
        for _ in range(self.number_of_clients_per_type):
            client = Client(
                public_key=base64.b64encode(ECCx(None).raw_pubkey)
            )
            client.full_clean()
            client.save()
            getattr(self, concent_client).append(client)

    def _prepare_subtasks(self):
        for i in range(self.number_of_subtasks):
            requestor_index = ((i + 1) // 3) % self.number_of_clients_per_type
            provider_index = i // 3
            task_to_compute = self._get_deserialized_task_to_compute(
                provider_public_key=self.providers[provider_index].public_key,
                requestor_public_key=self.requestors[requestor_index].public_key,
            )
            report_computed_task = self._get_deserialized_report_computed_task(task_to_compute=task_to_compute)

            subtask = store_subtask(
                task_id=report_computed_task.task_id,
                subtask_id=report_computed_task.subtask_id,
                provider_public_key=base64.b64decode(task_to_compute.provider_public_key),
                requestor_public_key=base64.b64decode(task_to_compute.requestor_public_key),
                state=Subtask.SubtaskState.ACCEPTED,
                next_deadline=None,
                task_to_compute=task_to_compute,
                report_computed_task=report_computed_task,
            )

            self.subtasks.append(subtask)

        assert Client.objects.count() == self.number_of_clients_per_type * 2

    def _prepare_related_payments_mocks(self):
        for subtask in get_subtasks_with_distinct_clients_pairs():  # pylint: disable=not-an-iterable
            # The SCI methods are called in the same order in `core.payments.report.get_related_payments_for_pair`.
            self.get_list_of_payments_mocks.append(
                [
                    self._create_batch_payment_object(
                        self.default_payment_amount,
                        self.closure_time,
                    )
                ]
            )
            self.get_list_of_payments_mocks.append(
                [
                    self._create_settlement_payment_object(
                        self.default_payment_amount,
                        self.closure_time,
                    )
                ]
            )
            subtask_list = Subtask.objects.filter(requestor=subtask.requestor, provider=subtask.provider)
            self.get_list_of_payments_mocks.append(
                [self._create_forced_subtask_payment_object(self.default_payment_amount, subtask.subtask_id)
                 for subtask in subtask_list]
            )
            self.get_covered_additional_verification_costs_mocks.append(
                [self._create_cover_additional_verification_costs_object(self.default_payment_amount, subtask.subtask_id)
                 for subtask in subtask_list]
            )
            self.get_covered_additional_verification_costs_mocks.append(
                [self._create_cover_additional_verification_costs_object(self.default_payment_amount, subtask.subtask_id)
                 for subtask in subtask_list]
            )

    def _prepare_related_pending_responses(self):
        for subtask in self.subtasks:
            store_pending_message(
                response_type=PendingResponse.ResponseType.ForcePaymentCommitted,
                client_public_key=subtask.requestor.public_key_bytes,
                queue=PendingResponse.Queue.Receive,
                subtask=subtask,
            )

            task_to_compute = deserialize_message(subtask.task_to_compute.data)

            payment_info = PaymentInfo(
                payment_ts=self.payment_ts,
                task_owner_key=hex_to_bytes_convert(task_to_compute.requestor_ethereum_public_key),
                provider_eth_account=task_to_compute.provider_ethereum_address,
                amount_paid=self.default_payment_amount,
                recipient_type=message.concents.ForcePaymentCommitted.Actor.Requestor.name,  # pylint: disable=no-member
                amount_pending=0,
            )
            payment_info.full_clean()
            payment_info.save()

            pending_response_force_payment_committed = PendingResponse.objects.last()
            pending_response_force_payment_committed.payment_info = payment_info
            pending_response_force_payment_committed.full_clean()
            pending_response_force_payment_committed.save()

            store_pending_message(
                response_type=PendingResponse.ResponseType.SubtaskResultsSettled,
                client_public_key=subtask.requestor.public_key_bytes,
                queue=PendingResponse.Queue.Receive,
                subtask=subtask,
            )
            store_pending_message(
                response_type=PendingResponse.ResponseType.SubtaskResultsSettled,
                client_public_key=subtask.requestor.public_key_bytes,
                queue=PendingResponse.Queue.Receive,
                subtask=subtask,
            )
