# Generated for the fork: audio-only direct downloads (Weg B).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sync', '0039_source_prefer_audio_track'),
    ]

    operations = [
        migrations.AddField(
            model_name='directdownloadjob',
            name='audio',
            field=models.BooleanField(default=False, verbose_name='audio only'),
        ),
        migrations.AddField(
            model_name='directdownloadjob',
            name='acodec',
            field=models.CharField(default='opus', max_length=8, verbose_name='audio codec'),
        ),
    ]
