import django
import os
import sys

from django.db import transaction
from logging import getLogger

from common.helpers import deserialize_message

from golem_messages.exceptions import MessageError

sys.path.append('concent_api')
os.environ['DJANGO_SETTINGS_MODULE'] = "concent_api.settings"
django.setup()

from core.models import StoredMessage  # noqa E402
from core.models import Subtask  # noqa E402

logger = getLogger(__name__)


def main() -> None:
    with transaction.atomic(using='control'):
        for subtask in Subtask.objects.select_for_update().all():
            try:
                report_computed_task = deserialize_message(subtask.report_computed_task.data.tobytes())
                if isinstance(report_computed_task.size, int):
                    logger.info(f'Size inside ReportComputedTask message inside subtask with subtask_id: {subtask.subtask_id} is: {report_computed_task.size}')
                    delete_unsupported_messages(subtask)
            except MessageError as golem_messages_exception:
                logger.info(f'During message deserialization exception raised: {golem_messages_exception}')
                delete_unsupported_messages(subtask)


def delete_unsupported_messages(subtask: Subtask) -> None:
    StoredMessage.objects.filter(subtask_id=subtask.subtask_id).delete()
    logger.info(f'Deleted subtask and all related messages with subtask_id: {subtask.subtask_id}')


if __name__ == '__main__':
    main()
