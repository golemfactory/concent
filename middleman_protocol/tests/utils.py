import assertpy
from golem_messages import ECCx


def assertpy_bytes_starts_with(data: bytes, starting_data: bytes):
    """
    Custom function which allows testing if given bytes start with other bytes using assertpy.
    """

    assert isinstance(data, bytes)
    assert isinstance(starting_data, bytes)

    assertpy.assert_that(
        str(data)[2:-1]
    ).starts_with(
        str(starting_data)[2:-1]
    )


def generate_ecc_key_pair():
    ecc = ECCx(None)
    return (ecc.raw_privkey, ecc.raw_pubkey)
