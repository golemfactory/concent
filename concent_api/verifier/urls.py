from django.conf.urls import url

from .views     import verifier

urlpatterns = [
    url(r'^verifier/$', verifier, name = 'verifier'),
]
