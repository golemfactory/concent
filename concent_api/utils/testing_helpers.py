import os
import random
import string
from golem_messages import ECCx
from core.constants import CLIENT_DETAILS_LENGTH


def generate_ecc_key_pair():
    ecc = ECCx(None)
    return (ecc.raw_privkey, ecc.raw_pubkey)


def generate_priv_and_pub_eth_account_key():
    client_eth_priv_key = os.urandom(32)
    client_eth_pub_key = generate_random_string(CLIENT_DETAILS_LENGTH)
    return (client_eth_priv_key, client_eth_pub_key)


def generate_random_string(length):
    return ''.join(random.choice(string.ascii_letters) for x in range(length))
