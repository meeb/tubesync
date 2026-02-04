from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('sync', '0036_alter_source_sponsorblock_categories'),
    ]

    operations = [
        migrations.AddField(
            model_name='source',
            name='include_shorts',
            field=models.BooleanField(
                default=False,
                help_text='Also sync Shorts for this channel (UC... IDs only, via its Shorts playlist)',
                verbose_name='include shorts',
            ),
        ),
        migrations.AddField(
            model_name='source',
            name='shorts_parent',
            field=models.ForeignKey(
                blank=True,
                help_text='Parent channel source for Shorts-derived playlists',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='shorts_children',
                to='sync.source',
            ),
        ),
    ]
