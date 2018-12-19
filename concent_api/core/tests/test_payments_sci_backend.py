from django.test import override_settings

import mock
from web3 import Web3

from common.testing_helpers import generate_ecc_key_pair
from common.helpers import get_current_utc_timestamp
from core.constants import MOCK_TRANSACTION_HASH
from core.payments.backends import sci_backend
from core.tests.utils import ConcentIntegrationTestCase


(CONCENT_PRIVATE_KEY, CONCENT_PUBLIC_KEY) = generate_ecc_key_pair()
(DIFFERENT_CONCENT_PRIVATE_KEY, DIFFERENT_CONCENT_PUBLIC_KEY) = generate_ecc_key_pair()
(SIGNING_SERVICE_PRIVATE_KEY, SIGNING_SERVICE_PUBLIC_KEY) = generate_ecc_key_pair()


@override_settings(
    CONCENT_ETHEREUM_PUBLIC_KEY='b51e9af1ae9303315ca0d6f08d15d8fbcaecf6958f037cc68f9ec18a77c6f63eae46daaba5c637e06a3e4a52a2452725aafba3d4fda4e15baf48798170eb7412',
    GETH_ADDRESS='http://localhost:5555/',
    GNT_DEPOSIT_CONTRACT_ADDRESS='0xcfB81A6EE3ae6aD4Ac59ddD21fB4589055c13DaD',
)
class SCIBackendTest(ConcentIntegrationTestCase):

    def setUp(self):
        super().setUp()

        self.task_to_compute = self._get_deserialized_task_to_compute()
        self.current_time = get_current_utc_timestamp()
        self.last_block = 8
        self.block_number = 10
        self.transaction_count = 5
        self.deposit_value = 1000
        self.transaction_value = 100

    def test_that_sci_backend_get_list_of_payments_should_return_list_of_forced_subtask_payments(self):
        with mock.patch(
            'core.payments.payment_interface.PaymentInterface.__new__',
            return_value=mock.Mock(
                get_forced_payments=mock.Mock(
                    return_value=self._get_list_of_force_transactions(),
                ),
                get_block_number=mock.Mock(
                    return_value=self.block_number,
                ),
            )
        ) as new_sci_rpc:
            with mock.patch(
                'core.payments.backends.sci_backend.BlocksHelper.get_first_block_after',
                return_value=mock.MagicMock(number=self.last_block),
            ) as get_first_block_after:
                list_of_payments = sci_backend.get_list_of_payments(
                    self.task_to_compute.requestor_ethereum_address,
                    self.task_to_compute.provider_ethereum_address,
                    self.current_time,
                    sci_backend.TransactionType.FORCE,
                )

        self.assertEqual(len(list_of_payments), len(self._get_list_of_force_transactions()))

        new_sci_rpc.return_value.get_forced_payments.assert_called_with(
            requestor_address=Web3.toChecksumAddress(self.task_to_compute.requestor_ethereum_address),
            provider_address=Web3.toChecksumAddress(self.task_to_compute.provider_ethereum_address),
            from_block=self.last_block,
            to_block=self.block_number,
        )

        new_sci_rpc.return_value.get_block_number.assert_called()

        get_first_block_after.assert_called_with(
            self.current_time
        )

    def test_that_sci_backend_get_list_of_payments_should_return_list_of_batch_transfers(self):
        with mock.patch(
            'core.payments.payment_interface.PaymentInterface.__new__',
            return_value=mock.Mock(
                get_batch_transfers=mock.Mock(
                    return_value=self._get_list_of_batch_transactions(),
                ),
                get_block_number=mock.Mock(
                    return_value=self.block_number,
                ),
            )
        ) as new_sci_rpc:
            with mock.patch(
                'core.payments.backends.sci_backend.BlocksHelper.get_first_block_after',
                return_value=mock.MagicMock(number=self.last_block),
            ) as get_first_block_after:
                list_of_payments = sci_backend.get_list_of_payments(
                    self.task_to_compute.requestor_ethereum_address,
                    self.task_to_compute.provider_ethereum_address,
                    self.current_time,
                    sci_backend.TransactionType.BATCH,
                )

        self.assertEqual(len(list_of_payments), len(self._get_list_of_batch_transactions()))

        new_sci_rpc.return_value.get_batch_transfers.assert_called_with(
            payer_address=Web3.toChecksumAddress(self.task_to_compute.requestor_ethereum_address),
            payee_address=Web3.toChecksumAddress(self.task_to_compute.provider_ethereum_address),
            from_block=self.last_block,
            to_block=self.block_number,
        )

        new_sci_rpc.return_value.get_block_number.assert_called()

        get_first_block_after.assert_called_with(
            self.current_time
        )

    def test_that_sci_backend_make_force_payment_to_provider_should_return_transaction_hash(self):
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
            transaction_hash = sci_backend.make_force_payment_to_provider(
                self.task_to_compute.requestor_ethereum_address,
                self.task_to_compute.provider_ethereum_address,
                self.transaction_value,
                self.current_time,
            )

        self.assertEqual(transaction_hash, MOCK_TRANSACTION_HASH)

        new_sci_rpc.return_value.get_deposit_value.assert_called_with(
            Web3.toChecksumAddress(self.task_to_compute.requestor_ethereum_address)
        )

        new_sci_rpc.return_value.force_payment.assert_called_with(
            requestor_address=Web3.toChecksumAddress(self.task_to_compute.requestor_ethereum_address),
            provider_address=Web3.toChecksumAddress(self.task_to_compute.provider_ethereum_address),
            value=self.transaction_value,
            closure_time=self.current_time,
        )

    def test_that_sci_backend_make_force_payment_to_provider_should_pay_at_least_requestor_account_balance(self):
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
            transaction_hash = sci_backend.make_force_payment_to_provider(
                self.task_to_compute.requestor_ethereum_address,
                self.task_to_compute.provider_ethereum_address,
                self.transaction_value,
                self.current_time,
            )

        self.assertEqual(transaction_hash, MOCK_TRANSACTION_HASH)

        new_sci_rpc.return_value.get_deposit_value.assert_called_with(
            Web3.toChecksumAddress(self.task_to_compute.requestor_ethereum_address)
        )

        new_sci_rpc.return_value.force_payment.assert_called_with(
            requestor_address=Web3.toChecksumAddress(self.task_to_compute.requestor_ethereum_address),
            provider_address=Web3.toChecksumAddress(self.task_to_compute.provider_ethereum_address),
            value=self.transaction_value - 1,
            closure_time=self.current_time,
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
        with mock.patch(
            'core.payments.payment_interface.PaymentInterface.__new__',
            return_value=mock.Mock(
                force_subtask_payment=mock.Mock(
                    return_value=MOCK_TRANSACTION_HASH
                ),
            )
        ) as new_sci_rpc:
            transaction_hash = sci_backend.force_subtask_payment(
                self.task_to_compute.requestor_ethereum_address,
                self.task_to_compute.provider_ethereum_address,
                self.transaction_value,
                self.task_to_compute.subtask_id,
            )

        self.assertEqual(transaction_hash, MOCK_TRANSACTION_HASH)

        new_sci_rpc.return_value.force_subtask_payment.assert_called_with(
            requestor_address=Web3.toChecksumAddress(self.task_to_compute.requestor_ethereum_address),
            provider_address=Web3.toChecksumAddress(self.task_to_compute.provider_ethereum_address),
            value=self.transaction_value,
            subtask_id=sci_backend._hexencode_uuid(self.task_to_compute.subtask_id),
        )

    def test_that_sci_backend_cover_additional_verification_cost_should_return_transaction_hash(self):
        with mock.patch(
            'core.payments.payment_interface.PaymentInterface.__new__',
            return_value=mock.Mock(
                cover_additional_verification_cost=mock.Mock(
                    return_value=MOCK_TRANSACTION_HASH
                ),
            ),
        ) as new_sci_rpc:
            transaction_hash = sci_backend.cover_additional_verification_cost(
                self.task_to_compute.provider_ethereum_address,
                self.transaction_value,
                self.task_to_compute.subtask_id,
            )

        self.assertEqual(transaction_hash, MOCK_TRANSACTION_HASH)

        new_sci_rpc.return_value.cover_additional_verification_cost.assert_called_with(
            address=Web3.toChecksumAddress(self.task_to_compute.provider_ethereum_address),
            value=self.transaction_value,
            subtask_id=sci_backend._hexencode_uuid(self.task_to_compute.subtask_id),
        )
