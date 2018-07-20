import sys
import requests
from typing import NamedTuple

ProtocolConstants = NamedTuple(
    "ProtocolConstants",
    [
        ("concent_messaging_time", int),
        ("force_acceptance_time", int),
        ("minimum_upload_rate", int),
        ("download_leadin_time", int),
        ("payment_due_time", int),
    ]
)


def get_protocol_constants(cluster_url):
    url = f"{cluster_url}/api/v1/protocol-constants/"
    response = requests.get(url, verify = False)
    json = response.json()
    return ProtocolConstants(**json)


def print_protocol_constants(constants):
    print("PROTOCOL_CONSTANTS: ")
    print("\n".join(f"{field} = {getattr(constants, field)}" for field in constants._fields))


def main():
    try:
        cluster_url = sys.argv[1]
    except IndexError:
        cluster_url = 'https://devel.concent.golem.network'

    cluster_consts = get_protocol_constants(cluster_url)
    print_protocol_constants(cluster_consts)


if __name__ == '__main__':
    main()
