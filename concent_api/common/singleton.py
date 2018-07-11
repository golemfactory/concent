from typing import Callable
from django.conf        import settings
from ethereum.transactions import Transaction
from golem_sci.client import Client
from golem_sci.contracts.provider import ContractDataProvider
from golem_sci.implementation import SCIImplementation
from golem_sci.transactionsstorage import TransactionsStorage

from web3 import HTTPProvider
from web3 import Web3
from web3.middleware import geth_poa_middleware

from core.payments.storage import DatabaseTransactionsStorage


#  Original code come from golemfactory/golem-smart-contracts-interface
#  Temporary SCI factory for Concent needs.
#  Gets storage as a parameter
def concent_sci(
    storage: TransactionsStorage,
    web3: Web3,
    address: Web3,
    tx_sign: Callable[[Transaction], None],
) -> SCIImplementation:
    assert issubclass(storage, TransactionsStorage)
    if geth_poa_middleware not in web3.middleware_stack:
        web3.middleware_stack.inject(geth_poa_middleware, layer=0)
    provider = ContractDataProvider('rinkeby')
    geth_client = Client(web3)
    nonce = geth_client.get_transaction_count(address)
    return SCIImplementation(
        geth_client,
        address,
        storage(nonce),
        provider,
        tx_sign,
    )


class ConcentRPC:
    __instance = None

    def __new__(cls, *args, **kwargs):  # pylint: disable=unused-argument
        if cls.__instance is None:
            cls.__instance = concent_sci(
                DatabaseTransactionsStorage,
                Web3(HTTPProvider(settings.GETH_ADDRESS)),
                Web3.toChecksumAddress(settings.CONCENT_ETHEREUM_ADDRESS),
                lambda tx: tx.sign(settings.CONCENT_ETHEREUM_PRIVATE_KEY)
            )
        return cls.__instance
