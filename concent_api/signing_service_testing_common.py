from pathlib import Path
import argparse
import configparser
import enum
import random
import socket

from golem_messages.message import Message
from golem_messages.message import Ping
from golem_sci import chains
from golem_sci import new_sci_rpc
from golem_sci.transactionsstorage import JsonTransactionsStorage
from middleman_protocol.concent_golem_messages.message import TransactionSigningRequest
from middleman_protocol.message import AbstractFrame
from middleman_protocol.message import GolemMessageFrame
from middleman_protocol.stream import send_over_stream
from middleman_protocol.stream import unescape_stream
import requests

from api_testing_common import count_fails
from api_testing_common import execute_tests
from api_testing_common import get_tests_list


# Defines name of default config file.
DEFAULT_CONFIG_FILE = 'signing_service_tests.ini'


class ComponentConnectionError(Exception):
    pass


# Defines available components.
class Components(enum.Enum):
    CONCENT_API = 'concent-api'
    MIDDLEMAN = 'middleman'
    ETHEREUM_BLOCKCHAIN = 'ethereum-blockchain'


# Defines required settings for all available components.
REQUIRED_COMPONENTS_SETTINGS = {
    Components.CONCENT_API: [
        'api_url',
    ],
    Components.MIDDLEMAN: [
        'host',
        'port',
    ],
    Components.ETHEREUM_BLOCKCHAIN: [
        'geth_address',
        'concent_ethereum_address',
    ],
}


def read_config() -> configparser.ConfigParser:
    """ Reads config from INI file. """
    config = configparser.ConfigParser()
    config.read(DEFAULT_CONFIG_FILE)
    return config


def read_command_line() -> argparse.Namespace:
    """ Reads arguments from command line. """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-c',
        '--concent-api-url',
        dest='concent_api_url',
        type=str,
    )
    parser.add_argument(
        '-a',
        '--middleman-host',
        dest='middleman_host',
        type=str,
    )
    parser.add_argument(
        '-p',
        '--middleman-port',
        dest='middleman_port',
        type=str,
    )
    parser.add_argument(
        '-g',
        '--ethereum-blockchain-geth-address',
        dest='ethereum_blockchain_geth_address',
        type=str,
    )
    parser.add_argument(
        '-e',
        '--ethereum-blockchain-concent-ethereum-address',
        dest='ethereum_blockchain_concent_ethereum_address',
        type=str,
    )

    return parser.parse_args()


def update_config(config: configparser.ConfigParser, arguments: argparse.Namespace) -> configparser.ConfigParser:
    """ Updates values in config on arguments parsed from command line. """
    if arguments.concent_api_url is not None:
        config[Components.CONCENT_API.value]['api_url'] = arguments.concent_api_url

    if arguments.middleman_host is not None:
        config[Components.MIDDLEMAN.value]['host'] = arguments.middleman_host
    if arguments.middleman_port is not None:
        config[Components.MIDDLEMAN.value]['port'] = arguments.middleman_port

    if arguments.ethereum_blockchain_geth_address is not None:
        config[Components.ETHEREUM_BLOCKCHAIN.value]['geth_address'] = arguments.ethereum_blockchain_geth_address
    if arguments.ethereum_blockchain_concent_ethereum_address is not None:
        config[Components.ETHEREUM_BLOCKCHAIN.value]['concent_ethereum_address'] = arguments.ethereum_blockchain_concent_ethereum_address

    return config


def are_required_settings_in_config(components: list, config: configparser.ConfigParser) -> None:
    """ Verifies if config values for required components are set. """
    for component in components:
        assert config.has_section(component.value)
        assert config.options(component.value) == REQUIRED_COMPONENTS_SETTINGS[component]


def run_tests(objects: dict) -> None:
    """ Main tests runner, prepares test config, gather test functions, executes them, show results. """
    assert 'REQUIRED_COMPONENTS' in objects, 'Test suite must define `REQUIRED_COMPONENTS`.'

    # Parse config.
    config = read_config()
    arguments = read_command_line()
    config = update_config(config, arguments)
    are_required_settings_in_config(objects['REQUIRED_COMPONENTS'], config)

    # Check if required components are running.
    check_if_required_components_are_running(objects['REQUIRED_COMPONENTS'], config)

    # Prepare tests list.
    test_id = str(random.randrange(1, 100000))
    tests_to_execute = get_tests_list([], list(objects.keys()))
    print("Tests to be executed: \n * " + "\n * ".join(tests_to_execute))
    print()

    # Execute tests.
    execute_tests(
        tests_to_execute=tests_to_execute,
        objects=objects,
        test_id=test_id,
        config=config,
    )

    # Count fails.
    if count_fails.get_fails() > 0:
        count_fails.print_fails()

    print("END")


