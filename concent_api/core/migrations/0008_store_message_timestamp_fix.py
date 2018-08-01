# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations

from common.helpers import deserialize_message
from common.helpers import parse_timestamp_to_utc_datetime


def switch_stored_message_timestamp_to_message_creation_time(apps, _schema_editor):
    StoredMessage = apps.get_model('core', 'StoredMessage')

    for stored_message in StoredMessage.objects.all():
        stored_message.timestamp = parse_timestamp_to_utc_datetime(
            deserialize_message(stored_message.data.tobytes()).timestamp
        )
        stored_message.full_clean()
        stored_message.save()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0007_auto_20180719_1241'),
    ]

    operations = [
        migrations.RunPython(
            switch_stored_message_timestamp_to_message_creation_time,
            reverse_code=migrations.RunPython.noop
        ),
    ]
