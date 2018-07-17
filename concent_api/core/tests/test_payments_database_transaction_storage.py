import os

from django.test import TestCase
from ethereum.transactions import Transaction

from core.models import GlobalTransactionState
from core.models import PendingEthereumTransaction
from core.payments.storage import DatabaseTransactionsStorage


def _sign(tx: Transaction) -> None:
    tx.sign(os.urandom(32))


class DatabaseTransactionsStorageTest(TestCase):

    multi_db = True

    def setUp(self):
        super().setUp()

        self.initial_nonce = 5
        self.increased_nonce = 10
        self.storage = DatabaseTransactionsStorage()
        self.storage.init(self.initial_nonce)

        self.global_transaction_state = GlobalTransactionState.objects.get(pk=0)

    def _create_pending_ethereum_transaction(self):
        pending_ethereum_transaction = PendingEthereumTransaction(
            nonce=int(self.global_transaction_state.nonce),
            gasprice=10 ** 6,
            startgas=80000,
            to=b'7917bc33eea648809c28',
            value=10,
            v=1,
            r=11,
            s=12,
            data=b'3078666333323333396130303030303030303030303030303030303030303030303032393662363963383738613734393865663463343531363436353231336564663834666334623330303030303030303030303030303030303030303030303030333431336437363161356332633362656130373531373064333239363566636161386261303533633030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303237313030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303562343336643666',
        )
        pending_ethereum_transaction.full_clean()
        pending_ethereum_transaction.save()

        self.global_transaction_state.nonce += 1
        self.global_transaction_state.full_clean()
        self.global_transaction_state.save()

        return pending_ethereum_transaction

    def _create_transaction(self):
        return Transaction(
            nonce=int(self.global_transaction_state.nonce),
            gasprice=10 ** 6,
            startgas=80000,
            value=10,
            to=b'7917bc33eea648809c28',
            v=28,
            r=105276041803796697890139158600495981346175539693000174052040367753737207356915,
            s=51455402244652678469360859593599492752947853083356495769067973718806366068077,
            data=b'3078666333323333396130303030303030303030303030303030303030303030303032393662363963383738613734393865663463343531363436353231336564663834666334623330303030303030303030303030303030303030303030303030333431336437363161356332633362656130373531373064333239363566636161386261303533633030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303237313030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303562343336643666',
        )

    def test_that_initial_nonce_should_be_retreived_from_rpc(self):
        nonce = self.storage._get_nonce()

        self.assertEqual(nonce, self.initial_nonce)
        self.assertEqual(GlobalTransactionState.objects.count(), 1)

        global_transaction_state = GlobalTransactionState.objects.first()
        self.assertEqual(global_transaction_state.pk, 0)
        self.assertEqual(global_transaction_state.nonce, self.initial_nonce)

    def test_that_if_global_transaction_state_exists_nonce_should_be_retreived_from_it(self):
        nonce = self.storage._get_nonce()

        self.assertEqual(nonce, self.global_transaction_state.nonce)
        self.assertEqual(GlobalTransactionState.objects.count(), 1)

    def test_that_get_all_tx_should_return_list_of_all_transactions(self):
        self._create_pending_ethereum_transaction()
        self._create_pending_ethereum_transaction()

        all_transactions = self.storage.get_all_tx()

        self.assertEqual(len(all_transactions), 2)
        for transaction in all_transactions:
            self.assertIsInstance(transaction, Transaction)

    def test_that_set_nonce_sign_and_save_tx_should_accept_transaction_and_increase_nonce(self):
        current_nonce = self.global_transaction_state.nonce
        transaction = self._create_transaction()

        self.storage.set_nonce_sign_and_save_tx(
            _sign,
            transaction
        )

        self.assertEqual(PendingEthereumTransaction.objects.count(), 1)

        pending_transaction_1 = PendingEthereumTransaction.objects.first()
        self.assertEqual(pending_transaction_1.nonce, current_nonce)

        self.global_transaction_state.refresh_from_db()
        self.assertEqual(self.global_transaction_state.nonce, current_nonce + 1)

    def test_that_set_nonce_sign_and_save_tx_should_fail_if_global_transaction_state_does_not_exist(self):
        transaction = self._create_transaction()
        self.global_transaction_state.delete()

        with self.assertRaises(GlobalTransactionState.DoesNotExist):
            self.storage.set_nonce_sign_and_save_tx(
                _sign,
                transaction
            )

        self.assertEqual(PendingEthereumTransaction.objects.count(), 0)

    def test_that_set_nonce_sign_and_save_tx_should_create_new_transaction_with_correct_nonce_if_nonce_does_not_match(self):
        transaction = self._create_transaction()
        self.global_transaction_state.nonce += 1
        self.global_transaction_state.full_clean()
        self.global_transaction_state.save()
        current_nonce = self.global_transaction_state.nonce

        self.storage.set_nonce_sign_and_save_tx(
            _sign,
            transaction
        )

        self.assertEqual(PendingEthereumTransaction.objects.count(), 1)
        self.global_transaction_state.refresh_from_db()
        self.assertEqual(self.global_transaction_state.nonce, current_nonce + 1)

    def test_that_put_tx_first_and_then_get_all_tx_returns_exactly_same_transaction_object(self):
        transaction = self._create_transaction()

        self.storage.set_nonce_sign_and_save_tx(
            _sign,
            transaction
        )

        all_transactions = self.storage.get_all_tx()

        self.assertEqual(len(all_transactions), 1)
        for field, _ in transaction.fields:
            self.assertEqual(
                getattr(transaction, field),
                getattr(all_transactions[0], field)
            )

    def test_that_remove_tx_should_remove_transaction_with_given_nonce(self):
        pending_transaction_1 = self._create_pending_ethereum_transaction()
        pending_transaction_2 = self._create_pending_ethereum_transaction()

        assert pending_transaction_2.nonce == self.global_transaction_state.nonce - 1

        self.storage.remove_tx(int(pending_transaction_1.nonce))

        self.assertEqual(PendingEthereumTransaction.objects.count(), 1)
        self.assertFalse(PendingEthereumTransaction.objects.filter(nonce=pending_transaction_1.nonce).exists())
        self.assertTrue(PendingEthereumTransaction.objects.filter(nonce=pending_transaction_2.nonce).exists())

    def test_that_remove_tx_should_fail_when_removing_transaction_with_nonce_that_does_not_exist(self):
        self._create_pending_ethereum_transaction()
        self._create_pending_ethereum_transaction()

        with self.assertRaises(PendingEthereumTransaction.DoesNotExist):
            self.storage.remove_tx(int(self.global_transaction_state.nonce))

        self.assertEqual(PendingEthereumTransaction.objects.count(), 2)

    def test_that_revert_last_tx_should_remove_last_transaction(self):
        pending_transaction_1 = self._create_pending_ethereum_transaction()
        pending_transaction_2 = self._create_pending_ethereum_transaction()
        current_nonce = self.global_transaction_state.nonce

        self.storage.revert_last_tx()

        self.assertEqual(PendingEthereumTransaction.objects.count(), 1)
        self.assertTrue(PendingEthereumTransaction.objects.filter(nonce=pending_transaction_1.nonce).exists())
        self.assertFalse(PendingEthereumTransaction.objects.filter(nonce=pending_transaction_2.nonce).exists())

        self.global_transaction_state.refresh_from_db()
        self.assertEqual(self.global_transaction_state.nonce, current_nonce - 1)

    def test_that_revert_last_tx_should_fail_when_reverting_transaction_with_nonce_that_does_not_exist(self):
        self._create_pending_ethereum_transaction()
        pending_transaction_2 = self._create_pending_ethereum_transaction()
        current_nonce = self.global_transaction_state.nonce

        assert pending_transaction_2.nonce == current_nonce - 1

        self.global_transaction_state.nonce += 1
        self.global_transaction_state.full_clean()
        self.global_transaction_state.save()

        with self.assertRaises(PendingEthereumTransaction.DoesNotExist):
            self.storage.revert_last_tx()

        self.assertEqual(PendingEthereumTransaction.objects.count(), 2)

        self.global_transaction_state.refresh_from_db()
        self.assertEqual(self.global_transaction_state.nonce, current_nonce + 1)

    def test_that_revert_last_tx_should_fail_if_global_transaction_state_does_not_exist(self):
        self._create_pending_ethereum_transaction()
        pending_transaction_2 = self._create_pending_ethereum_transaction()
        current_nonce = self.global_transaction_state.nonce

        assert pending_transaction_2.nonce == current_nonce - 1

        self.global_transaction_state.delete()

        with self.assertRaises(GlobalTransactionState.DoesNotExist):
            self.storage.revert_last_tx()

        self.assertEqual(PendingEthereumTransaction.objects.count(), 2)

    def test_that_maximum_values_works_correctly_with_pending_ethereum_transaction_database_model(self):
        pending_ethereum_transaction = PendingEthereumTransaction(
            nonce=self.global_transaction_state.nonce,
            gasprice=(2 ** 256 - 1),
            startgas=(2 ** 256 - 1),
            to=b'x' * 20,
            value=(2 ** 256 - 1),
            v=(2 ** 8 - 1),
            r=(2 ** 256 - 1),
            s=(2 ** 256 - 1),
            data=b'3078666333323333396130303030303030303030303030303030303030303030303032393662363963383738613734393865663463343531363436353231336564663834666334623330303030303030303030303030303030303030303030303030333431336437363161356332633362656130373531373064333239363566636161386261303533633030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303237313030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303562343336643666',
        )
        pending_ethereum_transaction.full_clean()
        pending_ethereum_transaction.save()

        pending_ethereum_transaction_from_database = PendingEthereumTransaction.objects.filter(nonce=int(self.global_transaction_state.nonce)).first()

        self.assertEqual(pending_ethereum_transaction_from_database, pending_ethereum_transaction)

    def test_that_function_is_storage_initialized_return_true_if_storage_is_initialized(self):
        self.assertEqual(self.storage._is_storage_initialized(), True)

    def test_that_function_is_storage_initialized_return_false_if_storage_is_not_initialized(self):
        GlobalTransactionState.objects.all().delete()
        assert GlobalTransactionState.objects.all().count() == 0

        not_initialzied_storage = DatabaseTransactionsStorage()
        self.assertEqual(not_initialzied_storage._is_storage_initialized(), False)

    def test_that_init_with_nonce_function_works_properly(self):
        GlobalTransactionState.objects.all().delete()
        assert GlobalTransactionState.objects.all().count() == 0

        self.storage._init_with_nonce(self.increased_nonce)
        self.assertEqual(GlobalTransactionState.objects.get(pk=0).nonce, self.increased_nonce)

    def test_that_storage_init_function_increase_nonce_if_is_lower_than_network_nonce(self):
        assert self.storage._get_nonce() == self.initial_nonce

        self.storage.init(self.increased_nonce)

        self.assertEqual(self.storage._get_nonce(), self.increased_nonce)
