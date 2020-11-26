from django.conf import settings
from youtube_dl import version as yt_version


def app_details(request):
    return {
        'app_version': str(settings.VERSION),
        'youtube_dl_version': str(yt_version.__version__)
    }
