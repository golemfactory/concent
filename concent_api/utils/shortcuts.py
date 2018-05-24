from django.conf    import settings

from golem_messages import message
from golem_messages import cryptography

ecies = cryptography.ECIES()


def load_without_public_key(data, client_public_key = None, check_time = True):
    """ Does the same `load` from golem_messages.shortcuts, but doesn't require public key. """

    def decrypt(payload):
        if not settings.CONCENT_PRIVATE_KEY:
            return payload
        return ecies.decrypt(payload, settings.CONCENT_PRIVATE_KEY)

    return message.base.Message.deserialize(data, decrypt, check_time, client_public_key)
