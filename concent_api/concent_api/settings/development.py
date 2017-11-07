# pylint: disable=unused-wildcard-import
from .base import *  # NOQA  # pylint: disable=wildcard-import

SECRET_KEY = 'testkey'

DEBUG = True

ALLOWED_HOSTS = ['localhost']

DATABASES['default']['USER']     = 'postgres'
DATABASES['default']['PASSWORD'] = ''
