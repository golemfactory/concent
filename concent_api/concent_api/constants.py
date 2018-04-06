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

    ("conductor-urls", {
        "required_django_apps": [
            "conductor",
        ],
        "url_patterns":         [
            url(r'^conductor/', include(conductor.urls, namespace = 'conductor')),
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
])


# Defines which database should be used for which app label
APP_LABEL_TO_DATABASE = {
    'auth':         'default',
    'admin':        'default',
    'contenttypes': 'default',
    'core':         'default',
    'conductor':    'storage',
    'sessions':     'default',
}
