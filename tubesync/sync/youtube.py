'''
    Wrapper for the yt-dlp library. Used so if there are any library interface
    updates we only need to udpate them in one place.
'''


import os

from collections import namedtuple
from common.logger import log
from copy import copy, deepcopy
from pathlib import Path

from django.conf import settings
from .utils import mkdir_p
import yt_dlp


_defaults = getattr(settings, 'YOUTUBE_DEFAULTS', {})
_youtubedl_cachedir = getattr(settings, 'YOUTUBE_DL_CACHEDIR', None)
if _youtubedl_cachedir:
    _youtubedl_cachedir = str(_youtubedl_cachedir)
    _defaults['cachedir'] = _youtubedl_cachedir
_youtubedl_tempdir = getattr(settings, 'YOUTUBE_DL_TEMPDIR', None)
if _youtubedl_tempdir:
    _youtubedl_tempdir = str(_youtubedl_tempdir)
    _youtubedl_tempdir_path = Path(_youtubedl_tempdir)
    mkdir_p(_youtubedl_tempdir_path)
    (_youtubedl_tempdir_path / '.ignore').touch(exist_ok=True)
    _paths = _defaults.get('paths', {})
    _paths.update({ 'temp': _youtubedl_tempdir, })
    _defaults['paths'] = _paths



class YouTubeError(yt_dlp.utils.DownloadError):
    '''
        Generic wrapped error for all errors that could be raised by youtube-dl.
    '''
    pass


def get_yt_opts():
    opts = copy(_defaults)
    cookie_file = settings.COOKIES_FILE
    if cookie_file.is_file():
        cookie_file_path = str(cookie_file.resolve())
        log.info(f'[youtube-dl] using cookies.txt from: {cookie_file_path}')
        opts.update({'cookiefile': cookie_file_path})
    return opts

def get_channel_id(url):
    # yt-dlp --simulate --no-check-formats --playlist-items 1
    #   --print 'pre_process:%(playlist_channel_id,playlist_id,channel_id)s'
    opts = get_yt_opts()
    opts.update({
        'skip_download': True,
        'simulate': True,
        'logger': log,
        'extract_flat': True,  # Change to False to get detailed info
        'check_formats': False,
        'playlist_items': '1',
    })

    with yt_dlp.YoutubeDL(opts) as y:
        try:
            response = y.extract_info(url, download=False)
        except yt_dlp.utils.DownloadError as e:
            raise YouTubeError(f'Failed to extract channel ID for "{url}": {e}') from e
        else:
            try:
                channel_id = response['channel_id']
            except Exception as e:
                raise YouTubeError(f'Failed to extract channel ID for "{url}": {e}') from e
            else:
                return channel_id

def get_channel_image_info(url):
    opts = get_yt_opts()
    opts.update({
        'skip_download': True,
        'simulate': True,
        'logger': log,
        'extract_flat': True,  # Change to False to get detailed info
    })

    with yt_dlp.YoutubeDL(opts) as y:
        try:
            response = y.extract_info(url, download=False)

            avatar_url = None
            banner_url = None
            for thumbnail in response['thumbnails']:
                if thumbnail['id'] == 'avatar_uncropped':
                    avatar_url = thumbnail['url']
                if thumbnail['id'] == 'banner_uncropped':
                    banner_url = thumbnail['url']
                if banner_url != None and avatar_url != None:
                    break

            return avatar_url, banner_url
        except yt_dlp.utils.DownloadError as e:
            raise YouTubeError(f'Failed to extract channel info for "{url}": {e}') from e


def _subscriber_only(msg='', response=None):
    if response is None:
        # process msg only
        msg = str(msg)
        if 'access to members-only content' in msg:
            return True
        if ': Join this channel' in msg:
            return True
        if 'Join this YouTube channel' in msg:
            return True
    else:
        # ignore msg entirely
        if not isinstance(response, dict):
            raise TypeError(f'response must be a dict, got "{type(response)}" instead')

        if 'availability' not in response.keys():
            return False

        # check for the specific expected value
        return 'subscriber_only' == response.get('availability')
    return False


def get_media_info(url):
    '''
        Extracts information from a YouTube URL and returns it as a dict. For a channel
        or playlist this returns a dict of all the videos on the channel or playlist
        as well as associated metadata.
    '''
    opts = get_yt_opts()
    opts.update({
        'ignoreerrors': False, # explicitly set this to catch exceptions
        'ignore_no_formats_error': False, # we must fail first to try again with this enabled
        'skip_download': True,
        'simulate': True,
        'logger': log,
        'extract_flat': True,
    })
    response = {}
    with yt_dlp.YoutubeDL(opts) as y:
        try:
            response = y.extract_info(url, download=False)
        except yt_dlp.utils.DownloadError as e:
            if not _subscriber_only(msg=e.msg):
                raise YouTubeError(f'Failed to extract_info for "{url}": {e}') from e
            # adjust options and try again
            opts.update({'ignore_no_formats_error': True,})
            with yt_dlp.YoutubeDL(opts) as yy:
                try:
                    response = yy.extract_info(url, download=False)
                except yt_dlp.utils.DownloadError as ee:
                    raise YouTubeError(f'Failed (again) to extract_info for "{url}": {ee}') from ee
                # validate the response is what we expected
                if not _subscriber_only(response=response):
                    response = {}

    if not response:
        raise YouTubeError(f'Failed to extract_info for "{url}": No metadata was '
                           f'returned by youtube-dl, check for error messages in the '
                           f'logs above. This task will be retried later with an '
                           f'exponential backoff.')
    return response


