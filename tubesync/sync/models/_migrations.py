from pathlib import Path
from django.conf import settings
from django.core.files.storage import FileSystemStorage


media_file_storage = FileSystemStorage(location=str(settings.DOWNLOAD_ROOT), base_url='/media-data/')


def get_media_file_path(instance, filename):
    return instance.filepath


def get_media_thumb_path(instance, filename):
    # we don't want to use alternate names for thumb files
    if instance.thumb:
        instance.thumb.delete(save=False)
    fileid = str(instance.uuid).lower()
    filename = f'{fileid}.jpg'
    prefix = fileid[:2]
    return Path('thumbs') / prefix / filename

