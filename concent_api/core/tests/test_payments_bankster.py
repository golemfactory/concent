from freezegun import freeze_time
import mock

from django.conf import settings
from django.test import override_settings
from golem_messages import factories

from common.constants import ConcentUseCase
from common.helpers import ethereum_public_key_to_address
from core.constants import MOCK_TRANSACTION_HASH
from core.exceptions import BanksterTimestampError
from core.exceptions import TooSmallProviderDeposit
from core.message_handlers import store_subtask
from core.models import Client
from core.models import DepositAccount
from core.models import DepositClaim
from core.models import Subtask
from core.payments.bankster import claim_deposit
from core.payments.bankster import discard_claim
from core.payments.bankster import finalize_payment
from core.payments.bankster import settle_overdue_acceptances
from core.tests.utils import ConcentIntegrationTestCase
from core.utils import hex_to_bytes_convert
from core.utils import generate_uuid


@override_settings(
    ADDITIONAL_VERIFICATION_COST=1,
    CONCENT_ETHEREUM_PUBLIC_KEY='b51e9af1ae9303315ca0d6f08d15d8fbcaecf6958f037cc68f9ec18a77c6f63eae46daaba5c637e06a3e4a52a2452725aafba3d4fda4e15baf48798170eb7412',
)
class ClaimDepositBanksterTest(ConcentIntegrationTestCase):

    def setUp(self):
        super().setUp()
        self.task_to_compute = self._get_deserialized_task_to_compute()
        self.subtask_cost = 1

    def test_that_claim_deposit_return_deposit_claims_if_both_requestor_and_provider_have_enough_funds(self):
        with mock.patch('core.payments.service.get_deposit_value', return_value=2) as get_deposit_value:
            (claim_against_requestor, claim_against_provider) = claim_deposit(
                subtask_id=self.task_to_compute.subtask_id,
                concent_use_case=ConcentUseCase.ADDITIONAL_VERIFICATION,
                requestor_ethereum_address=self.task_to_compute.requestor_ethereum_address,
                provider_ethereum_address=self.task_to_compute.provider_ethereum_address,
                subtask_cost=self.subtask_cost,
                requestor_public_key=hex_to_bytes_convert(self.task_to_compute.requestor_public_key),
                provider_public_key=hex_to_bytes_convert(self.task_to_compute.provider_public_key),
            )

        self.assertIsInstance(claim_against_requestor, DepositClaim)
        self.assertEqual(claim_against_requestor.subtask_id, self.task_to_compute.subtask_id)
        self.assertEqual(claim_against_requestor.payee_ethereum_address, self.task_to_compute.provider_ethereum_address)
        self.assertEqual(claim_against_requestor.amount, self.subtask_cost)
        self.assertEqual(claim_against_requestor.concent_use_case, ConcentUseCase.ADDITIONAL_VERIFICATION)

        self.assertIsInstance(claim_against_provider, DepositClaim)
        self.assertEqual(claim_against_provider.subtask_id, self.task_to_compute.subtask_id)
        self.assertEqual(
            claim_against_provider.payee_ethereum_address,
            ethereum_public_key_to_address(settings.CONCENT_ETHEREUM_PUBLIC_KEY)
        )
        self.assertEqual(claim_against_provider.amount, settings.ADDITIONAL_VERIFICATION_COST)
        self.assertEqual(claim_against_provider.concent_use_case, ConcentUseCase.ADDITIONAL_VERIFICATION)

        self.assertEqual(get_deposit_value.call_count, 2)

    def test_that_claim_deposit_return_only_requestors_deposit_claim_if_requestor_has_enough_funds_and_it_is_not_additional_verification(self):
        with mock.patch('core.payments.service.get_deposit_value', return_value=1) as get_deposit_value:
            (claim_against_requestor, claim_against_provider) = claim_deposit(
                subtask_id=self.task_to_compute.subtask_id,
                concent_use_case=ConcentUseCase.FORCED_ACCEPTANCE,
                requestor_ethereum_address=self.task_to_compute.requestor_ethereum_address,
                provider_ethereum_address=self.task_to_compute.provider_ethereum_address,
                subtask_cost=1,
                requestor_public_key=hex_to_bytes_convert(self.task_to_compute.requestor_public_key),
                provider_public_key=hex_to_bytes_convert(self.task_to_compute.provider_public_key),
            )

        self.assertIsInstance(claim_against_requestor, DepositClaim)
        self.assertEqual(claim_against_requestor.subtask_id, self.task_to_compute.subtask_id)
        self.assertEqual(claim_against_requestor.payee_ethereum_address, self.task_to_compute.provider_ethereum_address)
        self.assertEqual(claim_against_requestor.amount, self.subtask_cost)
        self.assertEqual(claim_against_requestor.concent_use_case, ConcentUseCase.FORCED_ACCEPTANCE)

        self.assertIsNone(claim_against_provider)
        self.assertEqual(get_deposit_value.call_count, 1)

    def test_that_claim_deposit_return_nones_if_requestor_has_zero_funds(self):
        with mock.patch('core.payments.service.get_deposit_value', return_value=0) as get_deposit_value:
            (claim_against_requestor, claim_against_provider) = claim_deposit(
                subtask_id=self.task_to_compute.subtask_id,
                concent_use_case=ConcentUseCase.ADDITIONAL_VERIFICATION,
                requestor_ethereum_address=self.task_to_compute.requestor_ethereum_address,
                provider_ethereum_address=self.task_to_compute.provider_ethereum_address,
                subtask_cost=1,
                requestor_public_key=hex_to_bytes_convert(self.task_to_compute.requestor_public_key),
                provider_public_key=hex_to_bytes_convert(self.task_to_compute.provider_public_key),
            )

        self.assertIsNone(claim_against_requestor)
        self.assertIsNone(claim_against_provider)
        self.assertEqual(get_deposit_value.call_count, 2)

    @override_settings(
        ADDITIONAL_VERIFICATION_COST=0
    )
    def test_that_claim_deposit_return_none_for_provider_if_additional_verification_cost_is_zero(self):
        with mock.patch('core.payments.service.get_deposit_value', return_value=1) as get_deposit_value:
            (claim_against_requestor, claim_against_provider) = claim_deposit(
                subtask_id=self.task_to_compute.subtask_id,
                concent_use_case=ConcentUseCase.ADDITIONAL_VERIFICATION,
                requestor_ethereum_address=self.task_to_compute.requestor_ethereum_address,
                provider_ethereum_address=self.task_to_compute.provider_ethereum_address,
                subtask_cost=1,
                requestor_public_key=hex_to_bytes_convert(self.task_to_compute.requestor_public_key),
                provider_public_key=hex_to_bytes_convert(self.task_to_compute.provider_public_key),
            )

        self.assertIsNotNone(claim_against_requestor)
        self.assertIsNone(claim_against_provider)
        self.assertEqual(get_deposit_value.call_count, 1)

    @override_settings(
        ADDITIONAL_VERIFICATION_COST=2
    )
    def test_that_claim_deposit_return_none_for_provider_if_provider_has_less_funds_than_needed(self):
        with mock.patch('core.payments.service.get_deposit_value', return_value=1) as get_deposit_value:
            with self.assertRaises(TooSmallProviderDeposit):
                claim_deposit(
                    subtask_id=self.task_to_compute.subtask_id,
                    concent_use_case=ConcentUseCase.ADDITIONAL_VERIFICATION,
                    requestor_ethereum_address=self.task_to_compute.requestor_ethereum_address,
                    provider_ethereum_address=self.task_to_compute.provider_ethereum_address,
                    subtask_cost=1,
                    requestor_public_key=hex_to_bytes_convert(self.task_to_compute.requestor_public_key),
                    provider_public_key=hex_to_bytes_convert(self.task_to_compute.provider_public_key),
                )

        self.assertEqual(get_deposit_value.call_count, 2)


