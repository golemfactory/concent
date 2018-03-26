from django.conf.urls import url

from .views import conductor

urlpatterns = [
    url(r'^conductor/', conductor, name='conductor'),
]
