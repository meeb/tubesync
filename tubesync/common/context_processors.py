from django.conf import settings


def app_details(request: object) -> dict:
    """
    Returns a dictionary containing application and third-party library versions.

    :param request: The current request object (not used in this function)
    :return: A dictionary with application and third-party library versions
    """
    return {
        "app_version": str(settings.VERSION),  # Convert VERSION to string
        "yt_dlp_version": yt_dlp_version,  # Imported from .third_party_versions
        "ffmpeg_version": ffmpeg_version,  # Imported from .third_party_versions
        "deno_version": deno_version,  # Imported from .third_party_versions
    }
