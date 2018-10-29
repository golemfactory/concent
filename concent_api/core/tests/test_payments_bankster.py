from freezegun import freeze_time
import mock

from django.test import override_settings
from golem_messages.utils import encode_hex

from common.constants import ConcentUseCase
from core.constants import MOCK_TRANSACTION
from core.models import Client
from core.models import DepositAccount
from core.models import DepositClaim
from core.payments.bankster import claim_deposit
from core.payments.bankster import discard_claim
from core.payments.bankster import finalize_payment
from core.payments.bankster import settle_overdue_acceptances
from core.tests.test_unit_model import store_report_computed_task_as_subtask
from core.tests.utils import ConcentIntegrationTestCase


@override_settings(
    ADDITIONAL_VERIFICATION_COST=1
)
class ClaimDepositBanksterTest(ConcentIntegrationTestCase):

    def setUp(self):
        super().setUp()
        self.task_to_compute = self._get_deserialized_task_to_compute()

    def test_that_claim_deposit_return_both_true_if_both_requestor_and_provider_have_enough_funds(self):
        with mock.patch('core.payments.service.get_deposit_value', return_value=1) as get_deposit_value:
            (requestor_has_enough_deposit, provider_has_enough_deposit) = claim_deposit(
                concent_use_case=ConcentUseCase.ADDITIONAL_VERIFICATION,
                requestor_ethereum_address=self.task_to_compute.requestor_ethereum_address,
                provider_ethereum_address=self.task_to_compute.provider_ethereum_address,
                subtask_cost=1,
            )

        self.assertTrue(requestor_has_enough_deposit)
        self.assertTrue(provider_has_enough_deposit)
        self.assertEqual(get_deposit_value.call_count, 2)

    def test_that_claim_deposit_return_both_true_if_requestor_has_enough_funds_and_it_is_not_additional_verification(self):
        with mock.patch('core.payments.service.get_deposit_value', return_value=1) as get_deposit_value:
            (requestor_has_enough_deposit, provider_has_enough_deposit) = claim_deposit(
                concent_use_case=ConcentUseCase.FORCED_ACCEPTANCE,
                requestor_ethereum_address=self.task_to_compute.requestor_ethereum_address,
                provider_ethereum_address=self.task_to_compute.provider_ethereum_address,
                subtask_cost=1,
            )

        self.assertTrue(requestor_has_enough_deposit)
        self.assertTrue(provider_has_enough_deposit)
        get_deposit_value.assert_called_once_with(
            client_eth_address=self.task_to_compute.requestor_ethereum_address
        )

    @override_settings(
        ADDITIONAL_VERIFICATION_COST=0
    )
    def test_that_claim_deposit_return_false_and_true_if_requestor_has_zero_funds(self):
        with mock.patch('core.payments.service.get_deposit_value', return_value=0) as get_deposit_value:
            (requestor_has_enough_deposit, provider_has_enough_deposit) = claim_deposit(
                concent_use_case=ConcentUseCase.ADDITIONAL_VERIFICATION,
                requestor_ethereum_address=self.task_to_compute.requestor_ethereum_address,
                provider_ethereum_address=self.task_to_compute.provider_ethereum_address,
                subtask_cost=1,
            )

        self.assertFalse(requestor_has_enough_deposit)
        self.assertTrue(provider_has_enough_deposit)
        self.assertEqual(get_deposit_value.call_count, 2)

    @override_settings(
        ADDITIONAL_VERIFICATION_COST=2
    )
    def test_that_claim_deposit_return_true_and_false_if_provider_has_less_funds_than_needed(self):
        with mock.patch('core.payments.service.get_deposit_value', return_value=1) as get_deposit_value:
            (requestor_has_enough_deposit, provider_has_enough_deposit) = claim_deposit(
                concent_use_case=ConcentUseCase.ADDITIONAL_VERIFICATION,
                requestor_ethereum_address=self.task_to_compute.requestor_ethereum_address,
                provider_ethereum_address=self.task_to_compute.provider_ethereum_address,
                subtask_cost=1,
            )

        self.assertTrue(requestor_has_enough_deposit)
        self.assertFalse(provider_has_enough_deposit)
        self.assertEqual(get_deposit_value.call_count, 2)


