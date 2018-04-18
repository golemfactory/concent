# -*- coding: utf-8 -*-
# Generated by Django 1.11.9 on 2018-04-18 12:54
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0013_auto_20180315_1648'),
    ]

    operations = [
        migrations.AlterField(
            model_name='paymentinfo',
            name='amount_paid',
            field=models.IntegerField(),
        ),
        migrations.AlterField(
            model_name='paymentinfo',
            name='amount_pending',
            field=models.IntegerField(),
        ),
        migrations.AlterField(
            model_name='paymentinfo',
            name='provider_eth_account',
            field=models.CharField(max_length=42),
        ),
        migrations.AlterField(
            model_name='paymentinfo',
            name='task_owner_key',
            field=models.CharField(max_length=128),
        ),
    ]
