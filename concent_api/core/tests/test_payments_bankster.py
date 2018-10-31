from freezegun import freeze_time
import mock

from django.conf import settings
from django.test import override_settings

from common.constants import ConcentUseCase
from core.constants import MOCK_TRANSACTION_HASH
from core.models import Client
from core.models import DepositAccount
from core.models import DepositClaim
from core.payments.bankster import ClaimPaymentInfo
from core.payments.bankster import claim_deposit
from core.payments.bankster import discard_claim
from core.payments.bankster import finalize_payment
from core.payments.bankster import settle_overdue_acceptances
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
        self.subtask_cost = 1

    @override_settings(
        ADDITIONAL_VERIFICATION_COST=0,
    )
    def test_that_when_additional_verification_cost_is_zero_finalize_payment_should_return_empty_provider_claim_payment_info(self):
        with mock.patch('core.payments.service.get_deposit_value', return_value=1) as get_deposit_value:
            with mock.patch('core.payments.service.force_subtask_payment', return_value=MOCK_TRANSACTION_HASH) as force_subtask_payment:
                with mock.patch('core.payments.service.cover_additional_verification_cost', return_value=MOCK_TRANSACTION_HASH) as cover_additional_verification_cost:
                    (requestors_claim_payment_info, providers_claim_payment_info) = finalize_payment(
                        subtask_id=self.task_to_compute.subtask_id,
                        concent_use_case=ConcentUseCase.ADDITIONAL_VERIFICATION,
                        requestor_ethereum_address=self.task_to_compute.requestor_ethereum_address,
                        provider_ethereum_address=self.task_to_compute.provider_ethereum_address,
                        subtask_cost=self.subtask_cost,
                    )

        self.assertIsInstance(requestors_claim_payment_info, ClaimPaymentInfo)
        self.assertIsInstance(providers_claim_payment_info, ClaimPaymentInfo)

        self.assertIsNotNone(requestors_claim_payment_info.tx_hash)
        self.assertIsNotNone(requestors_claim_payment_info.payment_ts)
        self.assertEqual(requestors_claim_payment_info.amount_paid, self.subtask_cost)
        self.assertEqual(requestors_claim_payment_info.amount_pending, 0)

        self.assertIsNone(providers_claim_payment_info.tx_hash)
        self.assertIsNone(providers_claim_payment_info.payment_ts)
        self.assertEqual(providers_claim_payment_info.amount_paid, 0)
        self.assertEqual(providers_claim_payment_info.amount_pending, 0)

        self.assertEqual(get_deposit_value.call_count, 2)
        self.assertEqual(
            get_deposit_value.call_args_list[0][1],
            {'client_eth_address': self.task_to_compute.requestor_ethereum_address}
        )
        self.assertEqual(
            get_deposit_value.call_args_list[1][1],
            {'client_eth_address': self.task_to_compute.provider_ethereum_address}
        )
        force_subtask_payment.assert_called_once_with(
            requestor_eth_address=self.task_to_compute.requestor_ethereum_address,
            provider_eth_address=self.task_to_compute.provider_ethereum_address,
            value=self.subtask_cost,
            subtask_id=self.task_to_compute.subtask_id,
        )
        cover_additional_verification_cost.assert_not_called()

    def test_that_when_both_provider_and_requestor_deposits_are_empty_finalize_payment_should_return_claim_payment_info_objects_with_full_amount_pending(self):
        with mock.patch('core.payments.service.get_deposit_value', return_value=0) as get_deposit_value:
            with mock.patch('core.payments.service.force_subtask_payment', return_value=MOCK_TRANSACTION_HASH) as force_subtask_payment:
                with mock.patch('core.payments.service.cover_additional_verification_cost', return_value=MOCK_TRANSACTION_HASH) as cover_additional_verification_cost:
                    (requestors_claim_payment_info, providers_claim_payment_info) = finalize_payment(
                        subtask_id=self.task_to_compute.subtask_id,
                        concent_use_case=ConcentUseCase.ADDITIONAL_VERIFICATION,
                        requestor_ethereum_address=self.task_to_compute.requestor_ethereum_address,
                        provider_ethereum_address=self.task_to_compute.provider_ethereum_address,
                        subtask_cost=self.subtask_cost,
                    )

        self.assertIsInstance(requestors_claim_payment_info, ClaimPaymentInfo)
        self.assertIsInstance(providers_claim_payment_info, ClaimPaymentInfo)

        self.assertIsNone(requestors_claim_payment_info.tx_hash)
        self.assertIsNone(requestors_claim_payment_info.payment_ts)
        self.assertEqual(requestors_claim_payment_info.amount_paid, 0)
        self.assertEqual(requestors_claim_payment_info.amount_pending, self.subtask_cost)

        self.assertIsNone(providers_claim_payment_info.tx_hash)
        self.assertIsNone(providers_claim_payment_info.payment_ts)
        self.assertEqual(providers_claim_payment_info.amount_paid, 0)
        self.assertEqual(providers_claim_payment_info.amount_pending, settings.ADDITIONAL_VERIFICATION_COST)

        self.assertEqual(get_deposit_value.call_count, 2)
        self.assertEqual(
            get_deposit_value.call_args_list[0][1],
            {'client_eth_address': self.task_to_compute.requestor_ethereum_address}
        )
        self.assertEqual(
            get_deposit_value.call_args_list[1][1],
            {'client_eth_address': self.task_to_compute.provider_ethereum_address}
        )
        force_subtask_payment.assert_not_called()
        cover_additional_verification_cost.assert_not_called()

    @override_settings(
        ADDITIONAL_VERIFICATION_COST=2,
    )
    def test_that_when_both_provider_and_requestor_deposits_are_not_empty_finalize_payment_should_create_transactions(self):
        with mock.patch('core.payments.service.get_deposit_value', return_value=2) as get_deposit_value:
            with mock.patch('core.payments.service.force_subtask_payment', return_value=MOCK_TRANSACTION_HASH) as force_subtask_payment:
                with mock.patch('core.payments.service.cover_additional_verification_cost', return_value=MOCK_TRANSACTION_HASH) as cover_additional_verification_cost:
                    (requestors_claim_payment_info, providers_claim_payment_info) = finalize_payment(
                        subtask_id=self.task_to_compute.subtask_id,
                        concent_use_case=ConcentUseCase.ADDITIONAL_VERIFICATION,
                        requestor_ethereum_address=self.task_to_compute.requestor_ethereum_address,
                        provider_ethereum_address=self.task_to_compute.provider_ethereum_address,
                        subtask_cost=self.subtask_cost,
                    )

        self.assertIsInstance(requestors_claim_payment_info, ClaimPaymentInfo)
        self.assertIsInstance(providers_claim_payment_info, ClaimPaymentInfo)

        self.assertIsNotNone(requestors_claim_payment_info.tx_hash)
        self.assertIsNotNone(requestors_claim_payment_info.payment_ts)
        self.assertEqual(requestors_claim_payment_info.amount_paid, self.subtask_cost)
        self.assertEqual(requestors_claim_payment_info.amount_pending, 0)

        self.assertIsNotNone(providers_claim_payment_info.tx_hash)
        self.assertIsNotNone(providers_claim_payment_info.payment_ts)
        self.assertEqual(providers_claim_payment_info.amount_paid, 2)
        self.assertEqual(providers_claim_payment_info.amount_pending, 0)

        self.assertEqual(get_deposit_value.call_count, 2)
        self.assertEqual(
            get_deposit_value.call_args_list[0][1],
            {'client_eth_address': self.task_to_compute.requestor_ethereum_address}
        )
        self.assertEqual(
            get_deposit_value.call_args_list[1][1],
            {'client_eth_address': self.task_to_compute.provider_ethereum_address}
        )
        force_subtask_payment.assert_called_once_with(
            requestor_eth_address=self.task_to_compute.requestor_ethereum_address,
            provider_eth_address=self.task_to_compute.provider_ethereum_address,
            value=self.subtask_cost,
            subtask_id=self.task_to_compute.subtask_id,
        )
        cover_additional_verification_cost.assert_called_once_with(
            provider_eth_address=self.task_to_compute.provider_ethereum_address,
            value=2,
            subtask_id=self.task_to_compute.subtask_id,
        )

    def test_that_in_not_additional_verification_use_case_provider_claim_payment_info_should_be_empty_even_if_he_has_non_empty_deposit(self):
        with mock.patch('core.payments.service.get_deposit_value', return_value=2) as get_deposit_value:
            with mock.patch('core.payments.service.force_subtask_payment', return_value=MOCK_TRANSACTION_HASH) as force_subtask_payment:
                with mock.patch('core.payments.service.cover_additional_verification_cost', return_value=MOCK_TRANSACTION_HASH) as cover_additional_verification_cost:
                    (requestors_claim_payment_info, providers_claim_payment_info) = finalize_payment(
                        subtask_id=self.task_to_compute.subtask_id,
                        concent_use_case=ConcentUseCase.FORCED_ACCEPTANCE,
                        requestor_ethereum_address=self.task_to_compute.requestor_ethereum_address,
                        provider_ethereum_address=self.task_to_compute.provider_ethereum_address,
                        subtask_cost=self.subtask_cost,
                    )

        self.assertIsInstance(requestors_claim_payment_info, ClaimPaymentInfo)
        self.assertIsInstance(providers_claim_payment_info, ClaimPaymentInfo)

        self.assertIsNotNone(requestors_claim_payment_info.tx_hash)
        self.assertIsNotNone(requestors_claim_payment_info.payment_ts)
        self.assertEqual(requestors_claim_payment_info.amount_paid, self.subtask_cost)
        self.assertEqual(requestors_claim_payment_info.amount_pending, 0)

        self.assertIsNone(providers_claim_payment_info.tx_hash)
        self.assertIsNone(providers_claim_payment_info.payment_ts)
        self.assertEqual(providers_claim_payment_info.amount_paid, 0)
        self.assertEqual(providers_claim_payment_info.amount_pending, 0)

        self.assertEqual(get_deposit_value.call_count, 1)
        self.assertEqual(
            get_deposit_value.call_args_list[0][1],
            {'client_eth_address': self.task_to_compute.requestor_ethereum_address}
        )
        force_subtask_payment.assert_called_once_with(
            requestor_eth_address=self.task_to_compute.requestor_ethereum_address,
            provider_eth_address=self.task_to_compute.provider_ethereum_address,
            value=self.subtask_cost,
            subtask_id=self.task_to_compute.subtask_id,
        )
        cover_additional_verification_cost.assert_not_called()


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
