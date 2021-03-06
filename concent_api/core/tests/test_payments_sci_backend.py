from uuid import UUID

import mock
from golem_messages.factories.concents import SubtaskResultsVerifyFactory
from golem_messages.factories.tasks import WantToComputeTaskFactory
from golem_messages.message.concents import SubtaskResultsVerify
from golem_messages.utils import uuid_to_bytes32
from web3 import Web3

from django.conf import settings

from common.testing_helpers import generate_ecc_key_pair
from common.helpers import get_current_utc_timestamp
from core.constants import PAYMENTS_FROM_BLOCK_SAFETY_MARGIN
from core.constants import MOCK_TRANSACTION_HASH
from core.exceptions import SCINotSynchronized
from core.payments.backends import sci_backend
from core.payments.backends.sci_backend import handle_sci_synchronization
from core.tests.utils import ConcentIntegrationTestCase


(CONCENT_PRIVATE_KEY, CONCENT_PUBLIC_KEY) = generate_ecc_key_pair()
(DIFFERENT_CONCENT_PRIVATE_KEY, DIFFERENT_CONCENT_PUBLIC_KEY) = generate_ecc_key_pair()
(SIGNING_SERVICE_PRIVATE_KEY, SIGNING_SERVICE_PUBLIC_KEY) = generate_ecc_key_pair()


