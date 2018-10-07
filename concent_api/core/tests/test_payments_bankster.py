from ethereum.transactions import Transaction
import mock

from django.conf import settings
from django.test import override_settings

from common.constants import ConcentUseCase
from core.payments.bankster import ClaimPaymentInfo
from core.payments.bankster import claim_deposit
from core.payments.bankster import finalize_payment
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

    def _create_transaction(self):
        return Transaction(
            nonce=1,
            gasprice=10 ** 6,
            startgas=80000,
            value=10,
            to=b'7917bc33eea648809c28',
            v=28,
            r=105276041803796697890139158600495981346175539693000174052040367753737207356915,
            s=51455402244652678469360859593599492752947853083356495769067973718806366068077,
            data=b'3078666333323333396130303030303030303030303030303030303030303030303032393662363963383738613734393865663463343531363436353231336564663834666334623330303030303030303030303030303030303030303030303030333431336437363161356332633362656130373531373064333239363566636161386261303533633030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303237313030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303562343336643666',
        )

    @override_settings(
        ADDITIONAL_VERIFICATION_COST=0,
    )
    def test_that_when_additional_verification_cost_is_zero_finalize_payment_should_return_empty_provider_claim_payment_info(self):
        with mock.patch('core.payments.service.get_deposit_value', return_value=1) as get_deposit_value:
            with mock.patch('core.payments.service.force_subtask_payment', return_value=self._create_transaction()) as force_subtask_payment:
                with mock.patch('core.payments.service.cover_additional_verification_cost', return_value=self._create_transaction()) as cover_additional_verification_cost:
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
            with mock.patch('core.payments.service.force_subtask_payment', return_value=self._create_transaction()) as force_subtask_payment:
                with mock.patch('core.payments.service.cover_additional_verification_cost', return_value=self._create_transaction()) as cover_additional_verification_cost:
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
            with mock.patch('core.payments.service.force_subtask_payment', return_value=self._create_transaction()) as force_subtask_payment:
                with mock.patch('core.payments.service.cover_additional_verification_cost', return_value=self._create_transaction()) as cover_additional_verification_cost:
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
            with mock.patch('core.payments.service.force_subtask_payment', return_value=self._create_transaction()) as force_subtask_payment:
                with mock.patch('core.payments.service.cover_additional_verification_cost', return_value=self._create_transaction()) as cover_additional_verification_cost:
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
