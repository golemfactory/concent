from golem_messages.cryptography import verify_pubkey
from golem_messages.exceptions import InvalidKeys


def is_valid_public_key(key):
    """ Validates if given bytes are valid public key by using function from golem-messages. """

    assert isinstance(key, bytes)

    try:
        verify_pubkey(key)
        return True
    except InvalidKeys:
        return False
