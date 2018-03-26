from django.conf.urls import url

from .views import upload_report

urlpatterns = [
    url(r'^upload_report/(?P<file_path>.+\.zip)$', upload_report, name='upload_report'),
]
