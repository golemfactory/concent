from golem_messages  import ECCx


def generate_ecc_key_pair():
    ecc = ECCx(None)
    return (ecc.raw_privkey, ecc.raw_pubkey)
