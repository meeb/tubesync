from django.conf import settings
from .third_party_versions import youtube_dl_version, ffmpeg_version


def app_details(request):
    return {
        'app_version': str(settings.VERSION),
        'youtube_dl_version': youtube_dl_version,
        'ffmpeg_version': ffmpeg_version,
    }
