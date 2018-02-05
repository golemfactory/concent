from django.conf.urls import url

from .constants import GATEKEEPER_DOWNLOAD_PATH
from .views     import download
from .views     import upload

urlpatterns = [
    url(r'^{}'.format(GATEKEEPER_DOWNLOAD_PATH), download,   name = 'download'),
    url(r'^upload-auth/',                        upload,     name = 'upload'),
]
