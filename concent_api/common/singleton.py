from django.conf import settings
from web3 import Web3

from golem_sci import chains
from golem_sci import new_sci_rpc

from core.payments.storage import DatabaseTransactionsStorage


class PaymentInterface:
    __instance = None

    def __new__(cls, *args, **kwargs):  # pylint: disable=unused-argument
        if cls.__instance is None:
            cls.__instance = new_sci_rpc(
                rpc=settings.GETH_ADDRESS,
                address=Web3.toChecksumAddress(settings.CONCENT_ETHEREUM_ADDRESS),
                chain=chains.RINKEBY,
                storage=DatabaseTransactionsStorage(),
                tx_sign=lambda tx: tx.sign(settings.CONCENT_ETHEREUM_PRIVATE_KEY),
            )
        return cls.__instance
