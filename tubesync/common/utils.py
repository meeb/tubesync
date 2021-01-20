from urllib.parse import urlunsplit, urlencode


def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def append_uri_params(uri, params):
    uri = str(uri)
    qs = urlencode(params)
    return urlunsplit(('', '', uri, qs, ''))


def clean_filename(filename):
    if not isinstance(filename, str):
        raise ValueError(f'filename must be a str, got {type(filename)}')
    to_scrub = '<>\/:*?"|'
    for char in to_scrub:
        filename = filename.replace(char, '')
    filename = ''.join([c for c in filename if ord(c) > 30])
    return ' '.join(filename.split())