class FinalizePaymentBanksterTest(ConcentIntegrationTestCase):

    def setUp(self):
        super().setUp()
        self.task_to_compute = self._get_deserialized_task_to_compute()

        self.subtask = store_subtask(
            task_id=self.task_to_compute.task_id,
            subtask_id=self.task_to_compute.subtask_id,
            provider_public_key=self.PROVIDER_PUBLIC_KEY,
            requestor_public_key=self.REQUESTOR_PUBLIC_KEY,
            state=Subtask.SubtaskState.ACCEPTED,
            next_deadline=None,
            task_to_compute=self.task_to_compute,
            report_computed_task=factories.tasks.ReportComputedTaskFactory(task_to_compute=self.task_to_compute)
        )
        self.subtask.full_clean()
        self.subtask.save()

        self.deposit_account = DepositAccount()
        self.deposit_account.client = self.subtask.requestor
        self.deposit_account.ethereum_address = self.task_to_compute.requestor_ethereum_address
        self.deposit_account.clean()
        self.deposit_account.save()

        self.deposit_claim = DepositClaim()
        self.deposit_claim.subtask_id = self.task_to_compute.subtask_id
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
            with mock.patch('core.payments.service.force_subtask_payment', return_value=MOCK_TRANSACTION_HASH) as force_subtask_payment:
                returned_value = finalize_payment(self.deposit_claim)
        self.assertEqual(returned_value, MOCK_TRANSACTION_HASH)

        get_deposit_value.assert_called_with(
            client_eth_address=self.deposit_claim.payer_deposit_account.ethereum_address,
        )
        force_subtask_payment.assert_called_once_with(
            requestor_eth_address=self.deposit_claim.payer_deposit_account.ethereum_address,
            provider_eth_address=self.deposit_claim.payee_ethereum_address,
            value=self.deposit_claim.amount,
            subtask_id=self.deposit_claim.subtask_id,
        )

    def test_that_when_deposit_claim_is_for_additional_verification_use_case_finalize_payment_should_call_cover_additional_verification_cost(self):
        self.deposit_claim.concent_use_case = ConcentUseCase.ADDITIONAL_VERIFICATION
        self.deposit_claim.clean()
        self.deposit_claim.save()

        with mock.patch('core.payments.service.get_deposit_value', return_value=2) as get_deposit_value:
            with mock.patch('core.payments.service.force_subtask_payment', return_value=MOCK_TRANSACTION_HASH) as force_subtask_payment:
                returned_value = finalize_payment(self.deposit_claim)

        self.assertEqual(returned_value, MOCK_TRANSACTION_HASH)

        get_deposit_value.assert_called_with(
            client_eth_address=self.deposit_claim.payer_deposit_account.ethereum_address,
        )
        force_subtask_payment.assert_called_once_with(
            requestor_eth_address=self.deposit_claim.payer_deposit_account.ethereum_address,
            provider_eth_address=self.deposit_claim.payee_ethereum_address,
            value=self.deposit_claim.amount,
            subtask_id=self.deposit_claim.subtask_id,
        )

    def test_that_when_there_are_other_deposit_claims_finalize_payment_substract_them_from_currently_processed_claim(self):
        self.deposit_claim = DepositClaim()
        self.deposit_claim.subtask_id = self._get_uuid('1')
        self.deposit_claim.payer_deposit_account = self.deposit_account
        self.deposit_claim.payee_ethereum_address = self.task_to_compute.provider_ethereum_address
        self.deposit_claim.concent_use_case = ConcentUseCase.FORCED_ACCEPTANCE
        self.deposit_claim.amount = 2
        self.deposit_claim.clean()
        # Save twice because we want two claims.
        self.deposit_claim.save()
        self.deposit_claim.pk = None
        self.deposit_claim.subtask_id = generate_uuid()
        self.deposit_claim.save()

        with mock.patch('core.payments.service.get_deposit_value', return_value=5) as get_deposit_value:
            with mock.patch('core.payments.service.force_subtask_payment', return_value=MOCK_TRANSACTION_HASH) as force_subtask_payment:
                returned_value = finalize_payment(self.deposit_claim)

        self.assertEqual(returned_value, MOCK_TRANSACTION_HASH)

        get_deposit_value.assert_called_with(
            client_eth_address=self.deposit_claim.payer_deposit_account.ethereum_address,
        )
        force_subtask_payment.assert_called_once_with(
            requestor_eth_address=self.deposit_claim.payer_deposit_account.ethereum_address,
            provider_eth_address=self.deposit_claim.payee_ethereum_address,
            # 5 - (2 + 2) | deposit_value - sum_of_other_claims
            value=1,
            subtask_id=self.deposit_claim.subtask_id,
        )


