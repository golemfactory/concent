from django.conf.urls import url

from .views import file_transfer_auth

urlpatterns = [
    url(r'^file-transfer-auth/$', file_transfer_auth, name = 'file-transfer-auth'),
]
