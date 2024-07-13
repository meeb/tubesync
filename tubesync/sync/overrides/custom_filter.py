"""
    This file can be overridden with a docker volume to allow specifying a custom filter function to call. This allows
    for higher order filtering for those that really want advanced controls, without exposing the web interface to
    potential RCE issues.

    You are simply provided with an instance of Media, and need to return True to skip it, or False to allow it to be
    downloaded.

    To use this custom file, download this file and modify the function to do your check for skipping a media item.
    Then use docker volumes to override /app/sync/overrides/ with your custom file (it must be called
    `custom_filter.py`)
    e.g. your `docker run` could have `-v /some/directory/tubesync-overrides:/app/sync/overrides`
    or docker-compose could have
        volumes:
            - /some/directory/tubesync-overrides:/app/sync/overrides


    The logic is that if any condition marks an item to be skipped, it will be skipped. To save resources, this
    custom filter won't be called if any other filter as already marked it to be skipped
"""

from ..models import Media
from common.logger import log


def filter_custom(instance: Media) -> bool:
    # Return True to skip, or False to allow the media item to be downloaded

    # Put your conditional logic here
    if False:
        # It's in your best interest to log when skipping, so you can look at the logs and see why your media isn't
        # downloading
        log.info(
            f"Media: {instance.source} / {instance} has met some custom condition. Marking to be skipped"
        )
        return True

    # Return False if we aren't skipping the media
    return False
