# data migration added manually by: tcely

from uuid import UUID
from django.db import migrations

subtitle_codecs = [
    {
        'uuid': UUID('07f0e7df-75e6-4b07-9430-5332e5207c67'),
        'codec': 'vtt', 'description': 'Web Video Text Tracks',
    },
    {
        'uuid': UUID('426e8edc-daf2-48b3-b44d-a18fd7bb68d0'),
        'codec': 'ttml', 'description': 'Timed Text Markup Language',
    },
    {
        'uuid': UUID('019b1fdd-a031-4491-99eb-fb3418b92ce2'),
        'codec': 'srt', 'description': 'SubRip Text',
    },
    {
        'uuid': UUID('d73a36e5-372d-46d4-9f84-a9f6d19b6646'),
        'codec': 'ass', 'description': 'Advanced SubStation Alpha',
    },
    {
        'uuid': UUID('bd0fb776-15e4-43a6-86dc-3c39a89a3cfe'),
        'codec': 'ssa', 'description': 'SubStation Alpha',
    },
    {
        'uuid': UUID('3395bc25-2bc9-4e0d-9943-60e3d2572abb'),
        'codec': 'scc', 'description': 'Scenarist Closed Caption',
    },
    {
        'uuid': UUID('4027ecfd-6c1c-43d0-b37c-add5f516b629'),
        'codec': 'sbv', 'description': 'SubViewer',
    },
    {
        'uuid': UUID('383b89a9-06fc-48aa-bd77-f87cd4cee211'),
        'codec': 'json3', 'description': 'YouTube (proprietary) Timed Text Markup Language',
    },
    {
        'uuid': UUID('475c7470-6af0-49f9-ad15-11ffc2eecd5e'),
        'codec': 'srv3', 'description': 'YouTube (proprietary) Timed Text Markup Language',
    },
    {
        'uuid': UUID('1ccd5388-f64c-4ccf-9ec8-5474e9843c30'),
        'codec': 'srv2', 'description': 'YouTube (proprietary) Timed Text Markup Language',
    },
    {
        'uuid': UUID('f15d5d2a-0a49-4146-8707-91d3bb1930bc'),
        'codec': 'srv1', 'description': 'YouTube (proprietary) Timed Text Markup Language',
    }
]

def create_codecs(query_set, arg_dict):
    return query_set.bulk_create(
        [ query_set.model(**d) for d in arg_dict ],
        update_conflicts=True,
        update_fields=['description'],
        unique_fields=['asset_type', 'codec'],
    )

def add_subtitle_codecs(manager, db_alias):
    qs = manager.using(db_alias)
    for d in subtitle_codecs:
        d['asset_type'] = 'subtitle'
    create_codecs(qs, subtitle_codecs)

def forwards_func(apps, schema_editor):
    # We get the model from the versioned app registry;
    # if we directly import it, it'll be the wrong version.
    Codec = apps.get_model("sync", "Codec")
    db_alias = schema_editor.connection.alias
    add_subtitle_codecs(Codec.objects, db_alias)

def reverse_func(apps, schema_editor):
    # Delete the rows added by `forwards_func`.
    Codec = apps.get_model("sync", "Codec")
    db_alias = schema_editor.connection.alias
    # Delete the subtitle codecs.
    Codec.objects.using(db_alias).filter(
        asset_type='subtitle',
        codec__in=[ d['codec'] for d in subtitle_codecs ],
    ).delete()

class Migration(migrations.Migration):

    dependencies = [
        ('sync', '0038_codec'),
    ]

    operations = [
        migrations.RunPython(forwards_func, reverse_func),
    ]

