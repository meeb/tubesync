from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sync', '0037_source_include_shorts_and_parent'),
    ]

    operations = [
        migrations.AddField(
            model_name='source',
            name='auto_quality',
            field=models.BooleanField(
                default=False,
                help_text='Automatically select the best available audio/video quality',
                verbose_name='auto quality',
            ),
        ),
    ]
