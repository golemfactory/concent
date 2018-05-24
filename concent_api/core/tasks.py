import logging

from celery import shared_task


logger = logging.getLogger(__name__)


@shared_task
def upload_finished(_subtask_id: str):
    pass
