import os
import random
import string
from golem_messages import ECCx
from golem_messages.cryptography import privtopub


def generate_ecc_key_pair() -> tuple:
    ecc = ECCx(None)
    return (ecc.raw_privkey, ecc.raw_pubkey)


def generate_priv_and_pub_eth_account_key() -> tuple:
    client_eth_priv_key = os.urandom(32)
    client_eth_pub_key = privtopub(client_eth_priv_key)
    return (client_eth_priv_key, client_eth_pub_key)


def generate_random_string(length: int) -> str:
    return ''.join(random.choice(string.ascii_letters) for x in range(length))
