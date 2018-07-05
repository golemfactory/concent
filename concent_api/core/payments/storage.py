import logging
from typing import Dict
from typing import List
from hexbytes import HexBytes
from ethereum.transactions import Transaction
from golem_sci.transactionsstorage import TransactionsStorage

from django.db import transaction

from core.exceptions import TransactionNonceMismatch
from common.singleton import ConcentRPC
from core.models import GlobalTransactionState
from core.models import PendingEthereumTransaction

logger = logging.getLogger(__name__)


class DatabaseTransactionsStorage(TransactionsStorage):
    """
    Concent custom implementation of TransactionsStorage interface used to store Ethereum transaction data into
    database using Django models.
    """

    def __init__(self, *args: List, **kwargs: Dict) -> None:
        super().__init__(*args, **kwargs)

        assert isinstance(nonce, int)
        if not GlobalTransactionState.objects.filter(pk=0).exists():
            concent_rpc = ConcentRPC()
            global_transaction_state = GlobalTransactionState(
                pk=0,
                nonce=concent_rpc.get_transaction_count(),  # TODO: Get it via backend
            )
            global_transaction_state.full_clean()
            global_transaction_state.save()

    @transaction.atomic(using='control')
    def get_nonce(self) -> int:
        """
        Returns the nonce for the next transaction.
        """
        global_transaction_state = self._get_locked_global_transaction_state()
        return int(global_transaction_state.nonce)

    @transaction.atomic(using='control')  # pylint: disable=no-self-use
    def get_all_tx(self) -> List[Transaction]:
        """
        Returns the list of all transactions.
        """
        return [
            Transaction(
                nonce=int(ethereum_transaction.nonce),
                gasprice=int(ethereum_transaction.gasprice),
                startgas=int(ethereum_transaction.startgas),
                value=int(ethereum_transaction.value),
                v=ethereum_transaction.v,
                r=int(ethereum_transaction.r),
                s=int(ethereum_transaction.s),
                data=ethereum_transaction.data.tobytes(),
                to=HexBytes(ethereum_transaction.to.tobytes()).hex(),
            )
            for ethereum_transaction in PendingEthereumTransaction.objects.all()
        ]

    @transaction.atomic(using='control')
    def put_tx_and_inc_nonce(self, tx: Transaction) -> None:
        """
        Save a valid transaction and increase the nonce.
        """
        global_transaction_state = self._get_locked_global_transaction_state()

        if int(global_transaction_state.nonce) != tx.nonce:
            raise TransactionNonceMismatch(
                f'Transaction nonce does not match. '
                f'Current={global_transaction_state.nonce}, '
                f'Transaction={tx.nonce}',
            )

        pending_ethereum_transaction = PendingEthereumTransaction(
            nonce=tx.nonce,
            gasprice=tx.gasprice,
            startgas=tx.startgas,
            value=tx.value,
            v=tx.v,
            r=tx.r,
            s=tx.s,
            data=tx.data,
            to=tx.to,
        )
        pending_ethereum_transaction.full_clean()
        pending_ethereum_transaction.save()

        global_transaction_state.nonce += 1
        global_transaction_state.full_clean()
        global_transaction_state.save()

    @transaction.atomic(using='control')
    def remove_tx(self, nonce: int) -> None:
        """
        Remove the transaction after it's been confirmed and doesn't have
        to be tracked anymore.
        """
        assert isinstance(nonce, int)
        # This is called here only to lock GlobalTransactionState
        self._get_locked_global_transaction_state()

        try:
            pending_ethereum_transaction = PendingEthereumTransaction.objects.get(nonce=nonce)
            pending_ethereum_transaction.delete()
            logger.info(f'Successfully removed PendingEthereumTransaction with nonce {nonce}.')
        except PendingEthereumTransaction.DoesNotExist:
            logger.error(f'Trying to remove PendingEthereumTransaction with nonce {nonce} but it does not exist.')
            raise

    @transaction.atomic(using='control')
    def revert_last_tx(self) -> None:
        """
        Remove the last transaction that was added.
        This shouldn't be ever called if everything is being used correctly,
        i.e. we don't try to send invalid transactions.
        """
        global_transaction_state = self._get_locked_global_transaction_state()

        try:
            pending_ethereum_transaction = PendingEthereumTransaction.objects.get(
                nonce=global_transaction_state.nonce - 1
            )
            pending_ethereum_transaction.delete()

            global_transaction_state.nonce -= 1
            global_transaction_state.full_clean()
            global_transaction_state.save()

            logger.info(
                f'Successfully reverted last PendingEthereumTransaction with nonce {pending_ethereum_transaction.nonce}.'
            )
        except GlobalTransactionState.DoesNotExist:
            logger.error(
                f'Trying to revert last PendingEthereumTransaction with nonce {global_transaction_state.nonce - 1} but it does not exist.'
            )
            raise

    @staticmethod
    def _get_locked_global_transaction_state() -> GlobalTransactionState:
        try:
            return GlobalTransactionState.objects.select_for_update().get(
                pk=0,
            )
        except GlobalTransactionState.DoesNotExist:
            logger.error(f'Trying to get GlobalTransactionState but it does not exist.')
            raise
