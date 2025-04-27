# Hand-crafted data migration

from django.db import migrations
from common.utils import django_queryset_generator as qs_gen


def use_tables(apps, schema_editor):
    Media = apps.get_model('sync', 'Media')
    qs = Media.objects.filter(metadata__isnull=False)
    for media in qs_gen(qs):
        media.save_to_metadata('migrated', True)

def restore_metadata_column(apps, schema_editor):
    Media = apps.get_model('sync', 'Media')
    qs = Media.objects.filter(metadata__isnull=False)
    for media in qs_gen(qs):
        metadata = media.loaded_metadata
        del metadata['migrated']
        del metadata['_using_table']
        media.metadata = media.metadata_dumps(arg_dict=metadata)
        media.save()


class Migration(migrations.Migration):

    dependencies = [
        ('sync', '0031_squashed_metadata_metadataformat'),
    ]

    operations = [
        migrations.RunPython(
            code=use_tables,
            reverse_code=restore_metadata_column,
        ),
    ]

