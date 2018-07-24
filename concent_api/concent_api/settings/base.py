import os

from mypy.types import Dict  # noqa # pylint: disable=unused-import

from django.conf.locale.en import formats
from golem_messages import constants

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Application definition

INSTALLED_APPS = [
    # Built-in apps:
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third-party apps:
    'raven.contrib.django.raven_compat',
    'constance',
    'constance.backends.database',

    # Our apps:
    'concent_api',
    'conductor',
    'core',
    'gatekeeper',
    'middleman',
    'verifier',
]

MIDDLEWARE = [
    'concent_api.middleware.HandleServerErrorMiddleware',  # this middleware is disabled in tests - check testing.py
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'concent_api.middleware.GolemMessagesVersionMiddleware',
    'concent_api.middleware.ConcentVersionMiddleware',
]

ROOT_URLCONF = 'concent_api.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'core', 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'concent_api.wsgi.application'


# Database
# https://docs.djangoproject.com/en/1.11/ref/settings/#databases

DATABASES = {
    # We set 'default' database to empty config explicitly, as we want to control very carefully which models are in
    # which database. However, django requires 'default' database to exists in settings.
    'default': {},
    'control': {
        'ENGINE':     'django.db.backends.postgresql_psycopg2',
        'NAME':       'concent_api',
        # 'USER':     'postgres',
        # 'PASSWORD': '',
        # 'HOST':     '',
        # 'PORT':     '',

        # Wrap each request in a transactions and rolled back on failure by default
        'ATOMIC_REQUESTS': True,
    },
    'storage': {
        'ENGINE':     'django.db.backends.postgresql_psycopg2',
        'NAME':       'storage',
        # 'USER':     'postgres',
        # 'PASSWORD': '',
        # 'HOST':     '',
        # 'PORT':     '',

        # Wrap each request in a transactions and rolled back on failure by default
        'ATOMIC_REQUESTS': True,
    }
}  # type: Dict[str, Dict]

DATABASE_ROUTERS = ['concent_api.database_router.DatabaseRouter']

# Defines database used by Constance app.
CONSTANCE_DBS = ['control']

# Password validation
# https://docs.djangoproject.com/en/1.11/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/1.11/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_L10N = True

USE_TZ = True

# Works as datetime format in django-admin.
formats.DATETIME_FORMAT = 'Y-m-d H:i:s'  # '2018-07-04 23:57:59'


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/1.11/howto/static-files/
STATICFILES_DIRS = [os.path.join(BASE_DIR, "core", "static")]
STATIC_URL = '/static/'

STATIC_ROOT = os.path.join(BASE_DIR, 'static-root')

LOGGING = {
    'version':                  1,
    'disable_existing_loggers': False,
    'formatters':               {
        'console': {
            'format':  '%(asctime)s %(levelname)-8s | %(message)s',
            'datefmt': '%H:%M:%S',
        },
    },
    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse',
        }
    },
    'handlers': {
        'sentry': {
            'level': 'ERROR',
            'class': 'raven.contrib.django.raven_compat.handlers.SentryHandler',
        },
        'mail_admins': {
            'level':   'ERROR',
            'filters': ['require_debug_false'],
            'class':   'django.utils.log.AdminEmailHandler',
        },
        'console': {
            'level':     'INFO',
            'class':     'logging.StreamHandler',
            'formatter': 'console',
        },
    },
    'loggers': {
        # NOTE: There are a few important caveats you need to consider when tweaking logging:
        # - If a message is logged to logger 'a.b' and propagates to logger 'a', only the level of logger
        #   'a.b' counts. Level of logger 'a' is ignored. Not kidding. See the diagram:
        #   https://docs.python.org/3/howto/logging.html#logging-flow
        # - level of logger 'a.b' determines not only what it handles but also what it propagates to parent.
        # - If a logger has no level, it inherits level from parent. Root logger (the one called '') has level WARNING by default.

        # RULES: Try to stick to the following conventions:
        # - Don't set level of a logger unless you explicitly want to prevent some messages from being handled or propagated.
        # - In most cases it's better to leave level at DEBUG here and set level in handler instead.
        # - Set level explicitly if you don't propagate. Such a logger should not be dependent on parent's level.
        # - Don't propagate to the root logger if the output is very verbose. Use a separate handler/file instead.
        # - Log at INFO level should be concise and contain only important stuff. Enough to understand what
        #   is happening but not necessarily why. DEBUG level can be more spammy.

        '': {
            # Logging to the console. The application is primarily going to run in foreground inside Docker container
            # and we want Docker to capture all that output. You can add an extra file handler in your local_settings.py
            # if you think you really need it. Do keep in mind though that log files need to be rotated or they'll eat
            # a lot of disk space.
            'handlers':  ['console'],
            # NOTE: Changing level of this logger will change levels of loggers from plugins
            # because they often don't have a level set explicitly and inherit this one instead.
            'level':     'DEBUG',
            'propagate': False,
        },
        'py.warnings': {
            # Prevent Python from printing its warnings to the console. Our top-level logger already handles and prints them.
            # I'm not entirely sure why this works but I think that the default py.warnings has a custom console handler
            # attached and by defining it here we're overwriting it and disabling the handler.
            'level':     'DEBUG',
            'propagate': True,
        },
        'django': {
            # Redefine django logger without handlers. Otherwise errors propagated from django.request
            # get logged to the console twice.
            'handlers':  [],
            'level':     'DEBUG',
            'propagate': True,
        },
        'django.db': {
            # Filter out DEBUG messages. There are too many of them. Django logs all DB queries at this level.
            'level':     'INFO',
            'propagate': True,
        },
        'django.request': {
            # Level is DEBUG because we're leaving filtering up to the handler.
            'handlers':  ['sentry'],
            'level':     'DEBUG',
            'propagate': True,
        },
        'concent.crash': {
            # Level is DEBUG because we're leaving filtering up to the handler.
            'handlers':  ['sentry'],
            'level':     'DEBUG',
            'propagate': True,
        },
    },
}

