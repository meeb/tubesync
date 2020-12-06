import os
import re
import math
from pathlib import Path
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
    valid_scheme, valid_netloc, valid_path, valid_query, extract_parts = (
        validator['scheme'], validator['domain'], validator['path_regex'],
        validator['qs_args'], validator['extract_key'])
    url_parts = urlsplit(str(url).strip())
    url_scheme = str(url_parts.scheme).strip().lower()
    if url_scheme != valid_scheme:
        raise ValidationError(f'scheme "{url_scheme}" must be "{valid_scheme}"')
    url_netloc = str(url_parts.netloc).strip().lower()
    if url_netloc != valid_netloc:
        raise ValidationError(f'domain "{url_netloc}" must be "{valid_netloc}"')
    url_path = str(url_parts.path).strip()
    matches = re.findall(valid_path, url_path)
    if not matches:
        raise ValidationError(f'path "{url_path}" must match "{valid_path}"')
    url_query = str(url_parts.query).strip()
    url_query_parts = parse_qs(url_query)
    for required_query in valid_query:
        if required_query not in url_query_parts:
            raise ValidationError(f'query string "{url_query}" must '
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


def get_remote_image(url):
    headers = {
        'user-agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                       '(KHTML, like Gecko) Chrome/69.0.3497.64 Safari/537.36')
    }
    r = requests.get(url, headers=headers, stream=True, timeout=60)
    r.raw.decode_content = True
    return Image.open(r.raw)


def resize_image_to_height(image, width, height):
    '''
        Resizes an image to 'height' pixels keeping the ratio. If the resulting width
        is larger than 'width' then crop it. If the resulting width is smaller than
        'width' then stretch it.
    '''
    ratio = image.width / image.height
    scaled_width = math.ceil(height * ratio)
    if scaled_width < width:
        # Width too small, stretch it
        scaled_width = width
    image = image.resize((scaled_width, height), Image.ANTIALIAS)
    if scaled_width > width:
        # Width too large, crop it
        delta = scaled_width - width
        left, upper = (delta / 2), 0
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
        os.path.commonpath([os.path.abspath(str(settings.MEDIA_ROOT))]),
        # Downloaded video files
        os.path.commonpath([os.path.abspath(str(settings.SYNC_VIDEO_ROOT))]),
        # Downloaded audio files
        os.path.commonpath([os.path.abspath(str(settings.SYNC_AUDIO_ROOT))]),
    )
    filepath = os.path.abspath(str(filepath))
    if not os.path.isfile(filepath):
        return False
    for allowed_path in allowed_paths:
        if allowed_path == os.path.commonpath([allowed_path, filepath]):
            return True
    return False


def delete_file(filepath):
    if file_is_editable(filepath):
        return os.remove(filepath)
    return False
