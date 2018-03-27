from django.conf    import settings

from golem_messages import message
from golem_messages import cryptography


def load_without_public_key(data, _privkey = None, _pubkey = None, _check_time = True):
    """ Does the same `load` from golem_messages.shortcuts, but doesn't require public key. """

    def verify(_msg_hash, _signature):
        return True

    def decrypt(payload):
        if not settings.CONCENT_PRIVATE_KEY:
            return payload
        ecc = cryptography.ECCx(settings.CONCENT_PRIVATE_KEY)
        return ecc.decrypt(payload)

    return message.base.Message.deserialize(data, decrypt, True, verify)
