from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('sync', '0024_auto_20240717_1535'),
    ]

    operations = [
        migrations.AddField(
            model_name='source',
            name='index_videos',
            field=models.BooleanField(default=True, help_text='Index video media from this source', verbose_name='index videos'),
        ),
        migrations.AddField(
            model_name='source',
            name='index_streams',
            field=models.BooleanField(default=False, help_text='Index live stream media from this source', verbose_name='index streams'),
        ),
    ]