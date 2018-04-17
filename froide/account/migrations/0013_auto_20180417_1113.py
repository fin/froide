# -*- coding: utf-8 -*-
# Generated by Django 1.11.12 on 2018-04-17 09:13
from __future__ import unicode_literals

from django.db import migrations, models
import froide.account.models
import froide.helper.storage


class Migration(migrations.Migration):

    dependencies = [
        ('account', '0012_application'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='profile_photo',
            field=models.ImageField(blank=True, null=True, storage=froide.helper.storage.HashedFilenameStorage(), upload_to=froide.account.models.profile_photo_path),
        ),
        migrations.AddField(
            model_name='user',
            name='profile_text',
            field=models.TextField(blank=True),
        ),
    ]
