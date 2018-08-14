from typing import Any

from django.conf import settings
from web3 import Web3

from golem_sci import chains
from golem_sci import new_sci_rpc
from golem_sci import SmartContractsInterface

from common.helpers import generate_ethereum_address_from_ethereum_public_key
from core.payments.sci_callback import sci_callback
from core.payments.storage import DatabaseTransactionsStorage


class PaymentInterface:
    __instance = None

    def __new__(cls, *args: Any, **kwargs: Any) -> SmartContractsInterface:  # pylint: disable=unused-argument
        if cls.__instance is None:
            cls.__instance = new_sci_rpc(
                rpc=settings.GETH_ADDRESS,
                address=Web3.toChecksumAddress(
                    generate_ethereum_address_from_ethereum_public_key(
                        settings.CONCENT_ETHEREUM_PUBLIC_KEY
                    )
                ),
                chain=chains.RINKEBY,
                storage=DatabaseTransactionsStorage(),
                tx_sign=sci_callback,
            )
        return cls.__instance
