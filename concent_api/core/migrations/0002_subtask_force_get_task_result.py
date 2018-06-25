# -*- coding: utf-8 -*-
# Generated by Django 1.11.9 on 2018-06-20 23:41
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='subtask',
            name='force_get_task_result',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='subtasks_for_force_get_task_result', to='core.StoredMessage'),
        ),
    ]