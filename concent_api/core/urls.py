from django.conf.urls import url

from .views import receive
from .views import send
from .views import protocol_constants

urlpatterns = [
    url(r'^send/$', send, name='send'),
    url(r'^receive/$', receive, name='receive'),
    url(r'^protocol-constants/$', protocol_constants, name='protocol_constants'),
]
