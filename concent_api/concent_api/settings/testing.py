# pylint: disable=unused-wildcard-import
from .base import *  # NOQA  # pylint: disable=wildcard-import

SECRET_KEY = 'testkey'

DEBUG = True

DATABASES = {
    # 'default' must be set for testing, otherwise tests won't work
    'default': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2',
        'USER': 'postgres',
        'ATOMIC_REQUESTS': True,
        'TEST': {
            'NAME': 'test_default'
        }
    },
    'control': {
        # NAME intentionally left unset, in case tests try to access the production database.
        # This could happen e.g. if someone executes a query at module level.
        'ENGINE':          'django.db.backends.postgresql_psycopg2',
        'USER':            'postgres',
        'ATOMIC_REQUESTS': True,
        'TEST': {
            'NAME': 'test_control'
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
    "conductor-urls",
    "gatekeeper",
    "verifier",
]

STORAGE_CLUSTER_ADDRESS = 'http://localhost/'

CONCENT_MESSAGING_TIME    = 2

FORCE_ACCEPTANCE_TIME     = 5

MINIMUM_UPLOAD_RATE       = 1

DOWNLOAD_LEADIN_TIME      = 3
