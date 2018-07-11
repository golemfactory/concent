import argparse
import logging.config
import os
import socket

from raven import Client

from constants import SIGNING_SERVICE_DEFAULT_PORT  # pylint: disable=no-name-in-module


logger = logging.getLogger()
crash_logger = logging.getLogger('crash')


def main(host, port):
    socket_to_concent = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        socket_to_concent.connect((host, port))
    except socket.gaierror as exception:
        logger.error(f'Exception occurred when connecting to {host}:{port}: {exception}')
        exit(f'Exception occurred when connecting to {host}:{port}: {exception}')

    socket_to_concent.send(b'GET / HTTP/1.0\r\n\r\n')
    data = socket_to_concent.recv(1024)
    logger.info(data)
    socket_to_concent.close()


def _parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        'concent_cluster_host',
        help='Host or IP address of a service on Concent cluster, to which SigningService connects over TCP.'
    )
    parser.add_argument(
        '--concent-cluster-port',
        default=SIGNING_SERVICE_DEFAULT_PORT,
        dest='concent_cluster_port',
        type=int,
        help=f'Port on which Concent cluster is listening (default: {SIGNING_SERVICE_DEFAULT_PORT}).'
    )
    parser.add_argument(
        '--sentry-dsn',
        default='',
        dest='sentry_dsn',
        help=f'Sentry DSN for error reporting.'
    )

    return parser.parse_args()


if __name__ == '__main__':
    logging.config.fileConfig(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'logging.ini'))
    args = _parse_arguments()

    raven_client = Client(dsn=args.sentry_dsn)
    crash_logger.handlers[0].client = raven_client  # type: ignore

    main(args.concent_cluster_host, args.concent_cluster_port)
