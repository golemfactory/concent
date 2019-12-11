import time
from collections import namedtuple
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


CLUSTER_GNT_DEPOSIT_CONTRACT_ADDRESSES = {
    'devel': '0x10ef3a07ea272E024cC0a66eCAe1Ba81eb3f5794',
    'staging': '0x884443710CDe8Bb56D10E81059513fb1c4Bf32A3',
    'test': '0x74751ae0b80276dB6b9310b7F8F79fe044205b83',
}

GETH_RINKEBY_ADDRESS = 'https://rinkeby.golem.network:55555'

CONTRACT_ADDRESSES = {
    contracts.GNT: '0x924442A66cFd812308791872C4B242440c108E19',
    contracts.GNTB: '0x123438d379BAbD07134d1d4d7dFa0BCbd56ca3F3',
    contracts.GNTDeposit: '',
    contracts.Faucet: '0x77b6145E853dfA80E8755a4e824c4F510ac6692e',
}

ETH_DONATE_ADDRESS = 'http://188.165.227.180:4000/donate/'

REQUESTOR_ETHEREUM_PRIVATE_KEY = b'}\xf3\xfc\x16ZUoM{h\xa9\xee\xfe_8\xbd\x02\x95\xc3\x8am\xd7\xff\x91R"\x1d\xb71\xed\x08\t'
REQUESTOR_ETHEREUM_PUBLIC_KEY = b'F\xdei\xa1\xc0\x10\xc8M\xce\xaf\xc0p\r\x8e\x8f\xb1` \x8d\xf7=\xa6\xb6\xbazL\xbbY\xd6:\xd5\x06\x8dP\xe7#\xb9\xbb\xf8T\xc73\xebH\x7f2\xcav\xb1\xd8w\xde\xdb\x89\xf0\xddD\xa5\xbf\x030\xf3\x96;'
PROVIDER_ETHEREUM_PRIVATE_KEY = b'\x1dJ\xaf_h\xe0Y#;p\xd7s>\xb4fOH\x19\xbc\x9e\xd1\xf4\t\xdf]!\x9c\xfe\x9f\x888x'
PROVIDER_ETHEREUM_PUBLIC_KEY = b'\x05\xa7w\xc6\x9b\x89<\xf8Rz\xef\xc4AwN}\xa0\x0e{p\xc8\xa7AF\xfc\xd26\xc1)\xdbgp\x8b]9\xfd\xaa]\xd5H@?F\x14\xdbU\x8b\x93\x8d\xf1\xfc{s3\x8c\xc7\x80-,\x9d\x194u\x8d'


class ValueNotGreatenThanZeroError(Exception):
    pass


class NotEnoughFoundsError(Exception):
    pass


class ResponseDonateFaucetError(Exception):
    pass