class FinalizePaymentBanksterTest(ConcentIntegrationTestCase):

    def setUp(self):
        super().setUp()
        self.task_to_compute = self._get_deserialized_task_to_compute()

        self.client = Client(public_key_bytes=self.PROVIDER_PUBLIC_KEY)
        self.client.clean()
        self.client.save()

        self.deposit_account = DepositAccount()
        self.deposit_account.client = self.client
        self.deposit_account.ethereum_address = self.task_to_compute.requestor_ethereum_address
        self.deposit_account.clean()
        self.deposit_account.save()

        self.deposit_claim = DepositClaim()
        self.deposit_claim.subtask = store_report_computed_task_as_subtask()
        self.deposit_claim.payer_deposit_account = self.deposit_account
        self.deposit_claim.payee_ethereum_address = self.task_to_compute.provider_ethereum_address
        self.deposit_claim.concent_use_case = ConcentUseCase.FORCED_ACCEPTANCE
        self.deposit_claim.amount = 2
        self.deposit_claim.clean()
        self.deposit_claim.save()

    def test_that_when_available_funds_are_zero_finalize_payment_should_delete_deposit_claim_and_return_none(self):
        with mock.patch('core.payments.service.get_deposit_value', return_value=0) as get_deposit_value:
            returned_value = finalize_payment(self.deposit_claim)

        self.assertIsNone(returned_value)
        self.assertFalse(DepositClaim.objects.filter(pk=self.deposit_claim.pk).exists())

        get_deposit_value.assert_called_with(
            client_eth_address=self.deposit_claim.payer_deposit_account.ethereum_address,
        )

    def test_that_when_deposit_claim_is_for_forced_acceptance_use_case_finalize_payment_should_call_force_subtask_payment(self):
        with mock.patch('core.payments.service.get_deposit_value', return_value=2) as get_deposit_value:
            with mock.patch('core.payments.service.force_subtask_payment', return_value=MOCK_TRANSACTION) as force_subtask_payment:
                returned_value = finalize_payment(self.deposit_claim)
        self.assertEqual(returned_value, encode_hex(MOCK_TRANSACTION.hash))

        get_deposit_value.assert_called_with(
            client_eth_address=self.deposit_claim.payer_deposit_account.ethereum_address,
        )
        force_subtask_payment.assert_called_once_with(
            requestor_eth_address=self.deposit_claim.payer_deposit_account.ethereum_address,
            provider_eth_address=self.deposit_claim.payee_ethereum_address,
            value=self.deposit_claim.amount,
            subtask_id=self.deposit_claim.subtask.subtask_id,
        )

    def test_that_when_deposit_claim_is_for_additional_verification_use_case_finalize_payment_should_call_cover_additional_verification_cost(self):
        self.deposit_claim.concent_use_case = ConcentUseCase.ADDITIONAL_VERIFICATION
        self.deposit_claim.clean()
        self.deposit_claim.save()

        with mock.patch('core.payments.service.get_deposit_value', return_value=2) as get_deposit_value:
            with mock.patch('core.payments.service.cover_additional_verification_cost', return_value=MOCK_TRANSACTION) as cover_additional_verification_cost:
                returned_value = finalize_payment(self.deposit_claim)

        self.assertEqual(returned_value, encode_hex(MOCK_TRANSACTION.hash))

        get_deposit_value.assert_called_with(
            client_eth_address=self.deposit_claim.payer_deposit_account.ethereum_address,
        )
        cover_additional_verification_cost.assert_called_once_with(
            provider_eth_address=self.deposit_claim.payer_deposit_account.ethereum_address,
            value=self.deposit_claim.amount,
            subtask_id=self.deposit_claim.subtask.subtask_id,
        )

    def test_that_when_there_are_other_deposit_claims_finalize_payment_substract_them_from_currently_processed_claim(self):
        self.deposit_claim = DepositClaim()
        self.deposit_claim.subtask = store_report_computed_task_as_subtask()
        self.deposit_claim.payer_deposit_account = self.deposit_account
        self.deposit_claim.payee_ethereum_address = self.task_to_compute.provider_ethereum_address
        self.deposit_claim.concent_use_case = ConcentUseCase.FORCED_ACCEPTANCE
        self.deposit_claim.amount = 2
        self.deposit_claim.clean()
        # Save twice because we want two same claims.
        self.deposit_claim.save()
        self.deposit_claim.pk = None
        self.deposit_claim.save()

        with mock.patch('core.payments.service.get_deposit_value', return_value=5) as get_deposit_value:
            with mock.patch('core.payments.service.force_subtask_payment', return_value=MOCK_TRANSACTION) as force_subtask_payment:
                returned_value = finalize_payment(self.deposit_claim)

        self.assertEqual(returned_value, encode_hex(MOCK_TRANSACTION.hash))

        get_deposit_value.assert_called_with(
            client_eth_address=self.deposit_claim.payer_deposit_account.ethereum_address,
        )
        force_subtask_payment.assert_called_once_with(
            requestor_eth_address=self.deposit_claim.payer_deposit_account.ethereum_address,
            provider_eth_address=self.deposit_claim.payee_ethereum_address,
            # 5 - (2 + 2) | deposit_value - sum_of_other_claims
            value=1,
            subtask_id=self.deposit_claim.subtask.subtask_id,
        )


