import os
import subprocess
from collections import defaultdict
from pathlib import Path, PurePosixPath
from shutil import copyfile
from tempfile import TemporaryDirectory
from urllib.parse import urlparse, urlunparse

from common.logger import log
from common.errors import (
    NoMetadataException,
)
from common.utils import multi_key_sort
from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from ..choices import Val, SourceResolution
from ..utils import filter_response, write_text_file


def copy_thumbnail(self):
    if not self.source.copy_thumbnails:
        return
    if not self.thumb_file_exists:
        from sync.tasks import download_media_image
        args = ( str(self.pk), self.thumbnail, )
        if not args[1]:
            return
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
    if downloaded_filepath is None:
        downloaded_filepath = self.filepath
    filepath = Path(downloaded_filepath)

    # Media has been downloaded successfully
    log.info(f'Successfully downloaded media: {self} (UUID: {self.pk}) to: '
             f'"{filepath}"')
    # Link the media file to the object and update info about the download
    self.media_file.name = str(filepath.relative_to(self.media_file.storage.location))
    self.downloaded = True
    self.download_date = timezone.now()
    self.downloaded_filesize = os.path.getsize(filepath)
    self.downloaded_container = container
    self.manual_skip = False
    self.skip = False
    if '+' in format_str:
        # Seperate audio and video streams
        vformat_code, aformat_code = format_str.split('+')
        aformat = self.get_format_by_code(aformat_code)
        vformat = self.get_format_by_code(vformat_code)
        self.downloaded_format = vformat['format']
        self.downloaded_height = vformat['height']
        self.downloaded_width = vformat['width']
        self.downloaded_audio_codec = aformat['acodec']
        self.downloaded_video_codec = vformat['vcodec']
        self.downloaded_fps = round(vformat['fps'])
        self.downloaded_hdr = vformat['is_hdr']
    else:
        # Combined stream or audio-only stream
        cformat_code = format_str
        cformat = self.get_format_by_code(cformat_code)
        self.downloaded_audio_codec = cformat['acodec']
        if cformat['vcodec']:
            # Combined
            self.downloaded_format = cformat['format']
            self.downloaded_height = cformat['height']
            self.downloaded_width = cformat['width']
            self.downloaded_video_codec = cformat['vcodec']
            self.downloaded_fps = round(cformat['fps'])
            self.downloaded_hdr = cformat['is_hdr']
        else:
            self.downloaded_format = Val(SourceResolution.AUDIO)
            self.downloaded_height = None
            self.downloaded_width = None
            self.downloaded_video_codec = None
            self.downloaded_fps = None
            self.downloaded_hdr = False


def download_thumbnails(self):
    # Format serialization functions mapped inside the registry
    def _format_as_string(urls, headers, rows) -> str:
        return '\n'.join(urls)

    FORMATTER_MAP = {
        'string': _format_as_string,
    }

    def get_youtube_thumbnails(video_id: str, output_format: str = 'string') -> str:
        """
            Generates and processes YouTube thumbnail URLs using urlunparse.
            Defaults to raw 'string' output, but can be extended.
        """
        scheme = 'https'
        hostname = 'i.ytimg.com'
        base_names = (
            'maxresdefault', 'sddefault', 'hqdefault', '1', '2', '3',
            'oardefault', 'oar1', 'oar2', 'oar3',
        )

        urls = []
        for name in base_names:
            # Construct full clean URLs directly using urlunparse tuples
            # Tuple format: (scheme, netloc, path, params, query, fragment)
            jpg = urlunparse((scheme, hostname, f'/vi/{video_id}/{name}.jpg', '', '', ''))
            webp = urlunparse((scheme, hostname, f'/vi_webp/{video_id}/{name}.webp', '', '', ''))

            urls.extend((jpg, webp))

        headers = ('Scheme', 'Hostname', 'Path', 'Filename')
        rows = []
        for url in urls:
            parsed = urlparse(url)
            rows.append((
                parsed.scheme,
                parsed.hostname,
                parsed.path,
                PurePosixPath(parsed.path).name,
            ))

        fmt = output_format.lower().strip()
        if fmt not in FORMATTER_MAP:
            raise ValueError(f'Unsupported format "{output_format}".')

        return FORMATTER_MAP[fmt](urls, headers, rows)

    def export_urls_to_temp_file(video_id: str) -> str:
        """Writes URLs.txt using the default 'string' configuration."""

        prefix = f'i.ytimg.com-thumbnails-[{video_id}]-'
        with TemporaryDirectory(prefix=prefix, delete=False) as temp_dir:
            file_path = Path(temp_dir) / 'URLs.txt'
            with open(file_path, 'w') as f:
                f.write(get_youtube_thumbnails(video_id))
                f.write('\n')

        return file_path

    def download_thumbnails_parallel(video_id: str, max_connections: int = 2) -> tuple[os.DirEntry,...]:
        """
            Executes high-performance parallel downloads via curl.
            Attempts all URLs, but strictly skips writing files for any 404 responses.
        """

        file_path = Path(export_urls_to_temp_file(video_id))
        temp_dir = file_path.parent

        curl_command = (
            'curl',
            '--parallel', '--parallel-immediate',
            '--parallel-max-host', str(max_connections),
            '--remote-time', '--remote-name-all',
            '--fail', '--verbose',
            '--show-error', '--show-headers',
            '--dump-header', 'curl.header.log.txt',
            '--stderr', 'curl.stderr.log.txt',
            '--url', f'@{file_path.name}',
        )

        try:
            subprocess.run(
                curl_command,
                cwd=str(temp_dir),
                check=False,
                capture_output=True,
                text=True,
            )

            downloaded_files = tuple(
                e for e in os.scandir(temp_dir)
                if (e.path := Path(e.path)).suffix in ('.jpg', '.webp') and e.is_file() and 0 < e.stat().st_size
            )

            log.debug(f'Parallel download pass completed. Successfully stored {len(downloaded_files)} valid files.')
  
            return downloaded_files

        except FileNotFoundError:
            raise RuntimeError("Missing dependencies: 'curl' executable was not found on your system environment PATH.")

    entries = download_thumbnails_parallel(self.key, 4)
    thumb_path = None
    for e in entries:
        if not thumb_path or ('.jpg' == e.path.suffix and e.stat().st_size > thumb_path.stat().st_size):
            thumb_path = e

    return thumb_path.path


