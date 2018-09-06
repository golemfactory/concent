from logging import getLogger
from typing import Any

from django.core.management.base import BaseCommand
from django.db.models import Q

from core.constants import REGEX_FOR_VALID_UUID
from core.models import StoredMessage
from core.models import Subtask

logger = getLogger(__name__)


class Command(BaseCommand):
    help = 'Removes Subtask and StoredMessage objects with subtask_id and task_id not matching UUID standard.'

    def handle(self, *args: Any, **options: Any) -> None:
        subtasks_deleted = Subtask.objects.exclude(
            Q(task_id__iregex=REGEX_FOR_VALID_UUID) |
            Q(subtask_id__iregex=REGEX_FOR_VALID_UUID)
        ).delete()
        stored_messages_deleted = StoredMessage.objects.exclude(
            Q(task_id__iregex=REGEX_FOR_VALID_UUID) |
            Q(subtask_id__iregex=REGEX_FOR_VALID_UUID)
        ).delete()
        logger.info(f'Deleted {subtasks_deleted[0]} subtasks and {stored_messages_deleted[0]} stored messages')
