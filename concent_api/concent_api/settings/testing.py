# pylint: disable=unused-wildcard-import
from .base import *  # NOQA  # pylint: disable=wildcard-import

SECRET_KEY = 'testkey'

DEBUG = True

DATABASES = {
    'default': {
        # NAME intentionally left unset, in case tests try to access the production database.
        # This could happen e.g. if someone executes a query at module level.
        'ENGINE':          'django.db.backends.postgresql_psycopg2',
        'USER':            'postgres',
        'ATOMIC_REQUESTS': True,
        'TEST': {
            'NAME': 'test_concent_api'
        }
    }
}

LOGGING = {
    'version': 1,
    'disable_existing_loggers': True,
    'handlers': {
        'null_handler': {'class': 'logging.NullHandler'}
    },
    'loggers': {
        '': {'handlers': ['null_handler']}
    }
}

CONCENT_FEATURES = [
    "concent-api",
    "gatekeeper",
    "admin-panel",
]

STORAGE_CLUSTER_ADDRESS = 'http://localhost/'
