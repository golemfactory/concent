from collections      import OrderedDict

from django.conf.urls import url, include
from django.contrib   import admin

import core.urls
import conductor.urls
import gatekeeper.urls


AVAILABLE_CONCENT_FEATURES = OrderedDict([
    ("admin-panel", {
        "required_django_apps": [
            "django.contrib.admin",
        ],
        "url_patterns":         [
            url(r'^admin/', admin.site.urls),
        ],
    }),

    ("concent-api", {
        "required_django_apps": [
            "core",
        ],
        "url_patterns":         [
            url(r'^api/v1/', include(core.urls, namespace = 'core')),
        ],
    }),

    ("concent-worker", {
        "required_django_apps": [
            "core",
        ],
        "url_patterns": [],
    }),

    ("conductor-urls", {
        "required_django_apps": [
            "conductor",
        ],
        "url_patterns":         [
            url(r'^conductor/', include(conductor.urls, namespace='conductor')),
        ],
    }),

    ("conductor-worker", {
        "required_django_apps": [
            "conductor",
        ],
        "url_patterns": [],
    }),

    ("gatekeeper", {
        "required_django_apps": [
            "gatekeeper",
        ],
        "url_patterns": [
            url(r'^gatekeeper/', include(gatekeeper.urls, namespace='gatekeeper')),
        ],
    }),

    ("middleman", {
        "required_django_apps": [
            "middleman",
        ],
        "url_patterns": [],
    }),

    ("verifier", {
        "required_django_apps": [
            "verifier",
        ],
        "url_patterns": [],
    }),
])


# Defines which database should be used for which app label
APP_LABEL_TO_DATABASE = {
    'auth':         'control',
    'admin':        'control',
    'contenttypes': 'control',
    'core':         'control',
    'conductor':    'storage',
    'constance':    'control',
    'database':     'control',
    'sessions':     'control',
}
DEFAULT_ERROR_MESSAGE = "Something went wrong, sorry"
