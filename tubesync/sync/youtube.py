'''
    Wrapper for the youtube-dl library. Used so if there are any library interface
    updates we only need to udpate them in one place.
'''


import os
from django.conf import settings
from copy import copy
from common.logger import log
import yt_dlp


_youtubedl_cachedir = getattr(settings, 'YOUTUBE_DL_CACHEDIR', None)
_defaults = getattr(settings, 'YOUTUBE_DEFAULTS', {})
if _youtubedl_cachedir:
    _youtubedl_cachedir = str(_youtubedl_cachedir)
    _defaults['cachedir'] = _youtubedl_cachedir



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


def get_media_info(url):
    '''
        Extracts information from a YouTube URL and returns it as a dict. For a channel
        or playlist this returns a dict of all the videos on the channel or playlist
        as well as associated metadata.
    '''
    opts = get_yt_opts()
    opts.update({
        'skip_download': True,
        'forcejson': True,
        'simulate': True,
        'logger': log,
        'extract_flat': True,
    })
    response = {}
    with yt_dlp.YoutubeDL(opts) as y:
        try:
            response = y.extract_info(url, download=False)
        except yt_dlp.utils.DownloadError as e:
            raise YouTubeError(f'Failed to extract_info for "{url}": {e}') from e
    if not response:
        raise YouTubeError(f'Failed to extract_info for "{url}": No metadata was '
                           f'returned by youtube-dl, check for error messages in the '
                           f'logs above. This task will be retried later with an '
                           f'exponential backoff.')
    return response


def download_media(url, media_format, extension, output_file, info_json, sponsor_categories="all", embed_thumbnail=False, embed_metadata=False, skip_sponsors=True):
    '''
        Downloads a YouTube URL to a file on disk.
    '''

    def hook(event):
        filename = os.path.basename(event['filename'])
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

    ytopts = {
        'format': media_format,
        'merge_output_format': extension,
        'outtmpl': output_file,
        'quiet': True,
        'progress_hooks': [hook],
        'writeinfojson': info_json,
        'postprocessors': []
    }
    sbopt = {
            'key': 'SponsorBlock',
            'categories': [sponsor_categories]
        }
    ffmdopt = {
        'key': 'FFmpegMetadata',
            'add_chapters': True,
            'add_metadata': True
    }

    opts = get_yt_opts()
    if embed_thumbnail:
        ytopts['postprocessors'].push({'key': 'EmbedThumbnail'})
    if embed_metadata:
        ffmdopt["embed-metadata"] = True
    if skip_sponsors:
        ytopts['postprocessors'].push(sbopt)
    
    ytopts['postprocessors'].push(ffmdopt)
        
    opts.update(ytopts)
        
    with yt_dlp.YoutubeDL(opts) as y:
        try:
            return y.download([url])
        except yt_dlp.utils.DownloadError as e:
            raise YouTubeError(f'Failed to download for "{url}": {e}') from e
    return False
