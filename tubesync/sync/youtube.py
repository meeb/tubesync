'''
    Wrapper for the yt-dlp library. Used so if there are any library interface
    updates we only need to udpate them in one place.
'''


import os

from common.logger import log
from common.utils import mkdir_p
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit, parse_qs

from django.conf import settings
from .choices import Val, FileExtension
from .hooks import postprocessor_hook, progress_hook
import yt_dlp
import yt_dlp.patch.check_thumbnails
import yt_dlp.patch.fatal_http_errors
from yt_dlp.utils import remove_end, shell_quote, OUTTMPL_TYPES


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
    opts = deepcopy(_defaults)
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
        'check_formats': False,
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
                if banner_url is not None and avatar_url is not None:
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


def get_media_info(url, /, *, days=None, info_json=None):
    '''
        Extracts information from a YouTube URL and returns it as a dict. For a channel
        or playlist this returns a dict of all the videos on the channel or playlist
        as well as associated metadata.
    '''
    start = None
    if days is not None:
        try:
            days = int(str(days), 10)
        except (TypeError, ValueError):
            days = None
        start = (
            f'yesterday-{days!s}days' if days else None
        )
    opts = get_yt_opts()
    default_opts = yt_dlp.parse_options([]).options
    class NoDefaultValue: pass # a unique Singleton, that may be checked for later
    user_set = lambda k, d, default=NoDefaultValue: d[k] if k in d.keys() else default
    default_paths = user_set('paths', default_opts.__dict__, dict())
    paths = user_set('paths', opts, default_paths)
    if 'temp' in paths:
        temp_dir_obj = TemporaryDirectory(prefix='.yt_dlp-', dir=paths['temp'])
        temp_dir_path = Path(temp_dir_obj.name)
        (temp_dir_path / '.ignore').touch(exist_ok=True)
        paths.update({
            'temp': str(temp_dir_path),
        })
    try:
        info_json_path = Path(info_json).resolve(strict=False)
    except (RuntimeError, TypeError):
        pass
    else:
        paths.update({
            'infojson': user_set('infojson', paths, str(info_json_path))
        })
    default_postprocessors = user_set('postprocessors', default_opts.__dict__, list())
    postprocessors = user_set('postprocessors', opts, default_postprocessors)
    postprocessors.append(dict(
        key='Exec',
        when='playlist',
        exec_cmd="/usr/bin/env bash /app/full_playlist.sh '%(id)s' '%(playlist_count)d'",
    ))
    cache_directory_path = Path(user_set('cachedir', opts, '/dev/shm'))
    playlist_infojson = 'postprocessor_[%(id)s]_%(n_entries)d_%(playlist_count)d_temp'
    outtmpl = dict(
        default='',
        infojson='%(extractor_key)s/%(id)s.%(ext)s' if paths.get('infojson') else '',
        pl_infojson=f'{cache_directory_path}/infojson/playlist/{playlist_infojson}.%(ext)s',
    )
    for k in OUTTMPL_TYPES.keys():
        outtmpl.setdefault(k, '')
    opts.update({
        'ignoreerrors': False, # explicitly set this to catch exceptions
        'ignore_no_formats_error': False, # we must fail first to try again with this enabled
        'skip_download': True,
        'simulate': False,
        'logger': log,
        'extract_flat': True,
        'allow_playlist_files': True,
        'check_formats': True,
        'check_thumbnails': False,
        'clean_infojson': False,
        'daterange': yt_dlp.utils.DateRange(start=start),
        'extractor_args': {
            'youtube': {'formats': ['missing_pot']},
            'youtubetab': {'approximate_date': ['true']},
        },
        'outtmpl': outtmpl,
        'overwrites': True,
        'paths': paths,
        'postprocessors': postprocessors,
        'skip_unavailable_fragments': False,
        'sleep_interval_requests': 1,
        'verbose': True if settings.DEBUG else False,
        'writeinfojson': True,
    })
    if start:
        log.debug(f'get_media_info: used date range: {opts["daterange"]} for URL: {url}')
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


