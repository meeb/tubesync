import os
import re
import math
from operator import itemgetter
from pathlib import Path
from tempfile import NamedTemporaryFile
import requests
from PIL import Image
from django.conf import settings
from urllib.parse import urlsplit, parse_qs
from django.forms import ValidationError


def validate_url(url, validator):
    '''
        Validate a URL against a dict of validation requirements. Returns an extracted
        part of the URL if the URL is valid, if invalid raises a ValidationError.
    '''
    valid_scheme, valid_netlocs, valid_path, invalid_paths, valid_query, \
        extract_parts = (
            validator['scheme'], validator['domains'], validator['path_regex'],
            validator['path_must_not_match'], validator['qs_args'],
            validator['extract_key']
    )
    url_parts = urlsplit(str(url).strip())
    url_scheme = str(url_parts.scheme).strip().lower()
    if url_scheme != valid_scheme:
        raise ValidationError(f'invalid scheme "{url_scheme}" must be "{valid_scheme}"')
    url_netloc = str(url_parts.netloc).strip().lower()
    if url_netloc not in valid_netlocs:
        raise ValidationError(f'invalid domain "{url_netloc}" must be one of "{valid_netlocs}"')
    url_path = str(url_parts.path).strip()
    matches = re.findall(valid_path, url_path)
    if not matches:
        raise ValidationError(f'invalid path "{url_path}" must match "{valid_path}"')
    for invalid_path in invalid_paths:
        if url_path.lower() == invalid_path.lower():
            raise ValidationError(f'path "{url_path}" is not valid')
    url_query = str(url_parts.query).strip()
    url_query_parts = parse_qs(url_query)
    for required_query in valid_query:
        if required_query not in url_query_parts:
            raise ValidationError(f'invalid query string "{url_query}" must '
                                  f'contain the parameter "{required_query}"')
    extract_from, extract_param = extract_parts
    extract_value = ''
    if extract_from == 'path_regex':
        try:
            submatches = matches[0]
            try:
                extract_value = submatches[extract_param]
            except IndexError:
                pass
        except IndexError:
            pass
    elif extract_from == 'qs_args':
        extract_value = url_query_parts[extract_param][0]
    return extract_value


def get_remote_image(url, force_rgb=True):
    headers = {
        'user-agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                       '(KHTML, like Gecko) Chrome/69.0.3497.64 Safari/537.36')
    }
    r = requests.get(url, headers=headers, stream=True, timeout=60)
    r.raw.decode_content = True
    i = Image.open(r.raw)
    if force_rgb:
        i = i.convert('RGB')
    return i


def resize_image_to_height(image, width, height):
    '''
        Resizes an image to 'height' pixels keeping the ratio. If the resulting width
        is larger than 'width' then crop it. If the resulting width is smaller than
        'width' then stretch it.
    '''
    image = image.convert('RGB')
    ratio = image.width / image.height
    scaled_width = math.ceil(height * ratio)
    if scaled_width < width:
        # Width too small, stretch it
        scaled_width = width
    image = image.resize((scaled_width, height), Image.LANCZOS)
    if scaled_width > width:
        # Width too large, crop it
        delta = scaled_width - width
        left, upper = round(delta / 2), 0
        right, lower = (left + width), height
        image = image.crop((left, upper, right, lower))
    return image


def file_is_editable(filepath):
    '''
        Checks that a file exists and the file is in an allowed predefined tuple of
        directories we want to allow writing or deleting in.
    '''
    allowed_paths = (
        # Media item thumbnails
        Path(str(settings.MEDIA_ROOT)).resolve(),

        # Downloaded media files
        Path(str(settings.DOWNLOAD_ROOT)).resolve(),
    )
    filepath = Path(str(filepath)).resolve()
    if not filepath.is_file():
        return False
    for allowed_path in allowed_paths:
        if str(allowed_path) == os.path.commonpath([allowed_path, filepath]):
            return True
    return False


def write_text_file(filepath, filedata):
    if not isinstance(filedata, str):
        raise TypeError(f'filedata must be a str, got "{type(filedata)}"')
    filepath_dir = str(Path(filepath).parent)
    with NamedTemporaryFile(mode='wt', suffix='.tmp', prefix='', dir=filepath_dir, delete=False) as f:
        new_filepath = Path(f.name)
        bytes_written = f.write(filedata)
    # chmod a+r temp_file
    old_mode = new_filepath.stat().st_mode
    if 0o444 != (0o444 & old_mode):
        new_filepath.chmod(0o444 | old_mode)
    if not file_is_editable(new_filepath):
        new_filepath.unlink()
        raise ValueError(f'File cannot be edited or removed: {filepath}')
    new_filepath.replace(filepath)
    return bytes_written


def delete_file(filepath):
    if file_is_editable(filepath):
        return os.remove(filepath)
    return False