def failed_format(self, format_str, /, *, cause=None, exc=None):
    if not self.has_metadata:
        return
    t = format_str.partition('+')
    data = self.loaded_metadata
    field = self.get_metadata_field('formats')
    formats = data.get(field, list())
    new_formats = [
        f
        for f in formats
        if f.get('format_id') not in (t[0],)
    ]
    self.save_to_metadata(field, new_formats)


def refresh_formats(self):
    if not self.has_metadata:
        return (None, False, 'missing metadata') # save, retry, msg
    data = self.loaded_metadata
    metadata_seconds = data.get('epoch', None)
    if not metadata_seconds:
        self.metadata_clear(save=True)
        return (None, False, 'invalid metadata was removed')

    now = timezone.now()
    attempted_key = '_refresh_formats_attempted'
    attempted_seconds = data.get(attempted_key)
    if attempted_seconds:
        # skip for recent unsuccessful refresh attempts also
        attempted_dt = self.ts_to_dt(attempted_seconds)
        if (now - attempted_dt) < timezone.timedelta(seconds=self.source.index_schedule // 3):
            return (False, None, 'already attempted recently')
    # skip for recent successful formats refresh
    refreshed_key = 'formats_epoch'
    formats_seconds = data.get(refreshed_key, metadata_seconds)
    metadata_dt = self.ts_to_dt(formats_seconds)
    if (now - metadata_dt) < timezone.timedelta(seconds=self.source.index_schedule):
        return (False, False, 'already recently completed')

    last_attempt = round((now - self.posix_epoch).total_seconds())
    self.save_to_metadata(attempted_key, last_attempt)
    self.skip = False
    metadata = self.index_metadata()
    if self.skip:
        return (False, True, 'found no formats; trying again')

    fmt_dict = defaultdict(str)
    response = metadata
    if getattr(settings, 'SHRINK_NEW_MEDIA_METADATA', False):
        response = filter_response(metadata, True)

    # save the new list of thumbnails
    thumbnails = self.get_metadata_first_value(
        'thumbnails',
        self.get_metadata_first_value('thumbnails', []),
        arg_dict=response,
    )
    field = self.get_metadata_field('thumbnails')
    self.save_to_metadata(field, thumbnails)
    fmt_dict['t'] = 'thumbnails'
    fmt_dict['s'] = ' and '

    # select and save our best thumbnail url
    try:
        thumbnail = [ thumb.get('url') for thumb in multi_key_sort(
            thumbnails,
            [('preference', True,)],
        ) if thumb.get('url', '').endswith('.jpg') ][0]
    except IndexError:
        pass
    else:
        field = self.get_metadata_field('thumbnail')
        self.save_to_metadata(field, thumbnail)
        fmt_dict['j'] = ', and '
        fmt_dict['s'] = '; '
        fmt_dict['t'] = 'thumbnail' + fmt_dict['j'] + fmt_dict['t']
        fmt_dict['j'] = ', '

    field = self.get_metadata_field('formats')
    self.save_to_metadata(field, response.get(field, []))
    self.save_to_metadata(refreshed_key, response.get('epoch', formats_seconds))
    if data.get('availability', 'public') != response.get('availability', 'public'):
        self.save_to_metadata('availability', response.get('availability', 'public'))
        fmt_dict['a'] = 'availability'
        fmt_dict['j'] = ', and ' if 'thumbnails' == fmt_dict['t'] else ', '
        fmt_dict['s'] = '; '
    return (True, False, 'updated formats{s}{a}{j}{t}'.format(**{k:fmt_dict[k] for k in 'sajt'}))


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


