# -*- coding: utf-8 -*-
# Generated by Django 1.11.8 on 2017-12-22 08:44
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_auto_20171221_1618'),
    ]

    operations = [
        migrations.AddField(
            model_name='receiveoutofbandstatus',
            name='delivered',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='receivestatus',
            name='delivered',
            field=models.BooleanField(default=False),
        ),
    ]
