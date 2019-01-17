import base64
import mock

from django.test import override_settings
from golem_messages import message
from golem_messages.cryptography import ECCx

from common.constants import ConcentUseCase
from common.helpers import deserialize_message
from core.constants import MOCK_TRANSACTION_HASH
from core.message_handlers import store_subtask
from core.models import Client
from core.models import DepositAccount
from core.models import DepositClaim
from core.models import PaymentInfo
from core.models import PendingResponse
from core.models import Subtask
from core.payments.report import create_report
from core.payments.report import get_subtasks_with_distinct_clients_pairs
from core.payments.report import get_errors_and_warnings
from core.payments.report import MatchingError
from core.payments.report import MatchingWarning
from core.payments.report import Payments
from core.payments.report import PendingResponses
from core.payments.report import prefetch_payment_info
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

        self._prepare_providers()
        self._prepare_requestors()
        self._prepare_subtasks()
        self._prepare_related_payments_mocks()
        self._prepare_related_pending_responses()

        assert self.default_payment_amount > 0
        assert self.number_of_clients_per_type > 1
        assert self.number_of_subtasks > 0

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

        # Test Report Summary.
        self.assertEqual(report.summary.number_of_pairs, self.number_of_pairs)
        self.assertEqual(report.summary.number_of_subtasks, self.number_of_subtasks)
        # 1 payment per pair.
        self.assertEqual(report.summary.number_of_regular_payments, self.number_of_pairs)
        # (2 regular payments for odds * 10 odds) + (2 regular payments for even * 10 evens)
        self.assertEqual(report.summary.number_of_forced_payments, 110)
        # 1 message per Subtask * default_payment_amount.
        self.assertEqual(report.summary.total_amount_to_be_paid, self.number_of_subtasks * 10)
        # (2 regular payments for odds * 10 odds) + (2 regular payments for even * 10 evens) * default_payment_amount
        self.assertEqual(report.summary.total_amount_actually_paid, 110 * self.default_payment_amount)
        # All payments paid correctly, so no pending payments.
        self.assertEqual(report.summary.total_amount_unrecoverable, 0)

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

            if len(pair_report.pending_responses.subtask_results_settled) == 4:
                pairs_with_two_subtasks_count += 1

            self.assertEqual(len(pair_report.pending_responses.subtask_results_rejected), 0)
            # 1 for each of 1 or 2 Subtasks.
            self.assertIn(len(pair_report.pending_responses.force_payment_committed), [1, 2])
            # 1 for each pair.
            self.assertEqual(len(pair_report.payments.regular_payments), 1)
            # 1 for each pair.
            self.assertEqual(len(pair_report.payments.settlement_payments), 1)
            # 1 for each of 1 or 2 Subtasks.
            self.assertIn(len(pair_report.payments.forced_subtask_payments), [1, 2])
            # 1 for each of 1 or 2 Subtasks.
            self.assertIn(len(pair_report.payments.additional_verification_payments_for_requestor), [1, 2])
            # 1 for each of 1 or 2 Subtasks.
            self.assertIn(len(pair_report.payments.additional_verification_payments_for_provider), [1, 2])
            self.assertEqual(len(pair_report.errors), 0)
            self.assertEqual(len(pair_report.warnings), 0)

            # Test Pair Report Summary.
            self.assertEqual(pair_report.summary.number_of_pairs, 1)
            self.assertIn(pair_report.summary.number_of_subtasks, [1, 2])
            self.assertEqual(pair_report.summary.number_of_regular_payments, 1)
            self.assertIn(pair_report.summary.total_amount_to_be_paid, [10, 20])
            self.assertIn(pair_report.summary.total_amount_actually_paid, [40, 70])
            self.assertEqual(pair_report.summary.total_amount_unrecoverable, 0)

        self.assertEqual(pairs_with_two_subtasks_count, self.number_of_pairs / 2)

    def _prepare_providers(self):
        for _ in range(self.number_of_clients_per_type):
            client = Client(
                public_key=base64.b64encode(ECCx(None).raw_pubkey)
            )
            client.full_clean()
            client.save()
            self.providers.append(client)

    def _prepare_requestors(self):
        for _ in range(self.number_of_clients_per_type):
            client = Client(
                public_key=base64.b64encode(ECCx(None).raw_pubkey)
            )
            client.full_clean()
            client.save()
            self.requestors.append(client)

    def _prepare_subtasks(self):
        for i in range(self.number_of_subtasks):
            task_to_compute = self._get_deserialized_task_to_compute(
                provider_public_key=self.providers[i // 3].public_key,
                requestor_public_key=(
                    self.requestors[(i + 1) // 3].public_key
                    if i != (self.number_of_subtasks - 1) else self.requestors[0].public_key
                ),
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
            self.get_list_of_payments_mocks.append(
                [self._create_forced_subtask_payment_object(self.default_payment_amount, subtask.subtask_id)
                 for subtask in Subtask.objects.filter(requestor=subtask.requestor, provider=subtask.provider)]
            )
            self.get_covered_additional_verification_costs_mocks.append(
                [self._create_cover_additional_verification_costs_object(self.default_payment_amount, subtask.subtask_id)
                 for subtask in Subtask.objects.filter(requestor=subtask.requestor, provider=subtask.provider)]
            )
            self.get_covered_additional_verification_costs_mocks.append(
                [self._create_cover_additional_verification_costs_object(self.default_payment_amount, subtask.subtask_id)
                 for subtask in Subtask.objects.filter(requestor=subtask.requestor, provider=subtask.provider)]
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


@override_settings(
    ADDITIONAL_VERIFICATION_COST=10,
)
class GetErrorsAndWarningsPaymentsReportTest(ConcentIntegrationTestCase):

    def setUp(self):
        super().setUp()

        task_to_compute = self._get_deserialized_task_to_compute()
        report_computed_task = self._get_deserialized_report_computed_task(task_to_compute=task_to_compute)

        self.subtask = store_subtask(
            task_id=report_computed_task.task_id,
            subtask_id=report_computed_task.subtask_id,
            provider_public_key=hex_to_bytes_convert(task_to_compute.provider_public_key),
            requestor_public_key=hex_to_bytes_convert(task_to_compute.requestor_public_key),
            state=Subtask.SubtaskState.ACCEPTED,
            next_deadline=None,
            task_to_compute=task_to_compute,
            report_computed_task=report_computed_task,
        )

        self.default_payment_amount = 10
        self.closure_time = get_current_utc_timestamp()
        self.payment_ts = parse_timestamp_to_utc_datetime(self.closure_time)

        store_pending_message(
            response_type=PendingResponse.ResponseType.SubtaskResultsSettled,
            client_public_key=self.subtask.requestor.public_key_bytes,
            queue=PendingResponse.Queue.Receive,
            subtask=self.subtask,
        )
        self.pending_response_subtask_results_settled = PendingResponse.objects.last()

        store_pending_message(
            response_type=PendingResponse.ResponseType.SubtaskResultsRejected,
            client_public_key=self.subtask.requestor.public_key_bytes,
            queue=PendingResponse.Queue.Receive,
            subtask=self.subtask,
        )
        self.pending_response_subtask_results_rejected = PendingResponse.objects.last()

        store_pending_message(
            response_type=PendingResponse.ResponseType.ForcePaymentCommitted,
            client_public_key=self.subtask.requestor.public_key_bytes,
            queue=PendingResponse.Queue.Receive,
            subtask=self.subtask,
        )
        self.pending_response_force_payment_committed = PendingResponse.objects.last()

        task_to_compute = deserialize_message(self.subtask.task_to_compute.data)

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

        self.pending_response_force_payment_committed.payment_info = payment_info
        self.pending_response_force_payment_committed.full_clean()
        self.pending_response_force_payment_committed.save()

    def test_get_errors_and_warnings_should_return_error_if_pair_data_has_no_forced_payment_related_to_message(self):
        payments = Payments(
            regular_payments=[],
            settlement_payments=[],
            forced_subtask_payments=[],
            additional_verification_payments_for_requestor=[],
            additional_verification_payments_for_provider=[],
        )
        pending_responses = PendingResponses(
            subtask_results_settled=[self.pending_response_subtask_results_settled],
            subtask_results_rejected=[],
            force_payment_committed=[],
        )

        (errors, warnings) = get_errors_and_warnings(payments, pending_responses)

        self.assertEqual(len(errors), 1)
        self.assertEqual(len(warnings), 0)
        self.assertEqual(errors[0].matching_error, MatchingError.MESSAGE_NOT_MATCHED_WITH_ANY_PAYMENT)

    def test_get_errors_and_warnings_should_return_error_and_warning_if_pair_data_has_no_forced_payment_related_to_message_and_deposit_claim_exists(self):
        payments = Payments(
            regular_payments=[],
            settlement_payments=[],
            forced_subtask_payments=[],
            additional_verification_payments_for_requestor=[],
            additional_verification_payments_for_provider=[],
        )
        pending_responses = PendingResponses(
            subtask_results_settled=[self.pending_response_subtask_results_settled],
            subtask_results_rejected=[],
            force_payment_committed=[],
        )

        self._create_client_and_related_deposit_account_and_deposit_claim(
            self.subtask,
            ConcentUseCase.FORCED_ACCEPTANCE,
        )

        (errors, warnings) = get_errors_and_warnings(payments, pending_responses)

        self.assertEqual(len(errors), 1)
        self.assertEqual(len(warnings), 1)
        self.assertEqual(errors[0].matching_error, MatchingError.MESSAGE_NOT_MATCHED_WITH_ANY_PAYMENT)
        self.assertEqual(warnings[0].matching_warning, MatchingWarning.NO_MATCHING_MESSAGE_FOR_PAYMENT_BUT_DEPOSIT_CLAIM_EXISTS)

    def test_get_errors_and_warnings_should_return_error_if_pair_data_has_two_forced_payments_related_to_message(self):
        payments = Payments(
            regular_payments=[],
            settlement_payments=[],
            forced_subtask_payments=[
                self._create_forced_subtask_payment_object(self.default_payment_amount, self.subtask.subtask_id),
                self._create_forced_subtask_payment_object(self.default_payment_amount, self.subtask.subtask_id),
            ],
            additional_verification_payments_for_requestor=[],
            additional_verification_payments_for_provider=[],
        )
        pending_responses = PendingResponses(
            subtask_results_settled=[self.pending_response_subtask_results_settled],
            subtask_results_rejected=[],
            force_payment_committed=[],
        )

        (errors, warnings) = get_errors_and_warnings(payments, pending_responses)

        self.assertEqual(len(errors), 1)
        self.assertEqual(len(warnings), 0)
        self.assertEqual(errors[0].matching_error, MatchingError.MORE_THAN_ONE_MATCHING_PAYMENT_FOR_MESSAGE)

    def test_get_errors_and_warnings_should_return_error_if_pair_data_has_no_message_related_to_verification_payment(self):
        payments = Payments(
            regular_payments=[],
            settlement_payments=[],
            forced_subtask_payments=[],
            additional_verification_payments_for_requestor=[
                self._create_cover_additional_verification_costs_object(
                    self.default_payment_amount, self.subtask.subtask_id
                ),
            ],
            additional_verification_payments_for_provider=[],
        )
        pending_responses = PendingResponses(
            subtask_results_settled=[],
            subtask_results_rejected=[],
            force_payment_committed=[],
        )

        (errors, warnings) = get_errors_and_warnings(payments, pending_responses)

        self.assertEqual(len(errors), 1)
        self.assertEqual(len(warnings), 0)
        self.assertEqual(errors[0].matching_error, MatchingError.PAYMENT_NOT_MATCHED_WITH_ANY_MESSAGE)

    def test_get_errors_and_warnings_should_return_error_and_warning_if_pair_data_has_no_message_related_to_verification_payment_and_deposit_claim_exists(self):
        payments = Payments(
            regular_payments=[],
            settlement_payments=[],
            forced_subtask_payments=[],
            additional_verification_payments_for_requestor=[
                self._create_cover_additional_verification_costs_object(
                    self.default_payment_amount, self.subtask.subtask_id
                ),
            ],
            additional_verification_payments_for_provider=[],
        )
        pending_responses = PendingResponses(
            subtask_results_settled=[],
            subtask_results_rejected=[],
            force_payment_committed=[],
        )

        self._create_client_and_related_deposit_account_and_deposit_claim(
            self.subtask,
            ConcentUseCase.ADDITIONAL_VERIFICATION,
        )

        (errors, warnings) = get_errors_and_warnings(payments, pending_responses)

        self.assertEqual(len(errors), 1)
        self.assertEqual(len(warnings), 1)
        self.assertEqual(errors[0].matching_error, MatchingError.PAYMENT_NOT_MATCHED_WITH_ANY_MESSAGE)
        self.assertEqual(warnings[0].matching_warning, MatchingWarning.NO_MATCHING_MESSAGE_FOR_PAYMENT_BUT_DEPOSIT_CLAIM_EXISTS)

    def test_get_errors_and_warnings_should_return_error_if_pair_data_has_three_messages_of_one_type_related_to_verification_payment(self):
        payments = Payments(
            regular_payments=[],
            settlement_payments=[],
            forced_subtask_payments=[
                self._create_forced_subtask_payment_object(self.default_payment_amount, self.subtask.subtask_id),
            ],
            additional_verification_payments_for_requestor=[
                self._create_cover_additional_verification_costs_object(
                    self.default_payment_amount, self.subtask.subtask_id
                ),
            ],
            additional_verification_payments_for_provider=[],
        )
        pending_responses = PendingResponses(
            subtask_results_settled=[
                self.pending_response_subtask_results_settled,
                self.pending_response_subtask_results_settled,
                self.pending_response_subtask_results_settled,
            ],
            subtask_results_rejected=[],
            force_payment_committed=[],
        )

        (errors, warnings) = get_errors_and_warnings(payments, pending_responses)

        self.assertEqual(len(errors), 1)
        self.assertEqual(len(warnings), 0)
        self.assertEqual(errors[0].matching_error, MatchingError.MORE_THAN_EXPECTED_MATCHING_MESSAGES_FOR_PAYMENT)

    def test_get_errors_and_warnings_should_return_error_if_pair_data_has_messages_of_both_types_related_to_verification_payment(self):
        payments = Payments(
            regular_payments=[],
            settlement_payments=[],
            forced_subtask_payments=[
                self._create_forced_subtask_payment_object(self.default_payment_amount, self.subtask.subtask_id),
            ],
            additional_verification_payments_for_requestor=[
                self._create_cover_additional_verification_costs_object(
                    self.default_payment_amount, self.subtask.subtask_id
                ),
            ],
            additional_verification_payments_for_provider=[],
        )
        pending_responses = PendingResponses(
            subtask_results_settled=[self.pending_response_subtask_results_settled],
            subtask_results_rejected=[self.pending_response_subtask_results_rejected],
            force_payment_committed=[],
        )

        (errors, warnings) = get_errors_and_warnings(payments, pending_responses)

        self.assertEqual(len(errors), 1)
        self.assertEqual(len(warnings), 0)
        self.assertEqual(errors[0].matching_error, MatchingError.MORE_THAN_ONE_SUBTASK_RESULT_FOR_SUBTASK)

    def test_get_errors_and_warnings_should_return_error_if_subtask_related_to_verification_payment_was_removed(self):
        payments = Payments(
            regular_payments=[],
            settlement_payments=[],
            forced_subtask_payments=[],
            additional_verification_payments_for_requestor=[
                self._create_cover_additional_verification_costs_object(
                    self.default_payment_amount, 'not_existing'
                ),
            ],
            additional_verification_payments_for_provider=[],
        )
        pending_responses = PendingResponses(
            subtask_results_settled=[self.pending_response_subtask_results_settled],
            subtask_results_rejected=[],
            force_payment_committed=[],
        )

        (_, warnings) = get_errors_and_warnings(payments, pending_responses)

        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0].matching_warning, MatchingWarning.VERIFICATION_PAYMENT_DO_NOT_HAVE_RELATED_SUBTASK)

    @override_settings(
        ADDITIONAL_VERIFICATION_COST=9,
    )
    def test_get_errors_and_warnings_should_return_error_if_pair_data_has_message_subtask_results_rejected_and_payment_amount_differs_from_additional_verification_cost(self):
        payments = Payments(
            regular_payments=[],
            settlement_payments=[],
            forced_subtask_payments=[],
            additional_verification_payments_for_requestor=[
                self._create_cover_additional_verification_costs_object(
                    self.default_payment_amount, self.subtask.subtask_id
                ),
            ],
            additional_verification_payments_for_provider=[],
        )
        pending_responses = PendingResponses(
            subtask_results_settled=[],
            subtask_results_rejected=[self.pending_response_subtask_results_rejected],
            force_payment_committed=[],
        )

        (errors, warnings) = get_errors_and_warnings(payments, pending_responses)

        self.assertEqual(len(errors), 0)
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0].matching_warning, MatchingWarning.PAYMENT_VALUE_DIFFERS_FROM_VERIFICATION_COST)

    def test_get_errors_and_warnings_should_return_error_if_pair_data_has_no_settlement_payment_related_to_message(self):
        payments = Payments(
            regular_payments=[],
            settlement_payments=[],
            forced_subtask_payments=[],
            additional_verification_payments_for_requestor=[],
            additional_verification_payments_for_provider=[],
        )
        pending_responses = PendingResponses(
            subtask_results_settled=[],
            subtask_results_rejected=[],
            force_payment_committed=[self.pending_response_force_payment_committed],
        )

        (errors, warnings) = get_errors_and_warnings(payments, pending_responses)

        self.assertEqual(len(errors), 1)
        self.assertEqual(len(warnings), 0)
        self.assertEqual(errors[0].matching_error, MatchingError.MESSAGE_NOT_MATCHED_WITH_ANY_PAYMENT)

    def test_get_errors_and_warnings_should_return_error_and_warning_if_pair_data_has_no_settlement_payment_related_to_message_and_deposit_claim_exists(self):
        payments = Payments(
            regular_payments=[],
            settlement_payments=[],
            forced_subtask_payments=[],
            additional_verification_payments_for_requestor=[],
            additional_verification_payments_for_provider=[],
        )
        pending_responses = PendingResponses(
            subtask_results_settled=[],
            subtask_results_rejected=[],
            force_payment_committed=[self.pending_response_force_payment_committed],
        )

        self._create_client_and_related_deposit_account_and_deposit_claim(
            self.subtask,
            ConcentUseCase.FORCED_PAYMENT,
            closure_time=self.closure_time,
        )

        (errors, warnings) = get_errors_and_warnings(payments, pending_responses)

        self.assertEqual(len(errors), 1)
        self.assertEqual(len(warnings), 1)
        self.assertEqual(errors[0].matching_error, MatchingError.MESSAGE_NOT_MATCHED_WITH_ANY_PAYMENT)
        self.assertEqual(warnings[0].matching_warning, MatchingWarning.NO_MATCHING_MESSAGE_FOR_PAYMENT_BUT_DEPOSIT_CLAIM_EXISTS)

    def test_get_errors_and_warnings_should_return_error_if_pair_data_has_two_settlement_payments_related_to_message(self):
        payments = Payments(
            regular_payments=[],
            settlement_payments=[
                self._create_settlement_payment_object(
                    self.default_payment_amount, self.closure_time
                ),
                self._create_settlement_payment_object(
                    self.default_payment_amount, self.closure_time
                )
            ],
            forced_subtask_payments=[],
            additional_verification_payments_for_requestor=[],
            additional_verification_payments_for_provider=[],
        )
        pending_responses = PendingResponses(
            subtask_results_settled=[],
            subtask_results_rejected=[],
            force_payment_committed=[self.pending_response_force_payment_committed],
        )

        (errors, warnings) = get_errors_and_warnings(payments, pending_responses)

        self.assertEqual(len(errors), 1)
        self.assertEqual(len(warnings), 0)
        self.assertEqual(errors[0].matching_error, MatchingError.MORE_THAN_ONE_MATCHING_PAYMENT_FOR_MESSAGE)

    def test_get_errors_and_warnings_should_return_error_if_pair_data_has_settlement_payment_with_different_payment_value_than_message(self):
        payments = Payments(
            regular_payments=[],
            settlement_payments=[
                self._create_settlement_payment_object(
                    self.default_payment_amount - 1, self.closure_time
                )
            ],
            forced_subtask_payments=[],
            additional_verification_payments_for_requestor=[],
            additional_verification_payments_for_provider=[],
        )
        pending_responses = PendingResponses(
            subtask_results_settled=[],
            subtask_results_rejected=[],
            force_payment_committed=[self.pending_response_force_payment_committed],
        )

        (errors, warnings) = get_errors_and_warnings(payments, pending_responses)

        self.assertEqual(len(errors), 1)
        self.assertEqual(len(warnings), 0)
        self.assertEqual(errors[0].matching_error, MatchingError.MESSAGE_VALUE_DIFFERS_FROM_PAYMENT_VALUE)

    def test_get_errors_and_warnings_should_return_error_if_pair_data_has_settlement_payment_with_different_closure_time_than_message(self):
        payments = Payments(
            regular_payments=[],
            settlement_payments=[
                self._create_settlement_payment_object(
                    self.default_payment_amount, self.closure_time - 1
                )
            ],
            forced_subtask_payments=[],
            additional_verification_payments_for_requestor=[],
            additional_verification_payments_for_provider=[],
        )
        pending_responses = PendingResponses(
            subtask_results_settled=[],
            subtask_results_rejected=[],
            force_payment_committed=[self.pending_response_force_payment_committed],
        )

        (errors, warnings) = get_errors_and_warnings(payments, pending_responses)

        self.assertEqual(len(errors), 1)
        self.assertEqual(len(warnings), 0)
        self.assertEqual(errors[0].matching_error, MatchingError.FORCE_PAYMENT_COMMITED_PAYMENT_TS_DIFFERS_FROM_SETTLEMENT_PAYMENT_CLOSURE_TIMESTAMP)

    def test_get_errors_and_warnings_should_return_warning_if_pair_data_has_settlement_payment_with_related_message_with_amount_pending(self):
        payments = Payments(
            regular_payments=[],
            settlement_payments=[
                self._create_settlement_payment_object(
                    self.default_payment_amount, self.closure_time
                )
            ],
            forced_subtask_payments=[],
            additional_verification_payments_for_requestor=[],
            additional_verification_payments_for_provider=[],
        )

        payment_info = self.pending_response_force_payment_committed.payment_info
        payment_info.amount_pending = 1
        payment_info.full_clean()
        payment_info.save()

        pending_responses = PendingResponses(
            subtask_results_settled=[],
            subtask_results_rejected=[],
            force_payment_committed=[self.pending_response_force_payment_committed],
        )

        (errors, warnings) = get_errors_and_warnings(payments, pending_responses)

        self.assertEqual(len(errors), 0)
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0].matching_warning, MatchingWarning.NOT_ENOUGH_DEPOSIT_TO_COVER_WHOLE_COST)

    def test_get_errors_and_warnings_should_return_warning_if_pair_data_has_settlement_payment_with_related_deposit_claim(self):
        payments = Payments(
            regular_payments=[],
            settlement_payments=[
                self._create_settlement_payment_object(
                    self.default_payment_amount, self.closure_time - 1
                )
            ],
            forced_subtask_payments=[],
            additional_verification_payments_for_requestor=[],
            additional_verification_payments_for_provider=[],
        )
        pending_responses = PendingResponses(
            subtask_results_settled=[],
            subtask_results_rejected=[],
            force_payment_committed=[],
        )

        self._create_client_and_related_deposit_account_and_deposit_claim(
            self.subtask,
            ConcentUseCase.FORCED_PAYMENT,
            closure_time=self.closure_time,
        )

        (errors, warnings) = get_errors_and_warnings(payments, pending_responses)

        self.assertEqual(len(errors), 1)
        self.assertEqual(len(warnings), 0)
        self.assertEqual(errors[0].matching_error, MatchingError.DEPOSIT_CLAIM_RELATED_TO_SETTLEMENT_PAYMENT_EXISTS)

    def test_get_errors_and_warnings_should_return_warning_if_pair_data_has_forced_payment_with_related_deposit_claim(self):
        payments = Payments(
            regular_payments=[],
            settlement_payments=[],
            forced_subtask_payments=[
                self._create_forced_subtask_payment_object(self.default_payment_amount, self.subtask.subtask_id),
            ],
            additional_verification_payments_for_requestor=[],
            additional_verification_payments_for_provider=[],
        )
        pending_responses = PendingResponses(
            subtask_results_settled=[],
            subtask_results_rejected=[],
            force_payment_committed=[],
        )

        self._create_client_and_related_deposit_account_and_deposit_claim(
            self.subtask,
            ConcentUseCase.FORCED_PAYMENT,
            closure_time=self.closure_time,
        )

        (errors, warnings) = get_errors_and_warnings(payments, pending_responses)

        self.assertEqual(len(errors), 1)
        self.assertEqual(len(warnings), 0)
        self.assertEqual(errors[0].matching_error, MatchingError.DEPOSIT_CLAIM_RELATED_TO_FORCED_PAYMENT_EXISTS)

    def _create_client_and_related_deposit_account_and_deposit_claim(
        self,
        subtask,
        concent_use_case,
        closure_time=None,
    ):
        task_to_compute = deserialize_message(subtask.task_to_compute.data)

        requestor_client = Client.objects.get(
            public_key=base64.b64encode(hex_to_bytes_convert(task_to_compute.requestor_public_key))
        )

        requestor_deposit_account = DepositAccount.objects.get_or_create_full_clean(
            client=requestor_client,
            ethereum_address=task_to_compute.requestor_ethereum_address,
        )
        requestor_deposit_account.full_clean()
        requestor_deposit_account.save()

        deposit_claim = DepositClaim(
            subtask_id=subtask.subtask_id,
            payee_ethereum_address=task_to_compute.provider_ethereum_address,
            payer_deposit_account=requestor_deposit_account,
            amount=self.default_payment_amount,
            concent_use_case=concent_use_case,
            tx_hash=MOCK_TRANSACTION_HASH,
            closure_time=parse_timestamp_to_utc_datetime(closure_time) if closure_time is not None else closure_time,
        )
        deposit_claim.full_clean()
        deposit_claim.save()
