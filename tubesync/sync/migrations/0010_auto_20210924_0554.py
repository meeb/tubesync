# Generated by Django 3.2.7 on 2021-09-24 05:54

import django.core.files.storage
from django.db import migrations, models
import sync.models


class Migration(migrations.Migration):

    dependencies = [
        ('sync', '0009_auto_20210218_0442'),
    ]

    operations = [
        migrations.AlterField(
            model_name='media',
            name='media_file',
            field=models.FileField(blank=True, help_text='Media file', max_length=255, null=True, storage=django.core.files.storage.FileSystemStorage(location='/home/meeb/Repos/github.com/meeb/tubesync/tubesync/downloads'), upload_to=sync.models.get_media_file_path, verbose_name='media file'),
        ),
        migrations.AlterField(
            model_name='source',
            name='index_schedule',
            field=models.IntegerField(choices=[(3600, 'Every hour'), (7200, 'Every 2 hours'), (10800, 'Every 3 hours'), (14400, 'Every 4 hours'), (18000, 'Every 5 hours'), (21600, 'Every 6 hours'), (43200, 'Every 12 hours'), (86400, 'Every 24 hours'), (259200, 'Every 3 days'), (604800, 'Every 7 days'), (0, 'Never')], db_index=True, default=86400, help_text='Schedule of how often to index the source for new media', verbose_name='index schedule'),
        ),
        migrations.AlterField(
            model_name='source',
            name='media_format',
            field=models.CharField(default='{yyyy_mm_dd}_{source}_{title}_{key}_{format}.{ext}', help_text='File format to use for saving files, detailed options at bottom of page.', max_length=200, verbose_name='media format'),
        ),
    ]
