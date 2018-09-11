from typing import Any

from logging import getLogger

from django.core.management.base import BaseCommand

from common.helpers import deserialize_message
from core.models import StoredMessage
from core.models import Subtask

from golem_messages.exceptions import MessageError


logger = getLogger(__name__)


class Command(BaseCommand):
    help = "Removes Subtasks which related ReportComputedTask cannot be deserialized or its size field is not int."

    def handle(self, *args: Any, **options: Any) -> None:
        for subtask in Subtask.objects.all():
            try:
                report_computed_task = deserialize_message(subtask.report_computed_task.data.tobytes())
                if not isinstance(report_computed_task.size, int):
                    delete_unsupported_messages(subtask.subtask_id)
            except MessageError as golem_messages_exception:
                logger.info(f'During message deserialization exception raised: {golem_messages_exception}')
                delete_unsupported_messages(subtask.subtask_id)


def delete_unsupported_messages(subtask: Subtask) -> None:
    subtask_id = subtask.subtask_id
    StoredMessage.objects.filter(subtask_id=subtask_id).delete()
    subtask.delete()
    logger.info(f'Deleted subtask and all related messages with subtask_id: {subtask_id}')