# Django constance config
CONSTANCE_BACKEND = 'constance.backends.database.DatabaseBackend'
CONSTANCE_CONFIG = {
    # Defines if Concent is in soft shutdown mode.
    'SOFT_SHUTDOWN_MODE': (False, 'Soft shutdown mode', bool),
}

CONSTANCE_CONFIG_FIELDSETS = {
    'Concent Options': ('SOFT_SHUTDOWN_MODE',),
}

# Private and public keys to be used by Concent to sign and encrypt its own messages.
# Stored in a 'bytes' array, e.g. b'\xf3\x97\x19\xcdX\xda...'
#CONCENT_PRIVATE_KEY =
#CONCENT_PUBLIC_KEY  =

# A global constant defining the length of the time window within which a requestor or a provider is supposed to
# contact concent and send or receive a message as defined in the protocol.
CONCENT_MESSAGING_TIME = int(constants.CMT.total_seconds())

# A global constant defining the length of the time window within which a requestor can
# contact concent for forced getting task results.
FORCE_ACCEPTANCE_TIME = int(constants.FAT.total_seconds())

# A global constant defining the assumed default resource download rate.
MINIMUM_UPLOAD_RATE = constants.DEFAULT_UPLOAD_RATE

# A global constant defining the download timeout margin independent from the size of the result.
DOWNLOAD_LEADIN_TIME = int(constants.DOWNLOAD_LEADIN_TIME.total_seconds())

# A global constant defining the lenght of the time window within which a requestor must pay
PAYMENT_DUE_TIME = int(constants.PDT.total_seconds())

# A global constant defining currently used payment backend.
PAYMENT_BACKEND = 'core.payments.backends.mock'

# A global constant defining the path to self-signed SSL certificate to storage cluster
STORAGE_CLUSTER_SSL_CERTIFICATE_PATH = ''

# A global constant defining address to geth client
# GETH_ADDRESS = 'http://localhost:8545'

# A global constant defining Concent ethereum contract address
# Stored in a 'string' 0x...
# CONCENT_ETHEREUM_ADDRESS = ''

# A global constant defining Concent ethereum private key
# Stored in a 'bytes' array, e.g. b'\xf3\x97\x19\xcdX\xda...'
# CONCENT_ETHEREUM_PRIVATE_KEY = ''

# A global constant defining the URL of the storage server
# STORAGE_SERVER_INTERNAL_ADDRESS = ''

# A global constant defining Path to a directory where verifier can store files downloaded from the storage server,
# rendering results and any intermediate files.
# VERIFIER_STORAGE_PATH = ''

CUSTOM_PROTOCOL_TIMES = False

# The minimum acceptable value of the SSIM metric. Values below this threshold for an image pair will result in a
# failed verification (i.e. the images are considered different).
VERIFIER_MIN_SSIM = 0.94

# A global constant defining how many times ADDITIONAL_VERIFICATION_TIME is multiplied to provide enought time for
# completing verification.
ADDITIONAL_VERIFICATION_TIME_MULTIPLIER = 2.0

# Which components of this Django application should be enabled in this particular server instance.
# The application is basically a bunch of services with totally different responsibilites that share a lot of code.
# In a typical setup each instance has only one or two features enabled. Some of them provide public APIs, others are
# meant never to be exposed to the wide Internet.
# Available features are:
# - "concent-api": The public API server that allows requrestors and providers to interact with Concent.
# - "concent-worker": Celery worker handling notification from storage cluster about completed file transfer.
# - "conductor-urls": API server handling notification from nginx about uploaded files.
# - "conductor-worker": Celery worker notifying control cluster about finished uploads and upon received
#                       acknowledgement, ordering the start of verification process.
# - "verifier": Celery worker that processes verification and notifies control cluster about its result.
# - "middleman":  A socket server that mediates communication between Signing Service and Concent.
# - "gatekeeper":  An internal helper that validates file transfer tokens.
# - "admin-panel": Django admin panel that provides access to database content and service statistics.
CONCENT_FEATURES = []  # type: ignore

# URL format: 'protocol://<user>:<password>@<hostname>:<port>/<virtual host>'
# CELERY_BROKER_URL = ''

# Debug setting for adding stack traces in HTTP500 responses
#DEBUG_INFO_IN_ERROR_RESPONSES =

# Temporary setting for enabling mock verification - the result of verification depends on subtask_id
MOCK_VERIFICATION_ENABLED = True

# Verifier setting defining number of threads used by Blender
BLENDER_THREADS = 1
