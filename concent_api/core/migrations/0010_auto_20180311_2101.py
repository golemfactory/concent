# -*- coding: utf-8 -*-
# Generated by Django 1.11.9 on 2018-03-11 21:01
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0009_auto_20180309_1642'),
    ]

    operations = [
        migrations.AlterField(
            model_name='subtask',
            name='state',
            field=models.CharField(choices=[('FORCING_REPORT', 'forcing_report'), ('REPORTED', 'reported'), ('FORCING_RESULT_TRANSFER', 'forcing_result_transfer'), ('RESULT_UPLOADED', 'result_uploaded'), ('FORCING_ACCEPTANCE', 'forcing_acceptance'), ('REJECTED', 'rejected'), ('VERIFICATION_FILE_TRANSFER', 'verification_file_transfer'), ('ADDITIONAL_VERIFICATION', 'additional_verification'), ('ACCEPTED', 'accepted'), ('FAILED', 'failed')], max_length=32),
        ),
    ]