# Yes, this looks odd. But, it works.
# It works without also causing indentation problems.
# I'll take ease of editing, thanks.
def download_media(
    url, media_format, extension, output_file,
    info_json, sponsor_categories=None,
    embed_thumbnail=False, embed_metadata=False,
    skip_sponsors=True, write_subtitles=False,
    auto_subtitles=False, sub_langs='en'
):
    '''
        Downloads a YouTube URL to a file on disk.
    '''

    opts = get_yt_opts()
    default_opts = yt_dlp.parse_options([]).options
    pp_opts = deepcopy(default_opts)

    # We fake up this option to make it easier for the user to add post processors.
    postprocessors = opts.get('add_postprocessors', pp_opts.add_postprocessors)
    if isinstance(postprocessors, str):
        # NAME1[:ARGS], NAME2[:ARGS]
        # ARGS are a semicolon ";" delimited list of NAME=VALUE
        #
        # This means that "," cannot be present in NAME or VALUE.
        # If you need to support that, then use the 'postprocessors' key,
        # in your settings dictionary instead.
        _postprocessor_opts_parser = lambda key, val='': (
            *(
                item.split('=', 1) for item in (val.split(';') if val else [])
            ),
            ( 'key', remove_end(key, 'PP'), )
        )
        postprocessors = list(
            dict(
                _postprocessor_opts_parser( *val.split(':', 1) )
            ) for val in map(str.strip, postprocessors.split(','))
        )
    if not isinstance(postprocessors, list):
        postprocessors = list()
    # Add any post processors configured the 'hard' way also.
    postprocessors.extend( opts.get('postprocessors', list()) )

    pp_opts.__dict__.update({
        'add_postprocessors': postprocessors,
        'embedthumbnail': embed_thumbnail,
        'addmetadata': embed_metadata,
        'addchapters': True,
        'embed_infojson': False,
        'writethumbnail': False,
        'force_keyframes_at_cuts': True,
        'sponskrub': False,
    })

    pp_opts.exec_cmd.update(
        opts.get('exec_cmd', default_opts.exec_cmd)
    )

    if skip_sponsors:
        # Let yt_dlp convert from human for us.
        pp_opts.sponsorblock_mark = yt_dlp.parse_options(
            ['--sponsorblock-mark=all,-chapter']
        ).options.sponsorblock_mark
        pp_opts.sponsorblock_remove.update(sponsor_categories or {})

    # Enable audio extraction for audio-only extensions
    audio_exts = set(Val(
        FileExtension.M4A,
        FileExtension.OGG,
    ))
    if extension in audio_exts:
        pp_opts.extractaudio = True
        pp_opts.nopostoverwrites = False
        # The ExtractAudio post processor can change the extension.
        # This post processor is to change the final filename back
        # to what we are expecting it to be.
        final_path = Path(output_file)
        try:
            final_path = final_path.resolve(strict=True)
        except FileNotFoundError:
            # This is very likely the common case
            final_path = Path(output_file).resolve(strict=False)
        expected_file = shell_quote(str(final_path))
        cmds = pp_opts.exec_cmd.get('after_move', list())
        cmds.append(
            f'test -f {expected_file} || '
            'mv -T -u -- %(filepath,_filename|)q '
            f'{expected_file}'
        )
        # assignment is the quickest way to cover both 'get' cases
        pp_opts.exec_cmd['after_move'] = cmds
    elif '+' not in media_format:
        pp_opts.remuxvideo = extension

    ytopts = {
        'format': media_format,
        'final_ext': extension,
        'merge_output_format': extension,
        'outtmpl': os.path.basename(output_file),
        'remuxvideo': pp_opts.remuxvideo,
        'quiet': False if settings.DEBUG else True,
        'verbose': True if settings.DEBUG else False,
        'noprogress': None if settings.DEBUG else True,
        'writeinfojson': info_json,
        'writesubtitles': write_subtitles,
        'writeautomaticsub': auto_subtitles,
        'subtitleslangs': sub_langs.split(','),
        'writethumbnail': embed_thumbnail,
        'check_formats': None,
        'overwrites': None,
        'skip_unavailable_fragments': False,
        'sleep_interval': 10,
        'max_sleep_interval': min(15*60, max(60, settings.DOWNLOAD_MEDIA_DELAY)),
        'sleep_interval_requests': 3,
        'extractor_args': opts.get('extractor_args', dict()),
        'paths': opts.get('paths', dict()),
        'postprocessor_args': opts.get('postprocessor_args', dict()),
        'postprocessor_hooks': opts.get('postprocessor_hooks', list()),
        'progress_hooks': opts.get('progress_hooks', list()),
    }
    output_dir = os.path.dirname(output_file)
    temp_dir_parent = output_dir
    temp_dir_prefix = '.yt_dlp-'
    if 'temp' in ytopts['paths']:
        v_key = parse_qs(urlsplit(url).query).get('v').pop()
        temp_dir_parent = ytopts['paths']['temp']
        temp_dir_prefix = f'{temp_dir_prefix}{v_key}-'
    temp_dir_obj = TemporaryDirectory(prefix=temp_dir_prefix,dir=temp_dir_parent)
    if temp_dir_obj and (Path(temp_dir_parent) / '.clean').exists():
        temp_dir_path = Path(temp_dir_obj.name)
    else:
        temp_dir_path = Path(temp_dir_parent)
    (temp_dir_path / '.ignore').touch(exist_ok=True)
    ytopts['paths'].update({
        'home': str(output_dir),
        'temp': str(temp_dir_path),
    })

    # Allow download of formats that tested good with 'missing_pot'
    youtube_ea_dict = ytopts['extractor_args'].get('youtube', dict())
    formats_list = youtube_ea_dict.get('formats', list())
    if 'missing_pot' not in formats_list:
        formats_list.append('missing_pot')
        youtube_ea_dict.update({
            'formats': formats_list,
        })
    ytopts['extractor_args'].update({
        'youtube': youtube_ea_dict,
    })

    postprocessor_hook_func = postprocessor_hook.get('function', None)
    if postprocessor_hook_func:
        ytopts['postprocessor_hooks'].append(postprocessor_hook_func)

    progress_hook_func = progress_hook.get('function', None)
    if progress_hook_func:
        ytopts['progress_hooks'].append(progress_hook_func)

    codec_options = list()
    ofn = ytopts['outtmpl']
    if 'av1-' in ofn:
        codec_options.extend(['-c:v', 'libsvtav1', '-preset', '8', '-crf', '35'])
    elif 'vp9-' in ofn:
        codec_options.extend(['-c:v', 'libvpx-vp9', '-b:v', '0', '-crf', '31', '-row-mt', '1', '-tile-columns', '2'])
    if '-opus' in ofn:
        codec_options.extend(['-c:a', 'libopus'])
    set_ffmpeg_codec = not (
        ytopts['postprocessor_args'] and
        ytopts['postprocessor_args']['modifychapters+ffmpeg']
    )
    if set_ffmpeg_codec and codec_options:
        ytopts['postprocessor_args'].update({
            'modifychapters+ffmpeg': codec_options,
        })

    # Provide the user control of 'overwrites' in the post processors.
    pp_opts.overwrites = opts.get(
        'overwrites',
        ytopts.get(
            'overwrites',
            default_opts.overwrites,
        ),
    )

    # Create the post processors list.
    # It already included user configured post processors as well.
    ytopts['postprocessors'] = list(yt_dlp.get_postprocessors(pp_opts))

    opts.update(ytopts)

    with yt_dlp.YoutubeDL(opts) as y:
        try:
            return y.download([url])
        except yt_dlp.utils.DownloadError as e:
            raise YouTubeError(f'Failed to download for "{url}": {e}') from e
    return False
