import os
from argparse import Action
from base64 import b64decode

from golem_messages.cryptography import verify_pubkey
from golem_messages.exceptions import InvalidKeys

from signing_service.constants import ETHEREUM_PRIVATE_KEY_LENGTH
from signing_service.constants import ETHEREUM_PRIVATE_KEY_REGEXP


def is_valid_public_key(key: bytes) -> bool:
    """ Validates if given bytes are valid public key by using function from golem-messages. """

    assert isinstance(key, bytes)

    try:
        verify_pubkey(key)
        return True
    except InvalidKeys:
        return False


def is_valid_private_key(key: str) -> bool:
    """
    Validates if given string is valid Ethereum private key.

    Ethereum private key format is described in
    `https://theethereum.wiki/w/index.php/Accounts,_Addresses,_Public_And_Private_Keys,_And_Tokens`.
    """

    assert isinstance(key, str)

    return len(key) == ETHEREUM_PRIVATE_KEY_LENGTH and ETHEREUM_PRIVATE_KEY_REGEXP.fullmatch(key) is not None


def make_secret_provider_factory(
    read_command_line=False,
    env_variable_name=None,
    use_file=False,
    base64_convert=False,
    string_decode=False,
):
    def wrapper(**kwargs):
        return SecretProvider(
            read_command_line,
            env_variable_name,
            use_file,
            base64_convert,
            string_decode,
            **kwargs
        )
    return wrapper


class SecretProvider(Action):

    def __init__(
        self,
        read_command_line,
        env_variable_name,
        use_file,
        base64_convert,
        string_decode,
        option_strings,
        dest,
        required=False,
        help=None  # pylint: disable=redefined-builtin
    ):
        self.read_command_line = read_command_line
        self.env_variable_name = env_variable_name
        self.use_file = use_file
        self.base64_convert = base64_convert
        self.string_decode = string_decode

        super().__init__(
            option_strings=option_strings,
            dest=dest,
            required=required,
            help=help,
            nargs=0 if self.env_variable_name is not None else None,
        )

    def __call__(self, parser, namespace, values, option_string=None):
        if values is not None and self.use_file:
            with open(values) as file:
                self.const = file.read()
        elif values is not None and self.read_command_line:
            self.const = values
        elif self.env_variable_name is not None:
            self.const = os.environ.get(self.env_variable_name)
        else:
            assert False
        if self.base64_convert:
            assert isinstance(self.const, str)
            self.const = b64decode(self.const)
            if self.string_decode:
                self.const = self.const.decode()
        setattr(namespace, self.dest, self.const)