def download_media(url, media_format, extension, output_file, info_json,
                   sponsor_categories=None,
                   embed_thumbnail=False, embed_metadata=False, skip_sponsors=True,
                   write_subtitles=False, auto_subtitles=False, sub_langs='en'):
    '''
        Downloads a YouTube URL to a file on disk.
    '''

    def hook(event):
        filename = os.path.basename(event['filename'])

        if event.get('downloaded_bytes') is None or event.get('total_bytes') is None:
            return None

        if event['status'] == 'error':
            log.error(f'[youtube-dl] error occured downloading: {filename}')
        elif event['status'] == 'downloading':
            downloaded_bytes = event.get('downloaded_bytes', 0)
            total_bytes = event.get('total_bytes', 0)
            eta = event.get('_eta_str', '?').strip()
            percent_done = event.get('_percent_str', '?').strip()
            speed = event.get('_speed_str', '?').strip()
            total = event.get('_total_bytes_str', '?').strip()
            if downloaded_bytes > 0 and total_bytes > 0:
                p = round((event['downloaded_bytes'] / event['total_bytes']) * 100)
                if (p % 5 == 0) and p > hook.download_progress:
                    hook.download_progress = p
                    log.info(f'[youtube-dl] downloading: {filename} - {percent_done} '
                             f'of {total} at {speed}, {eta} remaining')
            else:
                # No progress to monitor, just spam every 10 download messages instead
                hook.download_progress += 1
                if hook.download_progress % 10 == 0:
                    log.info(f'[youtube-dl] downloading: {filename} - {percent_done} '
                                f'of {total} at {speed}, {eta} remaining')
        elif event['status'] == 'finished':
            total_size_str = event.get('_total_bytes_str', '?').strip()
            elapsed_str = event.get('_elapsed_str', '?').strip()
            log.info(f'[youtube-dl] finished downloading: {filename} - '
                     f'{total_size_str} in {elapsed_str}')
        else:
            log.warn(f'[youtube-dl] unknown event: {str(event)}')

    hook.download_progress = 0

    default_opts = yt_dlp.parse_options([]).options
    pp_opts = deepcopy(default_opts.__dict__)
    pp_opts.update({
        'embedthumbnail': embed_thumbnail,
        'addmetadata': embed_metadata,
        'addchapters': True,
        'embed_infojson': False,
        'force_keyframes_at_cuts': True,
    })

    if skip_sponsors:
        pp_opts['sponsorblock_mark'].update('all,-chapter'.split(','))
        pp_opts['sponsorblock_remove'].update(sponsor_categories or {})

    ytopts = {
        'format': media_format,
        'merge_output_format': extension,
        'outtmpl': os.path.basename(output_file),
        'quiet': False if settings.DEBUG else True,
        'verbose': True if settings.DEBUG else False,
        'noprogress': None if settings.DEBUG else True,
        'progress_hooks': [hook],
        'writeinfojson': info_json,
        'postprocessors': [],
        'writesubtitles': write_subtitles,
        'writeautomaticsub': auto_subtitles,
        'subtitleslangs': sub_langs.split(','),
    }
    opts = get_yt_opts()
    ytopts['paths'] = opts.get('paths', {})
    ytopts['paths'].update({
        'home': os.path.dirname(output_file),
    })

    codec_options = []
    ofn = os.path.basename(output_file)
    if 'av1-' in ofn:
        codec_options = ['-c:v', 'libsvtav1', '-preset', '8', '-crf', '35']
    elif 'vp9-' in ofn:
        codec_options = ['-c:v', 'libvpx-vp9', '-b:v', '0', '-crf', '31']
    ytopts['postprocessor_args'] = opts.get('postprocessor_args', {})
    set_ffmpeg_codec = not (
        ytopts['postprocessor_args'] and
        ytopts['postprocessor_args']['modifychapters+ffmpeg']
    )
    if set_ffmpeg_codec and codec_options:
        ytopts['postprocessor_args'].update({
            'modifychapters+ffmpeg': codec_options,
        })

    # clean-up incompatible keys
    pp_opts = {k: v for k, v in pp_opts.items() if not k.startswith('_')}

    # convert dict to namedtuple
    yt_dlp_opts = namedtuple('yt_dlp_opts', pp_opts)
    pp_opts = yt_dlp_opts(**pp_opts)

    # create the post processors list
    ytopts['postprocessors'] = list(yt_dlp.get_postprocessors(pp_opts))

    opts.update(ytopts)

    with yt_dlp.YoutubeDL(opts) as y:
        try:
            return y.download([url])
        except yt_dlp.utils.DownloadError as e:
            raise YouTubeError(f'Failed to download for "{url}": {e}') from e
    return False