class SettleOverdueAcceptancesBanksterTest(ConcentIntegrationTestCase):

    def test_that_settle_overdue_acceptances_should_return_empty_claim_deposit_info_if_subtask_costs_where_already_paid(self):
        task_to_compute = self._get_deserialized_task_to_compute(
            price=13000,
        )

        subtask_results_accepted_list = [
            self._get_deserialized_subtask_results_accepted(
                task_to_compute=task_to_compute
            )
        ]

        with mock.patch(
            'core.payments.bankster.service.get_list_of_payments',
            side_effect=[
                self._get_list_of_batch_transactions(),
                self._get_list_of_force_transactions(),
            ]
        ) as get_list_of_payments_mock:
            requestors_claim_payment_info = settle_overdue_acceptances(
                requestor_ethereum_address=task_to_compute.requestor_ethereum_address,
                provider_ethereum_address=task_to_compute.provider_ethereum_address,
                acceptances=subtask_results_accepted_list,
            )

        get_list_of_payments_mock.assert_called()

        self.assertIsNone(requestors_claim_payment_info.tx_hash)
        self.assertIsNone(requestors_claim_payment_info.payment_ts)
        self.assertEqual(requestors_claim_payment_info.amount_paid, 0)
        self.assertEqual(requestors_claim_payment_info.amount_pending, 0)

    @override_settings(
        PAYMENT_DUE_TIME=10
    )
    def test_that_settle_overdue_acceptances_should_return_claim_deposit_info_with_amount_pending_if_requestor_deposit_value_is_zero(self):
        task_to_compute = self._get_deserialized_task_to_compute(
            price=10000,
        )

        with freeze_time("2018-02-05 10:00:15"):
            subtask_results_accepted_list = [
                self._get_deserialized_subtask_results_accepted(
                    task_to_compute=task_to_compute
                )
            ]

        with freeze_time("2018-02-05 10:00:25"):
            with mock.patch(
                'core.payments.bankster.service.get_deposit_value',
                return_value=0
            ) as get_deposit_value_mock:
                requestors_claim_payment_info = settle_overdue_acceptances(
                    requestor_ethereum_address=task_to_compute.requestor_ethereum_address,
                    provider_ethereum_address=task_to_compute.provider_ethereum_address,
                    acceptances=subtask_results_accepted_list,
                )

        get_deposit_value_mock.assert_called()

        self.assertIsNone(requestors_claim_payment_info.tx_hash)
        self.assertIsNone(requestors_claim_payment_info.payment_ts)
        self.assertEqual(requestors_claim_payment_info.amount_paid, 0)
        self.assertEqual(requestors_claim_payment_info.amount_pending, task_to_compute.price)

    @override_settings(
        PAYMENT_DUE_TIME=10
    )
    def test_that_settle_overdue_acceptances_should_return_claim_deposit_info_with_amount_paid(self):
        task_to_compute = self._get_deserialized_task_to_compute(
            price=15000,
        )

        with freeze_time("2018-02-05 10:00:15"):
            subtask_results_accepted_list = [
                self._get_deserialized_subtask_results_accepted(
                    task_to_compute=task_to_compute
                )
            ]

        with freeze_time("2018-02-05 10:00:25"):
            with mock.patch('core.payments.bankster.service.get_deposit_value', return_value=1000) as get_deposit_value_mock:
                with mock.patch(
                    'core.payments.bankster.service.get_list_of_payments',
                    side_effect=[
                        self._get_list_of_batch_transactions(),
                        self._get_list_of_force_transactions(),
                    ]
                ) as get_list_of_payments_mock:
                    requestors_claim_payment_info = settle_overdue_acceptances(
                        requestor_ethereum_address=task_to_compute.requestor_ethereum_address,
                        provider_ethereum_address=task_to_compute.provider_ethereum_address,
                        acceptances=subtask_results_accepted_list,
                    )

        get_deposit_value_mock.assert_called_once()
        get_list_of_payments_mock.assert_called()

        self.assertIsNotNone(requestors_claim_payment_info.tx_hash)
        self.assertIsNotNone(requestors_claim_payment_info.payment_ts)

        # The results of payments are calculated in the following way:
        # already_paid_value = 15000 - (
        #   (1000 + 2000 + 3000 + 4000)(batch_transactions) +
        #   (1000 + 2000)(force_transactions)
        # )
        # already_paid_value == 13000, so 2000 left
        # get_deposit_value returns 1000, so 1000 paid and 1000 left (pending)

        self.assertEqual(requestors_claim_payment_info.amount_paid, 1000)
        self.assertEqual(requestors_claim_payment_info.amount_pending, 1000)


