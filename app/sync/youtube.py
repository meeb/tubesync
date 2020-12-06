'''
    Wrapper for the youtube-dl library. Used so if there are any library interface
    updates we only need to udpate them in one place.
'''


from django.conf import settings
from copy import copy
from common.logger import log
import youtube_dl


_defaults = getattr(settings, 'YOUTUBE_DEFAULTS', {})
_defaults.update({'logger': log})


class YouTubeError(youtube_dl.utils.DownloadError):
    '''
        Generic wrapped error for all errors that could be raised by youtube-dl.
    '''
    pass


def get_media_info(url):
    '''
        Extracts information from a YouTube URL and returns it as a dict. For a channel
        or playlist this returns a dict of all the videos on the channel or playlist
        as well as associated metadata.
    '''
    opts = copy(_defaults)
    opts.update({
        'skip_download': True,
        'forcejson': True,
        'simulate': True,
    })
    response = {}
    with youtube_dl.YoutubeDL(opts) as y:
        try:
            response = y.extract_info(url, download=False)
        except youtube_dl.utils.DownloadError as e:
            raise YouTubeError(f'Failed to extract_info for "{url}": {e}') from e
    return response
