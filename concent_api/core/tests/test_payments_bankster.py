import mock

from django.test import override_settings

from common.constants import ConcentUseCase
from core.payments.bankster import claim_deposit
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