class DiscardClaimBanksterTest(ConcentIntegrationTestCase):

    def setUp(self):
        super().setUp()
        self.task_to_compute = self._get_deserialized_task_to_compute()

        self.client = Client(public_key_bytes=self.PROVIDER_PUBLIC_KEY)
        self.client.clean()
        self.client.save()

        self.deposit_account = DepositAccount()
        self.deposit_account.client = self.client
        self.deposit_account.ethereum_address = self.task_to_compute.requestor_ethereum_address
        self.deposit_account.clean()
        self.deposit_account.save()

        self.deposit_claim = DepositClaim()
        self.deposit_claim.payer_deposit_account = self.deposit_account
        self.deposit_claim.payee_ethereum_address = self.task_to_compute.provider_ethereum_address
        self.deposit_claim.concent_use_case = ConcentUseCase.FORCED_PAYMENT
        self.deposit_claim.amount = 1
        self.deposit_claim.clean()
        self.deposit_claim.save()

    def test_that_discard_claim_should_return_false_and_not_remove_deposit_claim_if_tx_hash_is_none(self):
        claim_removed = discard_claim(self.deposit_claim)

        self.assertFalse(claim_removed)
        self.assertTrue(DepositClaim.objects.filter(pk=self.deposit_claim.pk).exists())

    def test_that_discard_claim_should_return_true_and_remove_deposit_claim_if_tx_hash_is_set(self):
        self.deposit_claim.tx_hash = 64 * '0'
        self.deposit_claim.clean()
        self.deposit_claim.save()

        claim_removed = discard_claim(self.deposit_claim)

        self.assertTrue(claim_removed)
        self.assertFalse(DepositClaim.objects.filter(pk=self.deposit_claim.pk).exists())
