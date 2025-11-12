from django.conf import settings
from .third_party_versions import yt_dlp_version, ffmpeg_version, deno_version


def app_details(request):
    return {
        'app_version': str(settings.VERSION),
        'yt_dlp_version': yt_dlp_version,
        'ffmpeg_version': ffmpeg_version,
        'deno_version': deno_version,
    }