class SCIBackendTest(ConcentIntegrationTestCase):

    def setUp(self):
        self.required_confs = 2
        super().setUp()

        self.task_to_compute = self._get_deserialized_task_to_compute()
        self.current_time = get_current_utc_timestamp()
        self.last_block = 8
        self.block_number = 10
        self.transaction_count = 5
        self.deposit_value = 1000
        self.transaction_value = 100
        self.gnt_deposit = '0xcfB81A6EE3ae6aD4Ac59ddD21fB4589055c13DaD'

    def test_that_if_number_of_blocks_from_timestamp_is_smaller_than_required_confs_empty_list_is_returned(self):
        with mock.patch(
            'core.payments.payment_interface.PaymentInterface.__new__',
            return_value=mock.Mock(
                get_latest_confirmed_block_number=mock.Mock(
                    return_value=self.block_number,
                ),
                REQUIRED_CONFS=self.required_confs,
            )
        ):
            with mock.patch(
                'core.payments.backends.sci_backend.BlocksHelper.get_latest_existing_block_at',
                return_value=mock.MagicMock(number=self.last_block + self.required_confs),
            ):
                list_of_payments = sci_backend.get_list_of_payments(
                    self.task_to_compute.requestor_ethereum_address,
                    self.task_to_compute.provider_ethereum_address,
                    self.current_time,
                    sci_backend.TransactionType.FORCED_SUBTASK_PAYMENT,
                )

        self.assertEqual(list_of_payments, [])

    def test_that_sci_backend_get_list_of_payments_should_return_list_of_settlement_payments(self):
        with mock.patch(
            'core.payments.payment_interface.PaymentInterface.__new__',
            return_value=mock.Mock(
                get_forced_payments=mock.Mock(
                    return_value=self._get_list_of_settlement_transactions(),
                ),
                get_latest_confirmed_block_number=mock.Mock(
                    return_value=self.block_number,
                ),
                REQUIRED_CONFS=self.required_confs,
            )
        ) as new_sci_rpc_mock:
            with mock.patch(
                'core.payments.backends.sci_backend.BlocksHelper.get_latest_existing_block_at',
                return_value=mock.MagicMock(number=self.last_block),
            ) as get_latest_existing_block_at_mock:
                list_of_payments = sci_backend.get_list_of_payments(
                    self.task_to_compute.requestor_ethereum_address,
                    self.task_to_compute.provider_ethereum_address,
                    self.current_time,
                    sci_backend.TransactionType.SETTLEMENT,
                )

        self.assertEqual(len(list_of_payments), len(self._get_list_of_settlement_transactions()))

        new_sci_rpc_mock.return_value.get_forced_payments.assert_called_with(
            requestor_address=Web3.toChecksumAddress(self.task_to_compute.requestor_ethereum_address),
            provider_address=Web3.toChecksumAddress(self.task_to_compute.provider_ethereum_address),
            from_block=self.last_block,
            to_block=self.block_number - self.required_confs,
        )

        new_sci_rpc_mock.return_value.get_latest_confirmed_block_number.assert_called()

        get_latest_existing_block_at_mock.assert_called_with(self.current_time)

    def test_that_sci_backend_get_list_of_payments_should_return_list_of_batch_transfers(self):
        with mock.patch(
            'core.payments.payment_interface.PaymentInterface.__new__',
            return_value=mock.Mock(
                get_batch_transfers=mock.Mock(
                    return_value=self._get_list_of_batch_transactions(),
                ),
                get_latest_confirmed_block_number=mock.Mock(
                    return_value=self.block_number,
                ),
                REQUIRED_CONFS=self.required_confs,
            )
        ) as new_sci_rpc_mock:
            with mock.patch(
                'core.payments.backends.sci_backend.BlocksHelper.get_latest_existing_block_at',
                return_value=mock.MagicMock(number=self.last_block),
            ) as get_latest_existing_block_at_mock:
                list_of_payments = sci_backend.get_list_of_payments(
                    self.task_to_compute.requestor_ethereum_address,
                    self.task_to_compute.provider_ethereum_address,
                    self.current_time,
                    sci_backend.TransactionType.BATCH,
                )

        self.assertEqual(len(list_of_payments), len(self._get_list_of_batch_transactions()))

        new_sci_rpc_mock.return_value.get_batch_transfers.assert_called_with(
            payer_address=Web3.toChecksumAddress(self.task_to_compute.requestor_ethereum_address),
            payee_address=Web3.toChecksumAddress(self.task_to_compute.provider_ethereum_address),
            from_block=self.last_block,
            to_block=self.block_number - self.required_confs,
        )

        new_sci_rpc_mock.return_value.get_latest_confirmed_block_number.assert_called()

        get_latest_existing_block_at_mock.assert_called_with(self.current_time)

    def test_that_sci_backend_get_list_of_payments_should_return_list_of_forced_subtask_payments(self):
        with mock.patch(
            'core.payments.payment_interface.PaymentInterface.__new__',
            return_value=mock.Mock(
                get_forced_subtask_payments=mock.Mock(
                    return_value=self._get_list_of_forced_subtask_transactions(),
                ),
                get_latest_confirmed_block_number=mock.Mock(
                    return_value=self.block_number,
                ),
                REQUIRED_CONFS=self.required_confs,
            )
        ) as new_sci_rpc:
            with mock.patch(
                'core.payments.backends.sci_backend.BlocksHelper.get_latest_existing_block_at',
                return_value=mock.MagicMock(number=self.last_block),
            ) as get_latest_existing_block_at:
                list_of_payments = sci_backend.get_list_of_payments(
                    self.task_to_compute.requestor_ethereum_address,
                    self.task_to_compute.provider_ethereum_address,
                    self.current_time,
                    sci_backend.TransactionType.FORCED_SUBTASK_PAYMENT,
                )

        self.assertEqual(len(list_of_payments), len(self._get_list_of_forced_subtask_transactions()))

        new_sci_rpc.return_value.get_forced_subtask_payments.assert_called_with(
            requestor_address=Web3.toChecksumAddress(self.task_to_compute.requestor_ethereum_address),
            provider_address=Web3.toChecksumAddress(self.task_to_compute.provider_ethereum_address),
            from_block=self.last_block - PAYMENTS_FROM_BLOCK_SAFETY_MARGIN,
            to_block=self.block_number - self.required_confs,
        )

        new_sci_rpc.return_value.get_latest_confirmed_block_number.assert_called()

        get_latest_existing_block_at.assert_called_with(self.current_time)

    def test_that_sci_backend_make_settlement_payment_to_provider_should_return_transaction_hash(self):
        self.task_to_compute.sign_all_promissory_notes(
            deposit_contract_address=settings.GNT_DEPOSIT_CONTRACT_ADDRESS,
            private_key=self.REQUESTOR_PRIVATE_KEY,
        )
        (v, r, s) = self.task_to_compute.promissory_note_sig
        with mock.patch(
            'core.payments.payment_interface.PaymentInterface.__new__',
            return_value=mock.Mock(
                get_deposit_value=mock.Mock(
                    return_value=self.deposit_value
                ),
                force_payment=mock.Mock(
                    return_value=MOCK_TRANSACTION_HASH
                ),
            )
        ) as new_sci_rpc:
            transaction_hash = sci_backend.make_settlement_payment(
                requestor_eth_address=self.task_to_compute.requestor_ethereum_address,
                provider_eth_address=self.task_to_compute.provider_ethereum_address,
                value=[self.task_to_compute.price],
                subtask_ids=[self.task_to_compute.subtask_id],
                closure_time=self.current_time,
                v=[v],
                r=[r],
                s=[s],
                reimburse_amount=self.transaction_value,
            )

        self.assertEqual(transaction_hash, MOCK_TRANSACTION_HASH)

        new_sci_rpc.return_value.get_deposit_value.assert_called_with(
            Web3.toChecksumAddress(self.task_to_compute.requestor_ethereum_address)
        )

        new_sci_rpc.return_value.force_payment.assert_called_with(
            requestor_address=Web3.toChecksumAddress(self.task_to_compute.requestor_ethereum_address),
            provider_address=Web3.toChecksumAddress(self.task_to_compute.provider_ethereum_address),
            value=[self.task_to_compute.price],
            subtask_id=[uuid_to_bytes32(UUID(self.task_to_compute.subtask_id))],
            closure_time=self.current_time,
            v=[v],
            r=[r],
            s=[s],
            reimburse_amount=self.transaction_value,
        )

    def test_that_sci_backend_make_settlement_payment_to_provider_should_pay_at_least_requestor_account_balance(self):
        self.task_to_compute.sign_all_promissory_notes(
            deposit_contract_address=settings.GNT_DEPOSIT_CONTRACT_ADDRESS,
            private_key=self.REQUESTOR_PRIVATE_KEY,
        )
        (v, r, s) = self.task_to_compute.promissory_note_sig
        with mock.patch(
            'core.payments.payment_interface.PaymentInterface.__new__',
            return_value=mock.Mock(
                get_deposit_value=mock.Mock(
                    return_value=self.transaction_value - 1
                ),
                force_payment=mock.Mock(
                    return_value=MOCK_TRANSACTION_HASH
                ),
            )
        ) as new_sci_rpc:
            transaction_hash = sci_backend.make_settlement_payment(
                requestor_eth_address=self.task_to_compute.requestor_ethereum_address,
                provider_eth_address=self.task_to_compute.provider_ethereum_address,
                value=[self.task_to_compute.price],
                subtask_ids=[self.task_to_compute.subtask_id],
                closure_time=self.current_time,
                v=[v],
                r=[r],
                s=[s],
                reimburse_amount=self.transaction_value,
            )

        self.assertEqual(transaction_hash, MOCK_TRANSACTION_HASH)

        new_sci_rpc.return_value.get_deposit_value.assert_called_with(
            Web3.toChecksumAddress(self.task_to_compute.requestor_ethereum_address)
        )

        new_sci_rpc.return_value.force_payment.assert_called_with(
            requestor_address=Web3.toChecksumAddress(self.task_to_compute.requestor_ethereum_address),
            provider_address=Web3.toChecksumAddress(self.task_to_compute.provider_ethereum_address),
            value=[self.task_to_compute.price],
            subtask_id=[uuid_to_bytes32(UUID(self.task_to_compute.subtask_id))],
            closure_time=self.current_time,
            v=[v],
            r=[r],
            s=[s],
            reimburse_amount=self.transaction_value - 1,
        )

    def test_that_sci_backend_get_transaction_count_should_return_transaction_count(self):
        with mock.patch(
            'core.payments.payment_interface.PaymentInterface.__new__',
            return_value=mock.Mock(
                get_transaction_count=mock.Mock(
                    return_value=self.transaction_count
                ),
            )
        ) as new_sci_rpc:
            transaction_count = sci_backend.get_transaction_count()

        self.assertEqual(transaction_count, self.transaction_count)

        new_sci_rpc.return_value.get_transaction_count.assert_called()

    def test_that_sci_backend_get_deposit_value_should_return_deposit_value(self):
        with mock.patch(
            'core.payments.payment_interface.PaymentInterface.__new__',
            return_value=mock.Mock(
                get_deposit_value=mock.Mock(
                    return_value=self.deposit_value
                ),
            )
        ) as new_sci_rpc:
            deposit_value = sci_backend.get_deposit_value(
                self.task_to_compute.requestor_ethereum_address,
            )

        self.assertEqual(deposit_value, self.deposit_value)

        new_sci_rpc.return_value.get_deposit_value.assert_called_with(
            self.task_to_compute.requestor_ethereum_address,
        )

    def test_that_sci_backend_force_subtask_payment_should_return_transaction_hash(self):
        self.task_to_compute.sign_all_promissory_notes(
            deposit_contract_address=settings.GNT_DEPOSIT_CONTRACT_ADDRESS,
            private_key=self.REQUESTOR_PRIVATE_KEY,
        )
        v, r, s = self.task_to_compute.promissory_note_sig

        with mock.patch(
            'core.payments.payment_interface.PaymentInterface.__new__',
            return_value=mock.Mock(
                force_subtask_payment=mock.Mock(
                    return_value=MOCK_TRANSACTION_HASH
                ),
            )
        ) as new_sci_rpc:
            transaction_hash = sci_backend.force_subtask_payment(
                requestor_eth_address=self.task_to_compute.requestor_ethereum_address,
                provider_eth_address=self.task_to_compute.provider_ethereum_address,
                value=self.task_to_compute.price,
                subtask_id=self.task_to_compute.subtask_id,
                v=v,
                r=r,
                s=s,
                reimburse_amount=self.transaction_value,
            )

        self.assertEqual(transaction_hash, MOCK_TRANSACTION_HASH)

        new_sci_rpc.return_value.force_subtask_payment.assert_called_with(
            requestor_address=Web3.toChecksumAddress(self.task_to_compute.requestor_ethereum_address),
            provider_address=Web3.toChecksumAddress(self.task_to_compute.provider_ethereum_address),
            value=self.task_to_compute.price,
            subtask_id=sci_backend._hexencode_uuid(self.task_to_compute.subtask_id),
            v=v,
            r=r,
            s=s,
            reimburse_amount=self.transaction_value,
        )

    def test_that_sci_backend_cover_additional_verification_cost_should_return_transaction_hash(self):
        want_to_compute_task = WantToComputeTaskFactory(
            provider_public_key=self._get_provider_ethereum_hex_public_key()
        )
        subtask_results_verify: SubtaskResultsVerify = SubtaskResultsVerifyFactory(**{
            'subtask_results_rejected__'
            'report_computed_task__'
            'task_to_compute__'
            'want_to_compute_task': want_to_compute_task
        })
        subtask_results_verify.sign_concent_promissory_note(
            self.gnt_deposit,
            self.PROVIDER_PRIVATE_KEY,
        )
        v, r, s = subtask_results_verify.concent_promissory_note_sig
        with mock.patch(
            'core.payments.payment_interface.PaymentInterface.__new__',
            return_value=mock.Mock(
                cover_additional_verification_cost=mock.Mock(
                    return_value=MOCK_TRANSACTION_HASH
                ),
            ),
        ) as new_sci_rpc:
            transaction_hash = sci_backend.cover_additional_verification_cost(
                provider_eth_address=self.task_to_compute.provider_ethereum_address,
                value=self.task_to_compute.price,
                subtask_id=self.task_to_compute.subtask_id,
                v=v,
                r=r,
                s=s,
                reimburse_amount=self.transaction_value
            )

        self.assertEqual(transaction_hash, MOCK_TRANSACTION_HASH)

        new_sci_rpc.return_value.cover_additional_verification_cost.assert_called_with(
            address=Web3.toChecksumAddress(self.task_to_compute.provider_ethereum_address),
            value=self.task_to_compute.price,
            subtask_id=sci_backend._hexencode_uuid(self.task_to_compute.subtask_id),
            v=v,
            r=r,
            s=s,
            reimburse_amount=self.transaction_value,
        )

    def test_handle_sci_synchronization_raise_custom_exception_if_not_sync(self):

        @handle_sci_synchronization
        def dummy_handle_exception_if_sci_not_synchronized():
            return None

        with mock.patch(
            'core.payments.payment_interface.PaymentInterface.__new__',
            return_value=mock.Mock(
                is_synchronized=mock.Mock(
                    return_value=False,
                ),
            )
        ):
            with self.assertRaises(SCINotSynchronized):
                dummy_handle_exception_if_sci_not_synchronized()

    def test_handle_sci_synchronization_returns_empty_list_on_specific_value_error(self):

        @handle_sci_synchronization
        def dummy_handle_exception_if_sci_not_synchronized():
            raise ValueError("There are currently no blocks after")

        with mock.patch(
            'core.payments.payment_interface.PaymentInterface.__new__',
            return_value=mock.Mock(
                is_synchronized=mock.Mock(
                    return_value=True,
                ),
            )
        ):
            self.assertEqual(dummy_handle_exception_if_sci_not_synchronized(), [])

    def test_that_handle_sci_synchronization_raises_not_specific_value_error(self):

        @handle_sci_synchronization
        def dummy_handle_exception_if_sci_not_synchronized():
            raise ValueError()

        with mock.patch(
            'core.payments.payment_interface.PaymentInterface.__new__',
            return_value=mock.Mock(
                is_synchronized=mock.Mock(
                    return_value=True,
                ),
            )
        ):
            with self.assertRaises(ValueError):
                dummy_handle_exception_if_sci_not_synchronized()

    def test_that_handle_sci_synchronization_does_not_catch_other_exceptions(self):

        @handle_sci_synchronization
        def dummy_handle_exception_if_sci_not_synchronized():
            raise Exception("foo You!!!")

        with mock.patch(
            'core.payments.payment_interface.PaymentInterface.__new__',
            return_value=mock.Mock(
                is_synchronized=mock.Mock(
                    return_value=True,
                ),
            )
        ):
            with self.assertRaises(Exception):
                dummy_handle_exception_if_sci_not_synchronized()

    def test_that_sci_backend_get_covered_additional_verification_costs_should_return_list_of_payments(self):
        with mock.patch(
            'core.payments.payment_interface.PaymentInterface.__new__',
            return_value=mock.Mock(
                get_covered_additional_verification_costs=mock.Mock(
                    return_value=self._get_list_of_covered_additional_verification_costs()
                ),
                get_latest_confirmed_block_number=mock.Mock(
                    return_value=self.block_number,
                ),
                REQUIRED_CONFS=self.required_confs,
            ),
        ) as new_sci_rpc:
            with mock.patch(
                'core.payments.backends.sci_backend.BlocksHelper.get_latest_existing_block_at',
                return_value=mock.MagicMock(number=self.last_block),
            ) as get_latest_existing_block_at:
                list_of_payments = sci_backend.get_covered_additional_verification_costs(
                    self.task_to_compute.provider_ethereum_address,
                    self.current_time,
                )

        self.assertEqual(len(list_of_payments), len(self._get_list_of_covered_additional_verification_costs()))

        new_sci_rpc.return_value.get_covered_additional_verification_costs.assert_called_with(
            address=Web3.toChecksumAddress(self.task_to_compute.provider_ethereum_address),
            from_block=self.last_block - PAYMENTS_FROM_BLOCK_SAFETY_MARGIN,
            to_block=self.block_number - self.required_confs,
        )

        new_sci_rpc.return_value.get_latest_confirmed_block_number.assert_called()

        get_latest_existing_block_at.assert_called_with(self.current_time)
