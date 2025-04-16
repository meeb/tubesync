# Generated by Django 5.1.8 on 2025-04-11 07:36

import django.db.models.deletion
import sync.models
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sync', '0030_alter_source_source_vcodec'),
    ]

    operations = [
        migrations.CreateModel(
            name='Metadata',
            fields=[
                ('uuid', models.UUIDField(default=uuid.uuid4, editable=False, help_text='UUID of the metadata', primary_key=True, serialize=False, verbose_name='uuid')),
                ('site', models.CharField(blank=True, default='Youtube', help_text='Site from which the metadata was retrieved', max_length=256, verbose_name='site')),
                ('key', models.CharField(blank=True, default='', help_text='Media identifier at the site from which the metadata was retrieved', max_length=256, verbose_name='key')),
                ('created', models.DateTimeField(auto_now_add=True, db_index=True, help_text='Date and time the metadata was created', verbose_name='created')),
                ('retrieved', models.DateTimeField(auto_now_add=True, db_index=True, help_text='Date and time the metadata was retrieved', verbose_name='retrieved')),
                ('uploaded', models.DateTimeField(help_text='Date and time the media was uploaded', null=True, verbose_name='uploaded')),
                ('published', models.DateTimeField(help_text='Date and time the media was published', null=True, verbose_name='published')),
                ('value', models.JSONField(default=dict, encoder=sync.models.JSONEncoder, help_text='JSON metadata object', verbose_name='value')),
                ('media', models.OneToOneField(help_text='Media the metadata belongs to', on_delete=django.db.models.deletion.CASCADE, parent_link=False, related_name='new_metadata', to='sync.media')),
            ],
            options={
                'verbose_name': 'Metadata about a Media item',
                'verbose_name_plural': 'Metadata about a Media item',
                'unique_together': {('media', 'site', 'key')},
            },
        ),
        migrations.CreateModel(
            name='MetadataFormat',
            fields=[
                ('uuid', models.UUIDField(default=uuid.uuid4, editable=False, help_text='UUID of the format', primary_key=True, serialize=False, verbose_name='uuid')),
                ('site', models.CharField(blank=True, default='Youtube', help_text='Site from which the format is available', max_length=256, verbose_name='site')),
                ('key', models.CharField(blank=True, default='', help_text='Media identifier at the site for which this format is available', max_length=256, verbose_name='key')),
                ('number', models.PositiveIntegerField(help_text='Ordering number for this format', verbose_name='number')),
                ('code', models.CharField(blank=True, default='', help_text='Format identification code', max_length=64, verbose_name='code')),
                ('value', models.JSONField(default=dict, encoder=sync.models.JSONEncoder, help_text='JSON metadata format object', verbose_name='value')),
                ('metadata', models.ForeignKey(help_text='Metadata the format belongs to', on_delete=django.db.models.deletion.CASCADE, related_name='metadataformat', to='sync.metadata')),
            ],
            options={
                'verbose_name': 'Format from the Metadata about a Media item',
                'verbose_name_plural': 'Formats from the Metadata about a Media item',
                'unique_together': {('metadata', 'site', 'key', 'code'), ('metadata', 'site', 'key', 'number')},
            },
        ),
    ]
