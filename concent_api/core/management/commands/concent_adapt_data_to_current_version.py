from logging import getLogger

from django.core.management.base import BaseCommand
from typing import Any

from common.helpers import deserialize_message
from core.models import StoredMessage
from core.models import Subtask

logger = getLogger(__name__)


class Command(BaseCommand):
    help = "Adapts whole database to current Concent's version"

    def handle(self, *args: Any, **options: Any) -> None:
        for subtask in Subtask.objects.all():
            try:
                report_computed_task =  deserialize_message(subtask.report_computed_task.data.tobytes())
                if not isinstance(report_computed_task.size, int):
                    delete_unsupported_messages(subtask.subtask_id)
            except:
                delete_unsupported_messages(subtask.subtask_id)


def delete_unsupported_messages(subtask_id: str) -> None:
    Subtask.objects.filter(subtask_id=subtask_id).delete()
    StoredMessage.objects.filter(subtask_id=subtask_id).delete()
    logger.info(f'Deleted subtask and all related messages with subtask_id: {subtask_id}')
