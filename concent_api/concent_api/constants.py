from collections      import OrderedDict

from django.conf.urls import url, include
from django.contrib   import admin

import core.urls
import conductor.urls
import gatekeeper.urls
import verifier.urls

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

    ("conductor-urls", {
        "required_django_apps": [
            "conductor",
        ],
        "url_patterns":         [
            url(r'^conductor/', include(conductor.urls, namespace='conductor')),
        ],
    }),

    ("gatekeeper", {
        "required_django_apps": [
            "gatekeeper",
        ],
        "url_patterns":         [
            url(r'^gatekeeper/', include(gatekeeper.urls, namespace = 'gatekeeper')),
        ],
    }),

    ("verifier", {
        "required_django_apps": [
            "verifier",
        ],
        "url_patterns": [
            url(r'^verifier/', include(verifier.urls, namespace='verifier')),
        ],
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
