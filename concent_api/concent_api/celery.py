import os
from celery import Celery

# set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'concent_api.settings')


app = Celery('concent_api')

# Using a string here means the worker does not have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object('django.conf:settings', namespace = 'CELERY')

app.conf.task_create_missing_queues = True
app.conf.task_routes = ([
    ('verifier.tasks.verification_result', {'queue': 'concent'}),
    ('conductor.tasks.blender_verification_request', {'queue': 'conductor'}),
    ('conductor.tasks.upload_acknowledged', {'queue': 'conductor'}),
    ('verifier.tasks.blender_verification_order', {'queue': 'verifier'}),
],)
app.conf.task_default_queue = 'non_existing'
