import cProfile
import emoji
import io
import os
import pstats
import string
import time
from datetime import datetime
from urllib.parse import urlunsplit, urlencode, urlparse
from yt_dlp.utils import LazyList
from .errors import DatabaseConnectionError


def getenv(key, default=None, /, *, integer=False, string=True):
    '''
        Guarantees a returned type from calling `os.getenv`
        The caller can request the integer type,
          or use the default string type.
    '''

    args = dict(key=key, default=default, integer=integer, string=string)
    supported_types = dict(zip(args.keys(), (
        (str,), # key
        (
            bool,
            float,
            int,
            str,
            None.__class__,
        ), # default
        (bool,) * (len(args.keys()) - 2),
    )))
    unsupported_type_msg = 'Unsupported type for positional argument, "{}": {}'
    for k, t in supported_types.items():
        v = args[k]
        assert isinstance(v, t), unsupported_type_msg.format(k, type(v))

    d = str(default) if default is not None else None

    r = os.getenv(key, d)
    if r is None:
        if string: r = str()
        if integer: r = int()
    elif integer:
        r = int(float(r))
    return r


def parse_database_connection_string(database_connection_string):
    '''
        Parses a connection string in a URL style format, such as:
            postgresql://tubesync:password@localhost:5432/tubesync
            mysql://someuser:somepassword@localhost:3306/tubesync
        into a Django-compatible settings.DATABASES dict format. 
    '''
    valid_drivers = ('postgresql', 'mysql')
    default_ports = {
        'postgresql': 5432,
        'mysql': 3306,
    }
    django_backends = {
        'postgresql': 'django.db.backends.postgresql',
        'mysql': 'django.db.backends.mysql',
    }
    backend_options = {
        'postgresql': {},
        'mysql': {
            'charset': 'utf8mb4',
        }
    }
    try:
        parts = urlparse(str(database_connection_string))
    except Exception as e:
        raise DatabaseConnectionError(f'Failed to parse "{database_connection_string}" '
                                      f'as a database connection string: {e}') from e
    driver = parts.scheme
    user_pass_host_port = parts.netloc
    database = parts.path
    if driver not in valid_drivers:
        raise DatabaseConnectionError(f'Database connection string '
                                      f'"{database_connection_string}" specified an '
                                      f'invalid driver, must be one of {valid_drivers}')
    django_driver = django_backends.get(driver)
    host_parts = user_pass_host_port.split('@')
    if len(host_parts) != 2:
        raise DatabaseConnectionError(f'Database connection string netloc must be in '
                                      f'the format of user:pass@host')
    user_pass, host_port = host_parts
    user_pass_parts = user_pass.split(':')
    if len(user_pass_parts) != 2:
        raise DatabaseConnectionError(f'Database connection string netloc must be in '
                                      f'the format of user:pass@host')
    username, password = user_pass_parts
    host_port_parts = host_port.split(':')
    if len(host_port_parts) == 1:
        # No port number, assign a default port
        hostname = host_port_parts[0]
        port = default_ports.get(driver)
    elif len(host_port_parts) == 2:
        # Host name and port number
        hostname, port = host_port_parts
        try:
            port = int(port)
        except (ValueError, TypeError) as e:
            raise DatabaseConnectionError(f'Database connection string contained an '
                                          f'invalid port, ports must be integers: '
                                          f'{e}') from e
        if not 0 < port < 63336:
            raise DatabaseConnectionError(f'Database connection string contained an '
                                          f'invalid port, ports must be between 1 and '
                                          f'65535, got {port}')
    else:
        # Malformed
        raise DatabaseConnectionError(f'Database connection host must be a hostname or '
                                      f'a hostname:port combination')
    if database.startswith('/'):
        database = database[1:]
    if not database:
        raise DatabaseConnectionError(f'Database connection string path must be a '
                                      f'string in the format of /databasename')    
    if '/' in database:
        raise DatabaseConnectionError(f'Database connection string path can only '
                                      f'contain a single string name, got: {database}')
    return {
        'DRIVER': driver,
        'ENGINE': django_driver,
        'NAME': database,
        'USER': username,
        'PASSWORD': password,
        'HOST': hostname,
        'PORT': port,
        'CONN_MAX_AGE': 300,
        'OPTIONS': backend_options.get(driver),
    }


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
    to_scrub = r'<>\/:*?"|%'
    for char in list(to_scrub):
        filename = filename.replace(char, '')
    clean_filename = ''
    for c in filename:
        if c in string.whitespace:
            c = ' '
        if ord(c) > 30:
            clean_filename += c
    return clean_filename.strip()


def clean_emoji(s):
    if not isinstance(s, str):
        raise ValueError(f'parameter must be a str, got {type(s)}')
    return emoji.replace_emoji(s)


def json_serial(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, LazyList):
        return list(obj)
    raise TypeError(f'Type {type(obj)} is not json_serial()-able')


def time_func(func):
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        end = time.perf_counter()
        return (result, (end - start, start, end,),)
    return wrapper


def profile_func(func):
    def wrapper(*args, **kwargs):
        s = io.StringIO()
        with cProfile.Profile() as pr:
            pr.enable()
            result = func(*args, **kwargs)
            pr.disable()
            ps = pstats.Stats(pr, stream=s)
            ps.sort_stats(
                pstats.SortKey.CUMULATIVE
            ).print_stats()
        return (result, (s.getvalue(), ps, s,),)
    return wrapper


def remove_enclosed(haystack, /, open='[', close=']', sep=' ', *, valid=None, start=None, end=None):
    if not haystack:
        return haystack
    assert open and close, 'open and close are required to be non-empty strings'
    o = haystack.find(open, start, end)
    sep = sep or ''
    n = close + sep
    c = haystack.find(n, len(open)+o, end)
    if -1 in {o, c}:
        return haystack
    if valid is not None:
        content = haystack[len(open)+o:c]
        found = set(content)
        valid = set(valid)
        invalid = found - valid
        # assert not invalid, f'Invalid characters {invalid} found in: {content}'
        if invalid:
            return haystack
    return haystack[:o] + haystack[len(n)+c:]