def check_if_required_components_are_running(components: list, config: configparser.ConfigParser) -> None:
    """ Main tests runner, prepares test config, gather test functions, executes them, show results. """
    if Components.CONCENT_API in components:
        if not is_concent_api_running(**dict(config.items(Components.CONCENT_API.value))):
            raise ComponentConnectionError(
                f'Unable to connect to ConcentAPI with config: {config.items(Components.CONCENT_API.value)}'
            )
    if Components.MIDDLEMAN in components:
        if not is_middleman_running(**dict(config.items(Components.MIDDLEMAN.value))):
            raise ComponentConnectionError(
                f'Unable to connect to MiddleMan with config: {config.items(Components.MIDDLEMAN.value)}'
            )
    if Components.ETHEREUM_BLOCKCHAIN in components:
        if not is_ethereum_blockchain_running(**dict(config.items(Components.ETHEREUM_BLOCKCHAIN.value))):
            raise ComponentConnectionError(
                f'Unable to connect to Ethereum blockchain with config: {config.items(Components.ETHEREUM_BLOCKCHAIN.value)}'
            )


def is_concent_api_running(api_url: str) -> bool:
    """ Verifies if Concent API server instance is running on given API url. """
    try:
        response = requests.post(
            api_url,
            data=Ping().serialize(),
            headers={
                'Content-Type': 'application/octet-stream',
            },
            verify=False,
        )
        return (
            response.json()['error'] == 'Unknown message type' and
            response.json()['error_code'] == 'message.unknown'
        )
    except requests.ConnectionError:
        return False


def is_middleman_running(host: str, port: str) -> bool:
    """ Verifies if MiddleMan server instance is running on given host and port. """
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)

    try:
        client_socket.connect((host, int(port)))
        return True
    except ConnectionRefusedError:
        return False
    finally:
        client_socket.close()


def is_ethereum_blockchain_running(geth_address: str, concent_ethereum_address: str) -> bool:
    """ Verifies if Ethereum Blockchain is running and can be connected. """
    sci_client = new_sci_rpc(
        rpc=geth_address,
        address=concent_ethereum_address,
        chain=chains.RINKEBY,
        storage=JsonTransactionsStorage(filepath=Path('./storage.json')),
    )
    transaction_count = sci_client.get_transaction_count()
    return isinstance(transaction_count, int)


def send_message_to_middleman_and_receive_response(
    message: AbstractFrame,
    config: configparser.ConfigParser,
    concent_private_key: bytes,
    concent_public_key: bytes,
) -> GolemMessageFrame:
    """ Sends message to MiddleMan using MiddleMan protocol and retrieves response. """
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)

    try:
        client_socket.connect(
            (
                config.get(Components.MIDDLEMAN.value, 'host'),
                int(config.get(Components.MIDDLEMAN.value, 'port')),
            )
        )
        send_over_stream(
            connection=client_socket,
            raw_message=message,
            private_key=concent_private_key,
        )
        receive_frame_generator = unescape_stream(connection=client_socket)
        raw_response = next(receive_frame_generator)
        return GolemMessageFrame.deserialize(
            raw_message=raw_response,
            public_key=concent_public_key,
        )
    finally:
        client_socket.close()


def send_message_to_middleman_without_response(
    message: AbstractFrame,
    config: configparser.ConfigParser,
    concent_private_key: bytes,
) -> GolemMessageFrame:
    """ Sends message to MiddleMan using MiddleMan protocol and does not retrieve response. """
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)

    try:
        client_socket.connect(
            (
                config.get(Components.MIDDLEMAN.value, 'host'),
                int(config.get(Components.MIDDLEMAN.value, 'port')),
            )
        )
        send_over_stream(
            connection=client_socket,
            raw_message=message,
            private_key=concent_private_key,
        )
    finally:
        client_socket.close()


def create_golem_message_frame(payload: Message, request_id: int) -> GolemMessageFrame:
    return GolemMessageFrame(
        payload=payload,
        request_id=request_id,
    )


def correct_transaction_signing_request(request_id: int) -> TransactionSigningRequest:
    return TransactionSigningRequest(
        nonce=request_id,
        gasprice=10 ** 6,
        startgas=80000,
        value=10,
        to=b'7917bc33eea648809c28',
        data=b'3078666333323333396130303030303030303030303030303030303030303030303032393662363963383738613734393865663463343531363436353231336564663834666334623330303030303030303030303030303030303030303030303030333431336437363161356332633362656130373531373064333239363566636161386261303533633030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303237313030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303030303562343336643666',
        from_address=b'7917bc33eea648809c29',
    )


def incorrect_transaction_signing_request() -> TransactionSigningRequest:
    return TransactionSigningRequest()


def create_golem_message_frame_with_correct_transaction_signing_request(request_id: int) -> GolemMessageFrame:
    return create_golem_message_frame(
        payload=correct_transaction_signing_request(request_id),
        request_id=request_id,
    )


def create_golem_message_frame_with_incorrect_transaction_signing_request(request_id: int) -> GolemMessageFrame:
    return create_golem_message_frame(
        payload=incorrect_transaction_signing_request(),
        request_id=request_id,
    )
