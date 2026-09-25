# Generated migration for the Subtitle model (issue #1453)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sync', '0039_codec_data'),
    ]

    operations = [
        migrations.CreateModel(
            name='Subtitle',
            fields=[
                ('id', models.AutoField(
                    auto_created=True, primary_key=True, serialize=False, verbose_name='ID',
                    ),
                ),
                ('extension', models.CharField(
                    help_text='The file extension of the subtitle (e.g. vtt, srt)',
                    max_length=8,
                    verbose_name='extension',
                    ),
                ),
                ('language', models.CharField(
                    help_text='BCP-47 language tag of the subtitle track (e.g. en-US)',
                    max_length=16,
                    verbose_name='language',
                    ),
                ),
                ('original_language', models.CharField(
                    blank=False,
                    default=None,
                    help_text='BCP-47 language tag of the source language, or NULL if unknown',
                    max_length=16,
                    null=True,
                    verbose_name='original language',
                    ),
                ),
                ('machine_generated', models.BooleanField(
                    default=False,
                    help_text='Whether the subtitle was automatically generated',
                    verbose_name='machine generated',
                    ),
                ),
                ('codec', models.ForeignKey(
                    help_text='The codec used for this subtitle track',
                    null=True,
                    on_delete=models.deletion.SET_NULL,
                    related_name='subtitles',
                    to='sync.codec',
                    ),
                ),
            ],
            options={
                'verbose_name': 'Subtitle',
                'verbose_name_plural': 'Subtitles',
                'unique_together': {('language', 'extension')},
            },
        ),
    ]

