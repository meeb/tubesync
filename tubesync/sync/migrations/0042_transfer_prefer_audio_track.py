# Fork reconciliation: the fork shipped this feature early as
# Source.prefer_audio_track ('original'/'default', migration 0039). Upstream later
# merged the same feature as Source.audio_track ('o'/'d'), which arrives here as
# 0041_source_audio_track. Copy any value a fork DB already stored, then drop the
# obsolete column.

from django.db import migrations


_FORWARD = {'original': 'o', 'default': 'd'}
_REVERSE = {'o': 'original', 'd': 'default'}


def copy_prefer_to_audio_track(apps, schema_editor):
    Source = apps.get_model('sync', 'Source')
    for pk, old in Source.objects.values_list('pk', 'prefer_audio_track'):
        new = _FORWARD.get(old, 'o')
        Source.objects.filter(pk=pk).update(audio_track=new)


def copy_audio_track_to_prefer(apps, schema_editor):
    Source = apps.get_model('sync', 'Source')
    for pk, new in Source.objects.values_list('pk', 'audio_track'):
        old = _REVERSE.get(new, 'original')
        Source.objects.filter(pk=pk).update(prefer_audio_track=old)


class Migration(migrations.Migration):

    dependencies = [
        ('sync', '0041_source_audio_track'),
    ]

    operations = [
        migrations.RunPython(
            copy_prefer_to_audio_track,
            copy_audio_track_to_prefer,
        ),
        migrations.RemoveField(
            model_name='source',
            name='prefer_audio_track',
        ),
    ]
