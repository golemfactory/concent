import os
from celery import Celery, signals
from kombu import Queue

@signals.setup_logging.connect
def on_celery_setup_logging(**kwargs):
    pass

# set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'concent_api.settings')


app = Celery('concent_api')

# Using a string here means the worker does not have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object('django.conf:settings', namespace = 'CELERY')

app.conf.task_create_missing_queues = False

app.conf.task_queues = (
    Queue('concent'),
    Queue('conductor'),
    Queue('verifier'),
)

app.conf.task_routes = ([
    ('core.tasks.verification_result', {'queue': 'concent'}),
    ('core.tasks.upload_finished', {'queue': 'concent'}),
    ('core.tasks.result_upload_finished', {'queue': 'concent'}),
    ('conductor.tasks.blender_verification_request', {'queue': 'conductor'}),
    ('conductor.tasks.result_transfer_request', {'queue': 'conductor'}),
    ('conductor.tasks.upload_acknowledged', {'queue': 'conductor'}),
    ('verifier.tasks.blender_verification_order', {'queue': 'verifier'}),
],)
app.conf.task_default_queue = 'concent'
