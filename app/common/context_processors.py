from django.conf import settings


def app_details(request):
    return {
        'app_version': str(settings.VERSION)
    }
