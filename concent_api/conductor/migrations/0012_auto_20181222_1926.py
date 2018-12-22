# -*- coding: utf-8 -*-
# Generated by Django 1.11.13 on 2018-12-22 19:26
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('conductor', '0011_auto_20181107_1226'),
    ]

    operations = [
        migrations.AlterField(
            model_name='blendersubtaskdefinition',
            name='output_format',
            field=models.CharField(choices=[('JPEG', 'jpeg'), ('PNG', 'png'), ('EXR', 'exr')], max_length=32),
        ),
    ]