class SettleOverdueAcceptancesBanksterTest(ConcentIntegrationTestCase):

    def test_that_settle_overdue_acceptances_should_return_none_if_subtask_costs_where_already_paid(self):
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
            claim_against_requestor = settle_overdue_acceptances(
                requestor_ethereum_address=task_to_compute.requestor_ethereum_address,
                provider_ethereum_address=task_to_compute.provider_ethereum_address,
                acceptances=subtask_results_accepted_list,
                requestor_public_key=hex_to_bytes_convert(task_to_compute.requestor_public_key),
            )

        self.assertIsNone(claim_against_requestor)
        get_list_of_payments_mock.assert_called()

    @override_settings(
        PAYMENT_DUE_TIME=10
    )
    def test_that_settle_overdue_acceptances_should_return_none_if_requestor_deposit_value_is_zero(self):
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
                claim_against_requestor = settle_overdue_acceptances(
                    requestor_ethereum_address=task_to_compute.requestor_ethereum_address,
                    provider_ethereum_address=task_to_compute.provider_ethereum_address,
                    acceptances=subtask_results_accepted_list,
                    requestor_public_key=hex_to_bytes_convert(task_to_compute.requestor_public_key),
                )

        get_deposit_value_mock.assert_called()

        self.assertIsNone(claim_against_requestor)

    @override_settings(
        PAYMENT_DUE_TIME=10
    )
    def test_that_settle_overdue_acceptances_should_return_claim_deposit_with_amount_paid(self):
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
                    claim_against_requestor = settle_overdue_acceptances(
                        requestor_ethereum_address=task_to_compute.requestor_ethereum_address,
                        provider_ethereum_address=task_to_compute.provider_ethereum_address,
                        acceptances=subtask_results_accepted_list,
                        requestor_public_key=hex_to_bytes_convert(task_to_compute.requestor_public_key),
                    )

        get_deposit_value_mock.assert_called_once()
        get_list_of_payments_mock.assert_called()

        self.assertIsNotNone(claim_against_requestor.tx_hash)

        # The results of payments are calculated in the following way:
        # already_paid_value = 15000 - (
        #   (1000 + 2000 + 3000 + 4000)(batch_transactions) +
        #   (1000 + 2000)(force_transactions)
        # )
        # already_paid_value == 13000, so 2000 left
        # get_deposit_value returns 1000, so 1000 paid and 1000 left (pending)

        self.assertEqual(claim_against_requestor.amount, 1000)

    def test_that_settle_overdue_acceptances_should_raise_exception_if_any_transaction_from_acceptances_list_is_before_youngest_transaction_timestamp(self):
        task_to_compute = self._get_deserialized_task_to_compute(
            price=13000,
        )

        subtask_results_accepted_list = [
            self._get_deserialized_subtask_results_accepted(
                task_to_compute=task_to_compute,
                payment_ts="2018-02-05 12:00:00",
            )
        ]

        with mock.patch(
            'core.payments.bankster.service.get_list_of_payments',
            side_effect=[
                [self._create_payment_object(amount=1000, closure_time=subtask_results_accepted_list[0].payment_ts + 1)],
                self._get_list_of_force_transactions(),
            ]
        ) as get_list_of_payments_mock:
            with self.assertRaises(BanksterTimestampError):
                settle_overdue_acceptances(
                    requestor_ethereum_address=task_to_compute.requestor_ethereum_address,
                    provider_ethereum_address=task_to_compute.provider_ethereum_address,
                    acceptances=subtask_results_accepted_list,
                    requestor_public_key=hex_to_bytes_convert(task_to_compute.requestor_public_key),
                )

        get_list_of_payments_mock.assert_called()


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
