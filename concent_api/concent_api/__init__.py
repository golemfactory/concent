default_app_config = 'concent_api.apps.ConcentApiConfig'

# This creates the 'app' object for celery. Doing it here ensures that it's always created when Django starts.
# It's not necessary when using `manage.py runserver` or `celery worker` but e.g. gunicorn needs it.
from .celery import app as celery_app  # noqa: E402 pylint: disable=wrong-import-position

__all__ = ['celery_app']
