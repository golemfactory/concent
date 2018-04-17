from django.conf    import settings

from golem_messages import message
from golem_messages import cryptography


def load_without_public_key(data, client_public_key = None):
    """ Does the same `load` from golem_messages.shortcuts, but doesn't require public key. """

    def decrypt(payload):
        if not settings.CONCENT_PRIVATE_KEY:
            return payload
        ecc = cryptography.ECCx(settings.CONCENT_PRIVATE_KEY)
        return ecc.decrypt(payload)

    return message.base.Message.deserialize(data, decrypt, True, client_public_key)
