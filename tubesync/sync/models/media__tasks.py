import os
from pathlib import Path
from shutil import copyfile
from common.logger import log
from common.errors import (
    NoMetadataException,
)
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from ..choices import Val, SourceResolution
from ..utils import write_text_file


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
    return True


def download_finished(self, format_str, container, downloaded_filepath=None):
    media = self
    if downloaded_filepath is None:
        downloaded_filepath = self.filepath
    filepath = Path(downloaded_filepath)

    # Media has been downloaded successfully
    log.info(f'Successfully downloaded media: {media} (UUID: {media.pk}) to: '
             f'"{filepath}"')
    # Link the media file to the object and update info about the download
    self.media_file.name = str(filepath.relative_to(self.media_file.storage.location))
    media.downloaded = True
    media.download_date = timezone.now()
    media.downloaded_filesize = os.path.getsize(filepath)
    media.downloaded_container = container
    if '+' in format_str:
        # Seperate audio and video streams
        vformat_code, aformat_code = format_str.split('+')
        aformat = media.get_format_by_code(aformat_code)
        vformat = media.get_format_by_code(vformat_code)
        media.downloaded_format = vformat['format']
        media.downloaded_height = vformat['height']
        media.downloaded_width = vformat['width']
        media.downloaded_audio_codec = aformat['acodec']
        media.downloaded_video_codec = vformat['vcodec']
        media.downloaded_container = container
        media.downloaded_fps = vformat['fps']
        media.downloaded_hdr = vformat['is_hdr']
    else:
        # Combined stream or audio-only stream
        cformat_code = format_str
        cformat = media.get_format_by_code(cformat_code)
        media.downloaded_audio_codec = cformat['acodec']
        if cformat['vcodec']:
            # Combined
            media.downloaded_format = cformat['format']
            media.downloaded_height = cformat['height']
            media.downloaded_width = cformat['width']
            media.downloaded_video_codec = cformat['vcodec']
            media.downloaded_fps = cformat['fps']
            media.downloaded_hdr = cformat['is_hdr']
        else:
            self.downloaded_format = Val(SourceResolution.AUDIO)


def copy_thumbnail(self):
    if not self.source.copy_thumbnails:
        return
    if not self.thumb_file_exists:
        from sync.tasks import delete_task_by_media, download_media_image
        args = ( str(self.pk), self.thumbnail, )
        if not args[1]:
            return
        delete_task_by_media('sync.tasks.download_media_thumbnail', args)
        if download_media_image.call_local(*args):
            self.refresh_from_db()
    if not self.thumb_file_exists:
        return
    log.info(
        'Copying media thumbnail'
        f' from: {self.thumb.path}'
        f' to: {self.thumbpath}'
    )
    # copyfile returns the destination, so we may as well pass that along
    return copyfile(self.thumb.path, self.thumbpath)


def write_nfo_file(self):
    if not self.source.write_nfo:
        return
    log.info(f'Writing media NFO file to: {self.nfopath}')
    try:
        # write_text_file returns bytes written
        return write_text_file(self.nfopath, self.nfoxml)
    except PermissionError as e:
        msg = (
            'A permissions problem occured when writing'
            ' the new media NFO file: {}'
        )
        log.exception(msg, e)


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

