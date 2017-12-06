"""concent_api URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/1.11/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  url(r'^$', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  url(r'^$', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.conf.urls import url, include
    2. Add a URL to urlpatterns:  url(r'^blog/', include('blog.urls'))
"""

from django.conf            import settings
from django.core.exceptions import ImproperlyConfigured

from concent_api.constants  import AVAILABLE_CONCENT_FEATURES


if not hasattr(settings, 'CONCENT_FEATURES'):
    raise ImproperlyConfigured("CONCENT_FEATURES setting is not defined")

if not set(settings.CONCENT_FEATURES) - set(AVAILABLE_CONCENT_FEATURES.keys()) == set():
    raise ImproperlyConfigured("Unrecognized feature(s) in CONCENT_FEATURES")

urlpatterns = []  # type: ignore

# Run project only with features specified in CONCENT_FEATURES variable
for feature_name in settings.CONCENT_FEATURES:
    urlpatterns += AVAILABLE_CONCENT_FEATURES[feature_name]['url_patterns']
