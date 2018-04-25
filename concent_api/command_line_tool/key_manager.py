from utils.testing_helpers import generate_ecc_key_pair

REQUESTOR_PRIVATE_KEY = None
REQUESTOR_PUBLIC_KEY = None

PROVIDER_PRIVATE_KEY = None
PROVIDER_PUBLIC_KEY = None


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
