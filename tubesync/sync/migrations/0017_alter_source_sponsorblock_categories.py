# Generated by Django 3.2.18 on 2023-02-20 02:23

from django.db import migrations
import sync.fields


class Migration(migrations.Migration):

    dependencies = [
        ('sync', '0016_auto_20230214_2052'),
    ]

    operations = [
        migrations.AlterField(
            model_name='source',
            name='sponsorblock_categories',
            field=sync.fields.CommaSepChoiceField(default='all', help_text='Select the sponsorblocks you want to enforce', separator=''),
        ),
    ]
