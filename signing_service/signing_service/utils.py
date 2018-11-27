import binascii
import logging.config
import os
import smtplib
from argparse import Action
from argparse import Namespace
from argparse import ArgumentParser
from base64 import b64decode
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any
from typing import Callable
from typing import Optional
from typing import Union

from golem_messages.cryptography import verify_pubkey
from golem_messages.exceptions import InvalidKeys

from signing_service.constants import ETHEREUM_PRIVATE_KEY_REGEXP
from signing_service.exceptions import Base64DecodeError

logger = logging.getLogger()


def is_public_key_valid(key: bytes) -> bool:
    """ Validates if given bytes are valid public key by using function from golem-messages. """

    assert isinstance(key, bytes)

    try:
        verify_pubkey(key)
        return True
    except InvalidKeys:
        return False


def is_private_key_valid(key: str) -> bool:
    """
    Validates if given string is valid Ethereum private key.

    Ethereum private key format is described in
    `https://theethereum.wiki/w/index.php/Accounts,_Addresses,_Public_And_Private_Keys,_And_Tokens`.
    """

    assert isinstance(key, str)

    return ETHEREUM_PRIVATE_KEY_REGEXP.fullmatch(key) is not None


def make_secret_provider_factory(
    read_command_line: bool=False,
    env_variable_name: Union[str, None]=None,
    use_file: bool=False,
    base64_convert: bool=False,
    string_decode: bool=False,
) -> Callable:
    def wrapper(**kwargs: Any) -> 'SecretProvider':
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
        read_command_line: bool,
        env_variable_name: Union[str, None],
        use_file: bool,
        base64_convert: bool,
        string_decode: bool,
        option_strings: list,
        dest: str,
        required: bool=False,
        help: Optional[str]=None  # pylint: disable=redefined-builtin
    ) -> None:
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

    def __call__(  # type: ignore
        self,
        parser: ArgumentParser,
        namespace: Namespace,
        value: str,
        option_string: Optional[str]=None
    ) -> None:
        assert value is not None
        if self.use_file:
            with open(value) as file:
                self.const = file.read()
        elif self.read_command_line:
            self.const = value
        else:
            assert self.env_variable_name is not None
            self.const = os.environ.get(self.env_variable_name)
        if self.base64_convert:
            assert isinstance(self.const, str)
            try:
                self.const = b64decode(self.const)
            except binascii.Error as exception:
                logger.error(f'Unable to decode "{self.const}", {exception}')
                raise Base64DecodeError(f'Unable to decode "{self.const}", {exception}')
            if self.string_decode:
                self.const = self.const.decode()
        setattr(namespace, self.dest, self.const)


class ConsoleNotifier:

    @staticmethod
    def send(
        message: str,
    ) -> None:
        logger.info(message)


class EmailNotifier:

    __slots__ = (
        'from_email_address',
        'from_email_password',
        'to_email_addresses',
        'server',
    )

    def __init__(
        self,
        from_email_address: str,
        from_email_password: str,
        to_email_addresses: list,
    ) -> None:
        assert isinstance(from_email_address, str)
        assert isinstance(from_email_password, str)
        assert isinstance(to_email_addresses, list)
        self.from_email_address = from_email_address
        self.from_email_password = from_email_password
        self.to_email_addresses = to_email_addresses
        self.server = None

    def send(
        self,
        message: str,
    ) -> None:
        message_to_send = MIMEMultipart()
        message_to_send['From'] = "Signing Service Notifier"
        message_to_send['To'] = ','.join(self.to_email_addresses)
        message_to_send['Subject'] = "Signing Service notification"
        message_to_send.attach(MIMEText(message))
        self.__send_email(message_to_send)

    def __send_email(
        self,
        message: MIMEMultipart,
    ) -> None:
        try:
            self.__connect_to_gmail_smtp_server()
            self.server.send_message(message)  # type: ignore
            self.__end_smtp_server_connection()
        except smtplib.SMTPException as exception:
            logger.error(f'SMTPException occurred: {exception}')

    def __connect_to_gmail_smtp_server(self) -> None:
        self.server = smtplib.SMTP_SSL('smtp.gmail.com:465', timeout=3)  # type: ignore
        self.server.connect('smtp.gmail.com:465')  # type: ignore
        self.server.ehlo()  # type: ignore
        self.server.login(self.from_email_address, self.from_email_password)  # type: ignore
        self.server.set_debuglevel(True)  # type: ignore

    def __end_smtp_server_connection(self) -> None:
        self.server.quit()  # type: ignore
