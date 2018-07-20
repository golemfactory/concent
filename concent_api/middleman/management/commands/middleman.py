from django.core.management.base import BaseCommand

from middleman.constants import DEFAULT_INTERNAL_PORT
from middleman.constants import LOCALHOST_IP
from middleman.middleman_server import MiddleMan


class Command(BaseCommand):
    help = 'Starts MiddleMan app'

    def add_arguments(self, parser):
        parser.add_argument(
            '-a',
            '--bind-address',
            type=str,
            default=LOCALHOST_IP,
            help="A port MiddleMan will be listening for Concent clients to connect."
        )

        parser.add_argument(
            '-i',
            '--internal-port',
            type=int,
            default=DEFAULT_INTERNAL_PORT,
            help="A port MiddleMan will be listening for Concent clients to connect."
        )

    def handle(self, *args, **options):
        MiddleMan(
            bind_address=options['bind_address'],
            internal_port=options['internal_port'],
        ).run()

        print("\nEND OF EVANGELION")
