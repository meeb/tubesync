from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('sync', '0022_add_delete_files_on_disk'),
    ]

    operations = [
        migrations.AddField(
            model_name='media',
            name='title',
            field=models.CharField(
                verbose_name='title',
                max_length=100,
                blank=True,
                null=False,
                default='',
                help_text='Video title'
            ),
        ),
        migrations.AddField(
            model_name='media',
            name='duration',
            field=models.PositiveIntegerField(
                verbose_name='duration',
                blank=True,
                null=True,
                help_text='Duration of media in seconds'
            ),
        ),
        migrations.AddField(
            model_name='source',
            name='filter_seconds',
            field=models.PositiveIntegerField(
                verbose_name='filter seconds',
                blank=True,
                null=True,
                help_text='Filter Media based on Min/Max duration. Leave blank or 0 to disable filtering'
            ),
        ),
        migrations.AddField(
            model_name='source',
            name='filter_seconds_min',
            field=models.BooleanField(
                verbose_name='filter seconds min/max',
                choices=[(True, 'Minimum Length'), (False, 'Maximum Length')],
                default=True,
                help_text='When Filter Seconds is > 0, do we skip on minimum (video shorter than limit) or maximum ('
                          'video greater than maximum) video duration'
            ),
        ),
    ]
