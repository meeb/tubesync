from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('sync', '0037_alter_source_fallback'),
    ]

    operations = [
        migrations.AddField(
            model_name='source',
            name='avatar_image_url',
            field=models.URLField(
                blank=True,
                help_text='Avatar image URL captured during indexing',
                null=True,
                verbose_name='avatar image URL',
            ),
        ),
        migrations.AddField(
            model_name='source',
            name='banner_image_url',
            field=models.URLField(
                blank=True,
                help_text='Banner image URL captured during indexing',
                null=True,
                verbose_name='banner image URL',
            ),
        ),
        migrations.AddField(
            model_name='source',
            name='thumbnail_image_url',
            field=models.URLField(
                blank=True,
                help_text='Thumbnail image URL captured during indexing',
                null=True,
                verbose_name='thumbnail image URL',
            ),
        ),
    ]
