from typing import Any

from django.conf import settings
from web3 import Web3

from golem_sci import new_sci_rpc
from golem_sci.contracts import Contract
from golem_sci.implementation import SCIImplementation

from common.helpers import generate_ethereum_address_from_ethereum_public_key
from core.payments.sci_callback import sci_callback
from core.payments.storage import DatabaseTransactionsStorage


class PaymentInterface:
    __instance = None

    def __new__(cls, *args: Any, **kwargs: Any) -> SCIImplementation:  # pylint: disable=unused-argument
        if cls.__instance is None:
            cls.__instance = new_sci_rpc(
                rpc=settings.GETH_ADDRESS,
                address=Web3.toChecksumAddress(
                    generate_ethereum_address_from_ethereum_public_key(
                        settings.CONCENT_ETHEREUM_PUBLIC_KEY
                    )
                ),
                chain=settings.ETHEREUM_CHAIN,
                storage=DatabaseTransactionsStorage(),
                tx_sign=(
                    sci_callback if settings.USE_SIGNING_SERVICE else
                    lambda tx: tx.sign(settings.CONCENT_ETHEREUM_PRIVATE_KEY)
                ),
                contract_addresses={
                    Contract.GNT: '0x924442A66cFd812308791872C4B242440c108E19',
                    Contract.GNTB: '0x123438d379BAbD07134d1d4d7dFa0BCbd56ca3F3',
                    Contract.GNTDeposit: settings.GNT_DEPOSIT_CONTRACT_ADDRESS,
                    Contract.Faucet: '0x77b6145E853dfA80E8755a4e824c4F510ac6692e',
                }
            )
        return cls.__instance
