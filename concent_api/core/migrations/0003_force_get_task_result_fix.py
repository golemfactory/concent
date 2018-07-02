# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations
from django.utils.timezone import now

from common.helpers import deserialize_message
from golem_messages.message.concents import ForceGetTaskResult


def insert_force_get_task_result_if_empty(apps, _schema_editor):
    Subtask = apps.get_model('core', 'Subtask')
    StoredMessage = apps.get_model('core', 'StoredMessage')

    for subtask in Subtask.objects.filter(force_get_task_result__isnull=True):
        report_computed_task_serialized = subtask.report_computed_task
        force_get_task_result = ForceGetTaskResult(
            report_computed_task=deserialize_message(report_computed_task_serialized.data.tobytes())
        )

        stored_message = StoredMessage(
            type=force_get_task_result.TYPE,
            timestamp=now(),
            data=force_get_task_result.serialize(),
            task_id=subtask.task_id,
            subtask_id=subtask.subtask_id,
        )
        stored_message.full_clean()
        stored_message.save()

        subtask.force_get_task_result = stored_message
        subtask.full_clean()
        subtask.save()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_subtask_force_get_task_result'),
    ]

    operations = [
        migrations.RunPython(
            insert_force_get_task_result_if_empty,
            reverse_code=migrations.RunPython.noop
        ),
    ]
