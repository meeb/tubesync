import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sync', '0037_alter_source_fallback'),
    ]

    operations = [
        migrations.CreateModel(
            name='DirectDownloadJob',
            fields=[
                ('uuid', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False, verbose_name='uuid')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='updated at')),
                ('status', models.CharField(choices=[('running', 'Running'), ('done', 'Done'), ('stopped', 'Stopped'), ('error', 'Error')], db_index=True, default='running', max_length=10, verbose_name='status')),
                ('playlists', models.JSONField(default=list, verbose_name='playlists')),
                ('resolution', models.CharField(default='1080p', max_length=8, verbose_name='resolution')),
                ('cursor_playlist', models.PositiveIntegerField(default=0, verbose_name='cursor playlist')),
                ('cursor_video', models.PositiveIntegerField(default=0, verbose_name='cursor video')),
                ('total', models.PositiveIntegerField(default=0, verbose_name='total')),
                ('completed', models.PositiveIntegerField(default=0, verbose_name='completed')),
                ('failed', models.PositiveIntegerField(default=0, verbose_name='failed')),
                ('playlists_done', models.PositiveIntegerField(default=0, verbose_name='playlists done')),
                ('current', models.JSONField(blank=True, default=None, null=True, verbose_name='current')),
                ('log', models.JSONField(default=list, verbose_name='log')),
                ('stop_requested', models.BooleanField(default=False, verbose_name='stop requested')),
            ],
            options={
                'verbose_name': 'Direct Download Job',
                'verbose_name_plural': 'Direct Download Jobs',
                'ordering': ['-created_at'],
            },
        ),
    ]
