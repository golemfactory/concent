from .base import *

SECRET_KEY = 'testkey'

DEBUG = True

ALLOWED_HOSTS = ['localhost']

DATABASES['default']['USER']     = 'postgres'
DATABASES['default']['PASSWORD'] = ''
