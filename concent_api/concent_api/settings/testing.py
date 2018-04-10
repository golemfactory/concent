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
    },
    'storage': {
        # NAME intentionally left unset, in case tests try to access the production database.
        # This could happen e.g. if someone executes a query at module level.
        'ENGINE':          'django.db.backends.postgresql_psycopg2',
        'USER':            'postgres',
        'ATOMIC_REQUESTS': True,
        'TEST': {
            'NAME': 'test_storage'
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
    "admin-panel",
    "concent-api",
    "conductor",
    "gatekeeper",
    "verifier",
]

STORAGE_CLUSTER_ADDRESS = 'http://localhost/'

STORAGE_SERVER_INTERNAL_ADDRESS = 'http://localhost/'

VERIFIER_STORAGE_PATH = '/tmp/'

CONCENT_MESSAGING_TIME    = 0

FORCE_ACCEPTANCE_TIME     = 0

MAXIMUM_DOWNLOAD_TIME     = 0

SUBTASK_VERIFICATION_TIME = 0

BLENDER_MAX_RENDERING_TIME = 10
