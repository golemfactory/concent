import os

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Our apps:
    'core',
    'gatekeeper',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'concent_api.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
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
    'default': {
        'ENGINE':     'django.db.backends.postgresql_psycopg2',
        'NAME':       'concent_api',
        # 'USER':     'postgres',
        # 'PASSWORD': '',
        # 'HOST':     '',
        # 'PORT':     '',

        # Wrap each request in a transactions and rolled back on failure by default
        'ATOMIC_REQUESTS': True,
    }
}


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


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/1.11/howto/static-files/

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
            'handlers':  ['mail_admins'],
            'level':     'DEBUG',
            'propagate': True,
        },
    },
}


# Private and public keys to be used by Concent to sign and encrypt its own messages.
# Stored in a 'bytes' array, e.g. b'\xf3\x97\x19\xcdX\xda...'
#CONCENT_PRIVATE_KEY =
#CONCENT_PUBLIC_KEY  =

# A global constant defining the length of the time window within which a requestor or a provider is supposed to
# contact concent and send or receive a message as defined in the protocol.
CONCENT_MESSAGING_TIME = 3600  # seconds

# Which components of this Django application should be enabled in this particular server instance.
# The application is basically a bunch of services with totally different responsibilites that share a lot of code.
# In a typical setup each instance has only one or two features enabled. Some of them provide public APIs, others are
# meant never to be exposed to the wide Internet.
# Available features are:
# - "concent-api": The public API server that allows requrestors and providers to interact with Concent.
# - "Gatekeeper":  An internal helper that validates file transfer tokens.
# - "admin-panel": Django admin panel that provides access to database content and service statistics.
# CONCENT_FEATURES = []
