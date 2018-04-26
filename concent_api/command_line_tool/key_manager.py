from utils.testing_helpers import generate_ecc_key_pair
from django.conf import settings


REQUESTOR_PRIVATE_KEY = b"\xf1)\x82\xfd\xa7t\xd5\x7f\x00K\xa9\x12\x80\xed\x88\xef\xae\x03;\x11<0\xf8b\x96@\xaa\x92\xef\xa6;'"
REQUESTOR_PUBLIC_KEY = b'\xe3\xb0zQ\xef\xf3\xed\x82K\xe6^@ \x0b^\xd9\xbd\x05q\r\xc5\xda)\x96G\x89\xd6\x9c\x83[v\xa4C\xdf\x1d2\x03\xbfc\xd2\x05^\xa0\xae\xc2\xfb\xd5\xf4\xcf\xb9_\xb0r\xac\x93\xe2\xbd\xed\xaf\xb5l\xa25T'

PROVIDER_PRIVATE_KEY = b'\n\xf3bqtu`\xa6q\x08~\xfd\x98\xeb&8J\xb4\xcb\xe7\xe2\xd4\xd0J\x1fB\xdc|!j@\t'
PROVIDER_PUBLIC_KEY = b'CYz\xf3\x85\x82\xa0(\x86\xd5\x9f\xcdF\x01\x1d\xf5\x8a\x84\xc7\xf4\xd6Y\xbe\xc703\xdfrK,\n\xe6\x94JG\xcfr\xaf\x82{\xe8\xd68f\xfc\x05l\x13\n\x1a\x1c\x11 \x83p \xa1\xf7"ab\xd0\x1d\xd6'


class WrongConfigurationException(Exception):
    def __init__(self, error_message):
        self.message = error_message


def are_keys_predifined(party):
    formatted_party = party.upper()
    modules_objects = globals()
    public_key = f"{formatted_party}_PUBLIC_KEY"
    private_key = f"{formatted_party}_PRIVATE_KEY"
    is_pulbic_key_predefined = public_key in modules_objects and modules_objects[public_key] is not None
    is_private_key_predefined = private_key in modules_objects and modules_objects[private_key] is not None
    return is_pulbic_key_predefined and is_private_key_predefined


def _get_predefined_keys(party):
    formatted_party = party.upper()
    modules_objects = globals()
    public_key = f"{formatted_party}_PUBLIC_KEY"
    private_key = f"{formatted_party}_PRIVATE_KEY"
    return modules_objects[private_key], modules_objects[public_key]


class KeyManager(object):
    def __init__(self):
        self.requestor_private_key, self.requestor_public_key  = self._get_or_generate_keys('requestor')
        self.provider_private_key, self.provider_public_key = self._get_or_generate_keys('provider')

    def _get_or_generate_keys(self, party):
        if are_keys_predifined(party):
            return _get_predefined_keys(party)
        return generate_ecc_key_pair()

    def get_requestor_keys(self):
        return self.requestor_public_key, self.requestor_private_key

    def get_provider_keys(self):
        return self.provider_public_key, self.provider_private_key

    def get_concent_public_key(self):
        if not hasattr(settings, "CONCENT_PUBLIC_KEY"):
            raise WrongConfigurationException("CONCENT_PUBLIC_KEY is not defined")
        concent_public_key = settings.CONCENT_PUBLIC_KEY
        if not isinstance(concent_public_key, bytes):
            raise WrongConfigurationException("CONCENT_PUBLIC_KEY should be bytes")
        key_length = len(concent_public_key)
        if key_length != 64:
            raise WrongConfigurationException(f"CONCENT_PUBLIC_KEY is of wrong length: {key_length}")
        return concent_public_key
