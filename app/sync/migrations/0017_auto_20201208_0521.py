# Generated by Django 3.1.4 on 2020-12-08 05:21

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sync', '0016_auto_20201208_0518'),
    ]

    operations = [
        migrations.AlterField(
            model_name='source',
            name='source_resolution',
            field=models.CharField(choices=[('360p', '360p (SD)'), ('480p', '480p (SD)'), ('720p', '720p (HD)'), ('1080p', '1080p (Full HD)'), ('1440p', '1440p (2K)'), ('2160p', '2160p (4K)'), ('4320p', '4320p (8K)'), ('audio', 'Audio only')], db_index=True, default='1080p', help_text='Source resolution, desired video resolution to download', max_length=8, verbose_name='source resolution'),
        ),
    ]