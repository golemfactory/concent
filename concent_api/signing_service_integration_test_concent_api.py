#!/usr/bin/env python3

from configparser import ConfigParser
import os
import sys

from api_testing_common import count_fails

from signing_service_testing_common import Components
from signing_service_testing_common import run_tests


REQUIRED_COMPONENTS = [Components.CONCENT_API, Components.ETHEREUM_BLOCKCHAIN]

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "concent_api.settings")


@count_fails
def test_case_(test_id: str, config: ConfigParser) -> None:
    """

    """
    pass


if __name__ == '__main__':
    try:
        run_tests(globals())
    except Exception as exception:
        print("\nERROR: Tests failed with exception:\n", file=sys.stderr)
        sys.exit(str(exception))