def seconds_to_timestr(seconds):
   seconds = seconds % (24 * 3600)
   hour = seconds // 3600
   seconds %= 3600
   minutes = seconds // 60
   seconds %= 60
   return '{:02d}:{:02d}:{:02d}'.format(hour, minutes, seconds)


def multi_key_sort(sort_dict, specs, use_reversed=False):
    result = list(sort_dict)
    for key, reverse in reversed(specs):
        result = sorted(result, key=itemgetter(key), reverse=reverse)
    if use_reversed:
        return list(reversed(result))
    return result


def normalize_codec(codec_str):
    result = str(codec_str).upper()
    parts = result.split('.')
    if len(parts) > 0:
        result = parts[0].strip()
    else:
        return None
    if 'NONE' == result:
        return None
    if str(0) in result:
        prefix = result.rstrip('0123456789')
        result = prefix + str(int(result[len(prefix):]))
    return result


def _url_keys(arg_dict, filter_func):
    result = {}
    for key in arg_dict.keys():
        if 'url' in key:
            result.update(
                {key: filter_func(key=key, url=arg_dict[key])}
            )
    return result


def _drop_url_keys(arg_dict, key, filter_func):
    if key in arg_dict.keys():
        for val_dict in arg_dict[key]:
            for url_key, remove in _url_keys(val_dict, filter_func).items():
                if remove is True:
                    del val_dict[url_key]


def filter_response(response_dict):
    '''
        Clean up the response so as to not store useless metadata in the database.
    '''
    # raise an exception for an unexpected argument type
    if not isinstance(response_dict, dict):
        raise TypeError(f'response_dict must be a dict, got "{type(response_dict)}"')
    # optimize the empty case
    if not response_dict:
        return response_dict

    # beginning of formats cleanup {{{
    # drop urls that expire, or restrict IPs
    def drop_format_url(**kwargs):
        url = kwargs['url']
        return (
            url
            and '://' in url
            and (
                '/ip/' in url
                or 'ip=' in url
                or '/expire/' in url
                or 'expire=' in url
            )
        )

    # these format keys are not useful to us
    drop_keys = frozenset((
        'downloader_options',
        'fragments',
        'http_headers',
        '__needs_testing',
        '__working',
    ))
    for key in frozenset(('formats', 'requested_formats',)):
        _drop_url_keys(response_dict, key, drop_format_url)
        if key in response_dict.keys():
            for format in response_dict[key]:
                for drop_key in drop_keys:
                    if drop_key in format.keys():
                        del format[drop_key]
    # end of formats cleanup }}}

    # beginning of subtitles cleanup {{{
    # drop urls that expire
    def drop_subtitles_url(**kwargs):
        url = kwargs['url']
        return (
            url
            and '://' in url
            and '&expire=' in url
        )

    for key in frozenset(('subtitles', 'automatic_captions',)):
        if key in response_dict.keys():
            key_dict = response_dict[key]
            for lang_code in key_dict:
                _drop_url_keys(key_dict, lang_code, drop_subtitles_url)
    # end of subtitles cleanup }}}

    return response_dict


def parse_media_format(format_dict):
    '''
        This parser primarily adapts the format dict returned by youtube-dl into a
        standard form used by the matchers in matching.py. If youtube-dl changes
        any internals, update it here.
    '''
    vcodec_full = format_dict.get('vcodec', '')
    vcodec = normalize_codec(vcodec_full)
    acodec_full = format_dict.get('acodec', '')
    acodec = normalize_codec(acodec_full) 
    try:
        fps = int(format_dict.get('fps', 0))
    except (ValueError, TypeError):
        fps = 0
    height = format_dict.get('height', 0)
    try:
        height = int(height)
    except (ValueError, TypeError):
        height = 0
    width = format_dict.get('width', 0)
    try:
        width = int(width)
    except (ValueError, TypeError):
        width = 0
    format_full = format_dict.get('format_note', '').strip().upper()
    format_str = format_full[:-2] if format_full.endswith('60') else format_full
    format_str = format_str.strip()
    format_str = format_str[:-3] if format_str.endswith('HDR') else format_str
    format_str = format_str.strip()
    format_str = format_str[:-2] if format_str.endswith('60') else format_str
    format_str = format_str.strip()
    is_hls = True
    is_dash = False
    if 'DASH' in format_str:
        is_hls = False
        is_dash = True
        if height > 0:
            format_str = f'{height}P'
        else:
            format_str = None
    return {
        'id': format_dict.get('format_id', ''),
        'format': format_str,
        'format_verbose': format_dict.get('format', ''),
        'height': height,
        'width': width,
        'vcodec': vcodec,
        'fps': format_dict.get('fps', 0),
        'vbr': format_dict.get('tbr', 0),
        'acodec': acodec,
        'abr': format_dict.get('abr', 0),
        'is_60fps': fps > 50,
        'is_hdr': 'HDR' in format_dict.get('format', '').upper(),
        'is_hls': is_hls,
        'is_dash': is_dash,
    }
