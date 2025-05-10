from pathlib import Path
from django.conf import settings
from django.core.files.storage import FileSystemStorage
from ..choices import Val, YouTube_SourceType


media_file_storage = FileSystemStorage(location=str(settings.DOWNLOAD_ROOT), base_url='/media-data/')
_srctype_dict = lambda n: dict(zip( YouTube_SourceType.values, (n,) * len(YouTube_SourceType.values) ))


def _nfo_element(nfo, label, text, /, *, attrs={}, tail='\n', char=' ', indent=2):
    element = nfo.makeelement(label, attrs)
    element.text = text
    element.tail = tail + (char * indent)
    return element


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

