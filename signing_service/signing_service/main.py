import os

import logging.config
from raven import Client

from signing_service.signing_service import _parse_arguments
from signing_service.signing_service import SigningService
from signing_service.utils import get_notifier

crash_logger = logging.getLogger('crash')

if __name__ == '__main__':

    logging.config.fileConfig(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'logging.ini'))

    # Parse required arguments.
    args = _parse_arguments()

    raven_client = Client(
        dsn=args.sentry_dsn,
        environment=args.sentry_environment,
        tags={
            'component': 'signing-service',
        },
    )
    crash_logger.handlers[0].client = raven_client  # type: ignore

    notifier = get_notifier(args)

    SigningService(
        args.concent_cluster_host,
        args.concent_cluster_port,
        args.initial_reconnect_delay,
        args.concent_public_key,
        args.signing_service_private_key,
        args.ethereum_private_key,
        args.max_reconnect_attempts,
        notifier,
    ).run()
