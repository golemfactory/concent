import time
from typing import Callable

from pathlib import Path
import requests
from tempfile import mkdtemp

from eth_utils import to_checksum_address
from ethereum.utils import privtoaddr

from golem_messages.cryptography import ECCx
from golem_messages.utils import encode_hex
from golem_sci import contracts
from golem_sci import JsonTransactionsStorage
from golem_sci import new_sci_rpc
from golem_sci import SmartContractsInterface
from golem_sci.chains import RINKEBY


class ValueNotPositiveError(Exception):
    pass

class NotEnoughFoundsError(Exception):
    pass

class ResponseDonateFaucetError(Exception):
    pass


class SCIBaseTest():
    @staticmethod
    def _generate_keys() -> ECCx:
        return ECCx(None)

    def __init__(self, cluster_type: str) -> None:
        super().__init__()
        self.setUp(cluster_type)
        self.request_for_gntb()
        self.request_for_deposit()

    def setUp(self, cluster_type: str) -> None:
        self.provider_keys = self._generate_keys()
        self.requestor_keys = self._generate_keys()
        self.provider_empty_account_keys = self._generate_keys()
        self.requestor_empty_account_keys = self._generate_keys()
        self.CLUSTER_GNT_DEPOSIT_CONTRACT_ADDRESSES = {
            'devel': '0xcfB81A6EE3ae6aD4Ac59ddD21fB4589055c13DaD',
            'staging': '0xA172A4B929Ae9589E3228F723CB99508b8c0709a',
            'testnet': '0x694667D7787CFca1892606E81734860a617537B2',
        }
        self.geth_rinkeby_address = 'https://rinkeby.golem.network:55555'
        CONTRACT_ADDRESSES = {
            contracts.GNT: '0x924442A66cFd812308791872C4B242440c108E19',
            contracts.GNTB: '0x123438d379BAbD07134d1d4d7dFa0BCbd56ca3F3',
            contracts.GNTDeposit: self.CLUSTER_GNT_DEPOSIT_CONTRACT_ADDRESSES[cluster_type],
            contracts.Faucet: '0x77b6145E853dfA80E8755a4e824c4F510ac6692e',
        }
        requestor_storage = JsonTransactionsStorage(
            Path(mkdtemp()) / 'requestor_tx.json')
        provider_storage = JsonTransactionsStorage(
            Path(mkdtemp()) / 'provider_tx.json')

        self.requestor_sci = new_sci_rpc(
            rpc=self.geth_rinkeby_address,
            storage=requestor_storage,
            address=self.requestor_eth_address,
            tx_sign=lambda tx: tx.sign(self.requestor_private_key),
            contract_addresses=CONTRACT_ADDRESSES,
            chain=RINKEBY
        )

        self.provider_sci = new_sci_rpc(
            rpc=self.geth_rinkeby_address,
            storage=provider_storage,
            address=self.provider_eth_address,
            tx_sign=lambda tx: tx.sign(self.provider_private_key),
            contract_addresses=CONTRACT_ADDRESSES,
            chain=RINKEBY
        )
        self.sleep_time = 5
        self.timeout = 300

    @staticmethod
    def _test_eth_faucet_donate(eth_account_address: str) -> None:
        request_address = f"http://188.165.227.180:4000/donate/{eth_account_address}"
        response = requests.get(request_address)
        if response.status_code != 200:
            raise ResponseDonateFaucetError(f"Actual response is {response.status_code}. "
                                            f"Test Eth has not been transferred")
        else:
            print("Test Eth has been transferred")

    @staticmethod
    def _test_gnt_faucet(sci: SmartContractsInterface) -> None:
        sci.request_gnt_from_faucet()
        sci.open_gate()

    @staticmethod
    def _test_gnt_to_gntb_transfer(sci: SmartContractsInterface) -> None:
        sci.transfer_gnt(
            sci.get_gate_address(),
            sci.get_gnt_balance(sci.get_eth_address())
        )
        sci.transfer_from_gate()


    def _wait_unitl_timeout(self, condition: Callable, timeout_message: str, sleep_message: str) -> None:

        start = time.time()

        while condition():
            print(sleep_message)
            time.sleep(self.sleep_time)
            if start + self.timeout < time.time():
                raise TimeoutError(timeout_message)
        else:
            print(f'Sleep lasted for {int(time.time() - start)} seconds')


    def request_for_gntb(self) -> None:
        self._test_eth_faucet_donate(self.requestor_sci.get_eth_address())
        self._test_eth_faucet_donate(self.provider_sci.get_eth_address())

        self._wait_unitl_timeout(
            condition=lambda : (
                self.requestor_sci.get_eth_balance(self.requestor_sci.get_eth_address()) == 0 or
                self.provider_sci.get_eth_balance(self.provider_sci.get_eth_address()) == 0
            ),
            timeout_message='Test ETH faucet timeout',
            sleep_message='Waiting for test ETH for Provider and Requestor...',
        )

        self._test_gnt_faucet(self.requestor_sci)
        self._test_gnt_faucet(self.provider_sci)

        self._wait_unitl_timeout(
            condition=lambda : (
                self.requestor_sci.get_gnt_balance(self.requestor_sci.get_eth_address()) == 0 or
                self.provider_sci.get_gnt_balance(self.provider_sci.get_eth_address()) == 0 or
                self.requestor_sci.get_gate_address() is None or
                self.provider_sci.get_gate_address() is None
            ),
            timeout_message='Test GNT faucet timeout',
            sleep_message='Waiting for test GNT for Provider and Requestor...',
        )

        self._test_gnt_to_gntb_transfer(self.requestor_sci)
        self._test_gnt_to_gntb_transfer(self.provider_sci)

        self._wait_unitl_timeout(
            condition=lambda : (
                self.requestor_sci.get_gntb_balance(self.requestor_sci.get_eth_address()) == 0 or
                self.provider_sci.get_gntb_balance(self.provider_sci.get_eth_address()) == 0
            ),
            timeout_message='Test GNT to GNTB transfer timeout',
            sleep_message='Waiting for test GNTB for Provider and Requestor...',
        )

    def request_for_deposit(self, value: int=0):
        if value < 0:
            raise ValueNotPositiveError('Value must be greater than zero')
        requestor_gntb_balance = self.requestor_sci.get_gntb_balance(self.requestor_sci.get_eth_address())
        provider_gntb_balance = self.provider_sci.get_gntb_balance(self.provider_sci.get_eth_address())
        if requestor_gntb_balance == 0 or value > requestor_gntb_balance:
            raise NotEnoughFoundsError("Not enough GNTB founds on requestor's account")

        if provider_gntb_balance == 0 or value > provider_gntb_balance:
            raise NotEnoughFoundsError("Not enough GNTB founds on provider's account")

        self.requestor_sci.deposit_payment(
            value if value != 0 else requestor_gntb_balance
        )
        self.provider_sci.deposit_payment(
            value if value != 0 else provider_gntb_balance
        )
        self._wait_unitl_timeout(
            condition=lambda: (
                self.requestor_sci.get_deposit_value(self.requestor_sci.get_eth_address()) == 0 or
                self.provider_sci.get_deposit_value(self.provider_sci.get_eth_address()) == 0
            ),
            timeout_message='Test deposit GNTB timeout',
            sleep_message='Waiting for deposited GNTB for Provider and Requestor...',
        )

    def _get_gntb_balance(self, sci: SmartContractsInterface) -> int:
        return sci.get_gntb_balance(sci.get_eth_address())

    def _get_provider_gntb_balance(self) -> int:
        return self._get_gntb_balance(self.provider_sci)

    def _get_requestor_gntb_balance(self) -> int:
        return self._get_gntb_balance(self.requestor_sci)

    def check_that_provider_received_gntb_from_requestor(self, value):
        import ipdb; ipdb.set_trace()
        self._wait_unitl_timeout(
            condition=lambda: (
                    self.provider_sci.get_gntb_balance(self.provider_sci.get_eth_address()) != value
            ),
            timeout_message=f'Provider does not receive {value} GNTB from requestor',
            sleep_message='Waiting for GNTB from last trasaction beetwen Provider and Requestor',
        )

    @property
    def provider_public_key(self) -> bytes:
        return self.provider_keys.raw_pubkey

    @property
    def provider_private_key(self) -> bytes:
        return self.provider_keys.raw_privkey

    @property
    def provider_eth_address(self) -> str:
        return to_checksum_address(encode_hex(privtoaddr(self.provider_keys.raw_privkey)))

    @property
    def requestor_public_key(self) -> bytes:
        return self.requestor_keys.raw_pubkey

    @property
    def requestor_private_key(self) -> bytes:
        return self.requestor_keys.raw_privkey

    @property
    def requestor_eth_address(self) -> str:
        return to_checksum_address(encode_hex(privtoaddr(self.requestor_keys.raw_privkey)))

    @property
    def provider_empty_account_public_key(self) -> bytes:
        return self.provider_empty_account_keys.raw_pubkey

    @property
    def provider_empty_account_private_key(self) -> bytes:
        return self.provider_empty_account_keys.raw_privkey

    @property
    def provider_empty_account_eth_address(self) -> str:
        return to_checksum_address(encode_hex(privtoaddr(self.provider_empty_account_keys.raw_privkey)))

    @property
    def requestor_empty_account_public_key(self) -> bytes:
        return self.requestor_empty_account_keys.raw_pubkey

    @property
    def requestor_empty_account_private_key(self) -> bytes:
        return self.requestor_empty_account_keys.raw_privkey

    @property
    def requestor_empty_account_eth_address(self) -> str:
        return to_checksum_address(encode_hex(privtoaddr(self.requestor_empty_account_keys.raw_privkey)))
