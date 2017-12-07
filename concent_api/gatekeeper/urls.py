from django.conf.urls import url

from .views import download
from .views import upload

urlpatterns = [
    url(r'^download-auth/', download,   name = 'download'),
    url(r'^upload-auth/',   upload,     name = 'upload'),
]
