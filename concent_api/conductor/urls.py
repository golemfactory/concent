from django.conf.urls import url

from .views import report_upload

urlpatterns = [
    url(r'^report-upload/(?P<file_path>.+\.zip)$', report_upload, name='report-upload'),
]