class SCIBaseTest():
    @staticmethod
    def _generate_keys() -> ECCx:
        return ECCx(None)

    def __init__(self, cluster_address: str, init_new_users_accounts: bool=False) -> None:
        self.setUp(self.get_gnt_deposit_address_from_cluster_address(cluster_address), init_new_users_accounts)
        if init_new_users_accounts:
            self.request_for_gntb()
            self.request_for_deposit()

    def setUp(self, gnt_deposit_address: str, init_new_users_accounts: bool) -> None:
        if init_new_users_accounts:
            self.provider_keys = self._generate_keys()
            self.requestor_keys = self._generate_keys()
        else:
            ClientKeys = namedtuple('ClientKeys', ['raw_privkey', 'raw_pubkey'])
            self.provider_keys = ClientKeys(raw_privkey=PROVIDER_ETHEREUM_PRIVATE_KEY, raw_pubkey=PROVIDER_ETHEREUM_PUBLIC_KEY)
            self.requestor_keys = ClientKeys(raw_privkey=REQUESTOR_ETHEREUM_PRIVATE_KEY, raw_pubkey=REQUESTOR_ETHEREUM_PUBLIC_KEY)
        self.provider_empty_account_keys = self._generate_keys()
        self.requestor_empty_account_keys = self._generate_keys()
        CONTRACT_ADDRESSES[contracts.GNTDeposit] = gnt_deposit_address
        requestor_storage = JsonTransactionsStorage(Path(mkdtemp()) / 'requestor_tx.json')
        provider_storage = JsonTransactionsStorage(Path(mkdtemp()) / 'provider_tx.json')

        self.requestor_sci = new_sci_rpc(
            rpc=GETH_RINKEBY_ADDRESS,
            storage=requestor_storage,
            address=self.requestor_eth_address,
            tx_sign=lambda tx: tx.sign(self.requestor_private_key),
            contract_addresses=CONTRACT_ADDRESSES,
            chain=RINKEBY
        )

        self.provider_sci = new_sci_rpc(
            rpc=GETH_RINKEBY_ADDRESS,
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
        request_address = f"{ETH_DONATE_ADDRESS}{eth_account_address}"
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
            print(f'Sleep lasted for {int(time.time() - start)} seconds. Transaction confirmed.')

    def request_for_gntb(self) -> None:
        self._test_eth_faucet_donate(self.requestor_sci.get_eth_address())
        self._test_eth_faucet_donate(self.provider_sci.get_eth_address())

        self._wait_unitl_timeout(
            condition=lambda: (
                self.requestor_sci.get_eth_balance(self.requestor_sci.get_eth_address()) == 0 or
                self.provider_sci.get_eth_balance(self.provider_sci.get_eth_address()) == 0
            ),
            timeout_message='Test ETH faucet timeout',
            sleep_message='Waiting for test ETH for Provider and Requestor...',
        )

        self._test_gnt_faucet(self.requestor_sci)
        self._test_gnt_faucet(self.provider_sci)

        self._wait_unitl_timeout(
            condition=lambda: (
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
            condition=lambda: (
                self.requestor_sci.get_gntb_balance(self.requestor_sci.get_eth_address()) == 0 or
                self.provider_sci.get_gntb_balance(self.provider_sci.get_eth_address()) == 0
            ),
            timeout_message='Test GNT to GNTB transfer timeout',
            sleep_message='Waiting for test GNTB for Provider and Requestor...',
        )

    def request_for_deposit(self, value: int=0) -> None:
        if value < 0:
            raise ValueNotGreatenThanZeroError('Value must be greater than zero')
        requestor_gntb_balance = self.requestor_sci.get_gntb_balance(self.requestor_sci.get_eth_address())
        provider_gntb_balance = self.provider_sci.get_gntb_balance(self.provider_sci.get_eth_address())
        if requestor_gntb_balance == 0 or requestor_gntb_balance < value:
            raise NotEnoughFoundsError("Not enough GNTB founds on requestor's account")

        if provider_gntb_balance == 0 or provider_gntb_balance < value:
            raise NotEnoughFoundsError("Not enough GNTB founds on provider's account")

        self.requestor_sci.deposit_payment(
            value if value != 0 else requestor_gntb_balance
        )
        self.provider_sci.deposit_payment(
            value if value != 0 else provider_gntb_balance
        )
        self._wait_unitl_timeout(
            condition=lambda: (self.get_requestor_deposit_value() == 0 or self.get_provider_deposit_value() == 0),
            timeout_message='Test deposit GNTB timeout',
            sleep_message='Waiting for deposited GNTB for Provider and Requestor...',
        )

    def _get_gntb_balance(self, sci: SmartContractsInterface) -> int:
        return sci.get_gntb_balance(sci.get_eth_address())

    def get_provider_gntb_balance(self) -> int:
        return self._get_gntb_balance(self.provider_sci)

    def get_requestor_deposit_value(self) -> int:
        return self.requestor_sci.get_deposit_value(self.requestor_sci.get_eth_address())

    def get_provider_deposit_value(self) -> int:
        return self.provider_sci.get_deposit_value(self.provider_sci.get_eth_address())

    def ensure_that_provider_has_specific_gntb_balance(self, value: int) -> None:
        self._wait_unitl_timeout(
            condition=lambda: (self.get_provider_gntb_balance() != value),
            timeout_message=f'Provider gntb balance is different than expected',
            sleep_message=f'Provider current gntb balance: {self.get_provider_gntb_balance()}. Waiting for {value}',
        )

    def ensure_that_requestor_has_specific_deposit_balance(self, value: int) -> None:
        self._wait_unitl_timeout(
            condition=lambda: (self.get_requestor_deposit_value() != value),
            timeout_message=f'Requestor gntb deposit balance is different than expected',
            sleep_message=f'Requestor current gntb deposit balance: {self.get_requestor_deposit_value()}. Waiting for {value}',
        )

    def get_gnt_deposit_address_from_cluster_address(self, address: str) -> str:
        cluster_name = address.split('.')[0]
        if cluster_name.startswith('http'):
            cluster_name = cluster_name.split('//')[1]
        # If staging or testnet cluster will be tested then it should return 'staging' or 'test'
        # elsewhere it should always return 'devel' because of possibility to test Concent locally
        if cluster_name in CLUSTER_GNT_DEPOSIT_CONTRACT_ADDRESSES.keys():
            return CLUSTER_GNT_DEPOSIT_CONTRACT_ADDRESSES[cluster_name]
        else:
            try:
                from concent_api.settings import GNT_DEPOSIT_CONTRACT_ADDRESS
                assert isinstance(GNT_DEPOSIT_CONTRACT_ADDRESS, str) and len(GNT_DEPOSIT_CONTRACT_ADDRESS) == 42
                return GNT_DEPOSIT_CONTRACT_ADDRESS
            except ImportError:
                return CLUSTER_GNT_DEPOSIT_CONTRACT_ADDRESSES['devel']

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
