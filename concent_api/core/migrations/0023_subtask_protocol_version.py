# -*- coding: utf-8 -*-
# Generated by Django 1.11.13 on 2019-02-13 16:00
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0022_auto_20190129_1317'),
    ]

    operations = [
        migrations.AddField(
            model_name='subtask',
            name='protocol_version',
            field=models.CharField(max_length=10),
            preserve_default=False,
        ),
    ]
