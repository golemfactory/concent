import importlib
import os
from celery import Celery

import django

# set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'concent_api.settings')


app = Celery('concent_api')

# Using a string here means the worker does not have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object('django.conf:settings', namespace = 'CELERY')

django.setup()
from django.conf            import settings  # noqa: E402 pylint: disable=wrong-import-position
from concent_api.constants  import AVAILABLE_CONCENT_FEATURES  # noqa: E402 pylint: disable=wrong-import-position

# Load tasks only from features specified in CONCENT_FEATURES variable
for feature_name in settings.CONCENT_FEATURES:

    app.conf.imports += tuple(
        [f'{app}.tasks'
         for app in AVAILABLE_CONCENT_FEATURES[feature_name]['required_django_apps']
         if importlib.util.find_spec(f'{app}.tasks') is not None]
    )

app.conf.task_create_missing_queues = True
app.conf.task_routes = ([
    ('verifier.tasks.verification_result', {'queue': 'concent'}),
    ('conductor.tasks.blender_verification_request', {'queue': 'conductor'}),
    ('verifier.tasks.blender_verification_order', {'queue': 'verifier'}),
],)
app.conf.task_default_queue = 'non_existing'
app.conf.task_create_missing_queues = False
