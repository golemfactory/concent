# pylint: disable=unused-wildcard-import

try:
    from .local_settings import *  # NOQA  # pylint: disable=wildcard-import
except ImportError as exception:
    if "local_settings" in str(exception):
        print("There is no local_settings.py file in settings folder, create it and adjust your configurations.")
    else:
        raise
