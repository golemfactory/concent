from freezegun import freeze_time
import mock

from django.conf import settings
from django.test import override_settings
from golem_messages import factories

from common.constants import ConcentUseCase
from common.helpers import ethereum_public_key_to_address
from core.constants import MOCK_TRANSACTION_HASH
from core.exceptions import BanksterTransactionMismatchError
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
from core.utils import generate_uuid
from core.utils import get_current_utc_timestamp
from core.utils import hex_to_bytes_convert
from core.utils import parse_timestamp_to_utc_datetime


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

    def setUp(self):
        super().setUp()
        self.get_deposit_value_return_value_default = 15000
        self.task_to_compute = None
        self.subtask_results_accepted_list = None
        self.requestor_client = None
        self.requestor_deposit_account = None
        self.validate_list_of_transaction_mock = None
        self.get_deposit_value_mock = None
        self.get_list_of_payments_mock = None

    def create_subtask_results_accepted_list(self, price, number_of_items=1):
        self.task_to_compute = self._get_deserialized_task_to_compute(price=price)
        self.subtask_results_accepted_list = [
            self._get_deserialized_subtask_results_accepted(
                report_computed_task=self._get_deserialized_report_computed_task(
                    timestamp="2018-02-04 10:00:05",
                    task_to_compute=self.task_to_compute
                )
            ) for _ in range(number_of_items)
        ]

    def create_client_and_related_deposit_account(self):
        self.requestor_client = Client(
            public_key=self.task_to_compute.requestor_id
        )
        self.requestor_client.full_clean()
        self.requestor_client.save()

        self.requestor_deposit_account = DepositAccount(
            client=self.requestor_client,
            ethereum_address=self.task_to_compute.requestor_ethereum_address,
        )
        self.requestor_deposit_account.full_clean()
        self.requestor_deposit_account.save()

    def create_deposit_claim(self, amount, tx_hash):
        deposit_claim = DepositClaim(
            payee_ethereum_address=self.task_to_compute.provider_ethereum_address,
            payer_deposit_account=self.requestor_deposit_account,
            amount=amount,
            concent_use_case=ConcentUseCase.FORCED_PAYMENT,
            tx_hash=tx_hash,
            closure_time=parse_timestamp_to_utc_datetime(get_current_utc_timestamp()),
        )
        deposit_claim.full_clean()
        deposit_claim.save()

    def call_settle_overdue_acceptances_with_mocked_sci_functions(
        self,
        get_deposit_value_return_value=None,
        get_list_of_payments_return_value=None,
    ):
        with freeze_time("2018-02-05 10:00:25"):
            with mock.patch('core.payments.bankster.validate_list_of_transaction_timestamp') as self.validate_list_of_transaction_mock:
                with mock.patch(
                    'core.payments.bankster.service.get_deposit_value',
                    return_value=(
                        get_deposit_value_return_value if get_deposit_value_return_value is not None
                        else self.get_deposit_value_return_value_default
                    ),
                ) as self.get_deposit_value_mock:
                    with mock.patch(
                        'core.payments.bankster.service.get_list_of_payments',
                        side_effect=[
                            (
                                get_list_of_payments_return_value if get_list_of_payments_return_value is not None
                                else self._get_list_of_settlement_transactions()
                            ),
                            self._get_list_of_batch_transactions()
                        ],
                    ) as self.get_list_of_payments_mock:
                        claim_against_requestor = settle_overdue_acceptances(
                            requestor_ethereum_address=self.task_to_compute.requestor_ethereum_address,
                            provider_ethereum_address=self.task_to_compute.provider_ethereum_address,
                            acceptances=self.subtask_results_accepted_list,
                            requestor_public_key=hex_to_bytes_convert(self.task_to_compute.requestor_public_key),
                        )

        return claim_against_requestor

    def assert_mocked_sci_functions_were_called(self, get_list_of_payments_call_count=2):
        self.get_deposit_value_mock.assert_called_once()
        self.validate_list_of_transaction_mock.assert_called_once()
        self.assertEqual(self.get_list_of_payments_mock.call_count, get_list_of_payments_call_count)

    def test_that_settle_overdue_acceptances_should_return_none_if_subtask_costs_where_already_paid(self):
        """
        In this test we have following calculations:

        TaskToCompute price:                                     3000
        Sum of amounts from list of settlement transactions:     3000
        Sum of amounts from list of transactions:                4000 (does not matter in this case)
        Requestor deposit value:                                15000 (does not matter in this case)

        Amount pending = 3000 - 3000 = 0
        """
        self.create_subtask_results_accepted_list(price=3000)

        claim_against_requestor = self.call_settle_overdue_acceptances_with_mocked_sci_functions()

        self.assertIsNone(claim_against_requestor)
        self.assert_mocked_sci_functions_were_called()

    def test_that_settle_overdue_acceptances_should_return_none_if_requestor_deposit_value_is_zero(self):
        """
        In this test we have following calculations:

        TaskToCompute price:                                    3000 (does not matter in this case)
        Sum of amounts from list of settlement transactions:    3000 (does not matter in this case)
        Sum of amounts from list of transactions:               4000 (does not matter in this case)
        Requestor deposit value:                                0
        """
        self.create_subtask_results_accepted_list(price=3000)

        claim_against_requestor = self.call_settle_overdue_acceptances_with_mocked_sci_functions(
            get_deposit_value_return_value=0
        )

        self.assertIsNone(claim_against_requestor)
        self.assert_mocked_sci_functions_were_called()

    def test_that_settle_overdue_acceptances_should_return_claim_deposit_with_amount_paid(self):
        """
        In this test we have following calculations:

        TaskToCompute price:                                    15000
        Sum of amounts from list of settlement transactions:     3000
        Sum of amounts from list of transactions:                4000
        Requestor deposit value:                                15000

        Amount pending = 15000 - (3000 + 4000) = 8000
        Payable amount = min(15000, 8000) = 8000
        """
        self.create_subtask_results_accepted_list(price=15000)

        claim_against_requestor = self.call_settle_overdue_acceptances_with_mocked_sci_functions()

        self.assertIsNotNone(claim_against_requestor.tx_hash)
        self.assertEqual(claim_against_requestor.amount, 8000)
        self.assert_mocked_sci_functions_were_called()

    def test_that_settle_overdue_acceptances_should_return_claim_deposit_with_amount_paid_if_there_was_no_previous_settlement_transactions(self):
        """
        In this test we have following calculations:

        TaskToCompute price:                                    15000
        Sum of amounts from list of settlement transactions:        0
        Sum of amounts from list of transactions:                4000
        Requestor deposit value:                                20000

        Amount pending = 15000 - 4000 = 11000
        Payable amount = min(11000, 20000) = 11000
        """
        self.create_subtask_results_accepted_list(price=15000)

        claim_against_requestor = self.call_settle_overdue_acceptances_with_mocked_sci_functions(
            get_deposit_value_return_value=20000,
            get_list_of_payments_return_value=[],
        )

        self.assertIsNotNone(claim_against_requestor.tx_hash)
        self.assertEqual(claim_against_requestor.amount, 11000)
        self.assert_mocked_sci_functions_were_called()

    def test_that_settle_overdue_acceptances_should_return_claim_deposit_with_amount_paid_when_requesting_payment_for_multiple_subtasks(self):
        """
        In this test we have following calculations:

        TaskToCompute price:                         2 x 7500 = 15000
        Sum of amounts from list of settlement transactions:     3000
        Sum of amounts from list of transactions:                4000
        Requestor deposit value:                                15000

        Amount pending = 15000 - (3000 + 4000) = 8000
        Payable amount = min(8000, 15000) = 8000
        """
        self.create_subtask_results_accepted_list(price=7500, number_of_items=2)

        claim_against_requestor = self.call_settle_overdue_acceptances_with_mocked_sci_functions()

        self.assertIsNotNone(claim_against_requestor.tx_hash)
        self.assertEqual(claim_against_requestor.amount, 8000)
        self.assert_mocked_sci_functions_were_called()

    def test_that_settle_overdue_acceptances_should_return_claim_deposit_with_amount_available_on_requestor_deposit_if_it_is_greater_then_left_amount(self):
        """
        In this test we have following calculations:

        TaskToCompute price:                                    15000
        Sum of amounts from list of settlement transactions:     3000
        Sum of amounts from list of transactions:                4000
        Requestor deposit value:                                 5000

        Amount pending = 15000 - (3000 + 4000) = 8000
        Payable amount = min(8000, 5000) = 5000
        """
        self.create_subtask_results_accepted_list(price=15000)

        claim_against_requestor = self.call_settle_overdue_acceptances_with_mocked_sci_functions(
            get_deposit_value_return_value=5000,
        )

        self.assertIsNotNone(claim_against_requestor.tx_hash)
        self.assertEqual(claim_against_requestor.amount, 5000)
        self.assert_mocked_sci_functions_were_called()

    def test_that_settle_overdue_acceptances_should_return_claim_deposit_with_amount_paid_when_there_are_existing_claims(self):
        """
        In this test we have following calculations:

        TaskToCompute price:                                    15000
        Sum of amounts from list of settlement transactions:        0
        Sum of amounts from list of transactions:                4000
        Requestor deposit value:                                15000
        Sum of existing claims:                                  7000

        Amount pending = 15000 - (4000 + 7000) = 4000
        Payable amount = min(4000, 15000) = 4000
        """
        self.create_subtask_results_accepted_list(price=15000)
        self.create_client_and_related_deposit_account()
        self.create_deposit_claim(
            amount=3000,
            tx_hash=64 * 'A',
        )
        self.create_deposit_claim(
            amount=4000,
            tx_hash=64 * 'B',
        )

        claim_against_requestor = self.call_settle_overdue_acceptances_with_mocked_sci_functions(
            get_list_of_payments_return_value=[]
        )

        self.assertIsNotNone(claim_against_requestor.tx_hash)
        self.assertEqual(claim_against_requestor.amount, 4000)
        self.assert_mocked_sci_functions_were_called()

    def test_that_settle_overdue_acceptances_should_return_claim_deposit_with_amount_paid_when_there_are_both_existing_claims_and_payments(self):
        """
        In this test we have following calculations:

        TaskToCompute price:                                    15000
        Sum of amounts from list of settlement transactions:     3000
        Sum of amounts from list of transactions:                4000
        Requestor deposit value:                                15000
        Sum of existing claims:                                  7000

        Amount pending = 15000 - (3000 + 4000 + 7000) = 1000
        Payable amount = min(1000, 15000) = 1000
        """
        self.create_subtask_results_accepted_list(price=15000)
        self.create_client_and_related_deposit_account()
        self.create_deposit_claim(
            amount=3000,
            tx_hash=64 * 'A',
        )
        self.create_deposit_claim(
            amount=4000,
            tx_hash=64 * 'B',
        )

        claim_against_requestor = self.call_settle_overdue_acceptances_with_mocked_sci_functions()

        self.assertIsNotNone(claim_against_requestor.tx_hash)
        self.assertEqual(claim_against_requestor.amount, 1000)
        self.assert_mocked_sci_functions_were_called()

    def test_that_settle_overdue_acceptances_should_return_claim_deposit_with_amount_paid_when_there_are_both_existing_claims_and_payments_with_the_same_transaction_hash(self):
        """
        In this test we have following calculations:

        TaskToCompute price:                                    15000
        Sum of amounts from list of settlement transactions:     2000
        Sum of amounts from list of transactions:                4000
        Requestor deposit value:                                15000
        Sum of existing claims:                                  6000

        Amount pending = 15000 - (2000 + 4000 + 6000 - 2000) = 5000  // (2000 from claim matching blockchain transaction is ignored)
        Payable amount = min(5000, 15000) = 5000
        """
        self.create_subtask_results_accepted_list(price=15000)
        self.create_client_and_related_deposit_account()

        with freeze_time("2018-02-05 10:00:25"):
            self.create_deposit_claim(
                amount=2000,
                tx_hash=MOCK_TRANSACTION_HASH,
            )

        self.create_deposit_claim(
            amount=4000,
            tx_hash=64 * 'B',
        )

        with freeze_time("2018-02-05 10:00:25"):
            list_of_payments_return_value = [
                self._create_settlement_payment_object(
                    amount=2000,
                )
            ]

        claim_against_requestor = self.call_settle_overdue_acceptances_with_mocked_sci_functions(
            get_list_of_payments_return_value=list_of_payments_return_value,
        )

        self.assertIsNotNone(claim_against_requestor.tx_hash)
        self.assertEqual(claim_against_requestor.amount, 5000)
        self.assert_mocked_sci_functions_were_called()

    def test_that_settle_overdue_acceptances_should_raise_exception_if_transaction_from_blockchain_will_not_match_database_claim(self):
        """
        In this test we have following calculations:

        TaskToCompute price:                                    15000
        Sum of amounts from list of settlement transactions:     3000
        Sum of amounts from list of transactions:                4000
        Requestor deposit value:                                15000
        Sum of existing claims:                                  7000
        """
        self.create_subtask_results_accepted_list(price=15000)
        self.create_client_and_related_deposit_account()

        self.create_deposit_claim(
            amount=3000,
            tx_hash=MOCK_TRANSACTION_HASH,
        )

        with self.assertRaises(BanksterTransactionMismatchError):
            self.call_settle_overdue_acceptances_with_mocked_sci_functions()

        self.assert_mocked_sci_functions_were_called(get_list_of_payments_call_count=1)


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
        self.deposit_claim.closure_time = parse_timestamp_to_utc_datetime(get_current_utc_timestamp())
        self.deposit_claim.full_clean()
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
