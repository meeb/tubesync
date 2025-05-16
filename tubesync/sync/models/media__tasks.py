from common.logger import log
from common.errors import (
    NoMetadataException,
)
from django.utils import timezone


def download_checklist(self, skip_checks=False):
    media = self
    if skip_checks:
        return True

    if not media.source.download_media:
        log.warn(f'Download task triggered for media: {media} (UUID: {media.pk}) but '
                 f'the source {media.source} has since been marked to not download, '
                 f'not downloading')
        return False
    if media.skip or media.manual_skip:
        # Media was toggled to be skipped after the task was scheduled
        log.warn(f'Download task triggered for media: {media} (UUID: {media.pk}) but '
                 f'it is now marked to be skipped, not downloading')
        return False
    # metadata is required to generate the proper filepath
    if not media.has_metadata:
        raise NoMetadataException('Metadata is not yet available.')
    downloaded_file_exists = (
        media.downloaded and
        media.has_metadata and
        (
            media.media_file_exists or
            media.filepath.exists()
        )
    )
    if downloaded_file_exists:
        # Media has been marked as downloaded before the download_media task was fired,
        # skip it
        log.warn(f'Download task triggered for media: {media} (UUID: {media.pk}) but '
                 f'it has already been marked as downloaded, not downloading again')
        return False
    max_cap_age = media.source.download_cap_date
    published = media.published
    if max_cap_age and published:
        if published <= max_cap_age:
            log.warn(f'Download task triggered media: {media} (UUID: {media.pk}) but '
                     f'the source has a download cap and the media is now too old, '
                     f'not downloading')
            return False


def wait_for_premiere(self):
    hours = lambda td: 1+int((24*td.days)+(td.seconds/(60*60)))

    in_hours = None
    if self.has_metadata or not self.published:
        return (False, in_hours,)

    now = timezone.now()
    if self.published < now:
        in_hours = 0
        self.manual_skip = False
        self.skip = False
    else:
        in_hours = hours(self.published - now)
        self.manual_skip = True
        self.title = _(f'Premieres in {in_hours} hours')

    return (True, in_hours,)

