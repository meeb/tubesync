from django.conf import settings
from django.core.files.storage import FileSystemStorage
from ..choices import Val, YouTube_SourceType


media_file_storage = FileSystemStorage(location=str(settings.DOWNLOAD_ROOT), base_url='/media-data/')
_srctype_dict = lambda n: dict(zip( YouTube_SourceType.values, (n,) * len(YouTube_SourceType.values) ))

