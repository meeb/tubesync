import cProfile
import emoji
import gc
import io
import os
import pstats
import string
import time
from django.core.paginator import Paginator
from functools import partial
from operator import attrgetter, itemgetter
from pathlib import Path
from urllib.parse import urlunsplit, urlencode, urlparse
from .errors import DatabaseConnectionError

def directory_and_stem(arg_path, /, all_suffixes=False):
    filepath = Path(arg_path)
    stem = Path(filepath.stem)
    while all_suffixes and stem.suffixes and '' != stem.suffix:
        stem = Path(stem.stem)
    return (filepath.parent, str(stem),)


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


def glob_quote(filestr, /):
    _glob_specials = {
        '?': '[?]',
        '*': '[*]',
        '[': '[[]',
        ']': '[]]', # probably not needed, but it won't hurt
    }

    if not isinstance(filestr, str):
        raise TypeError(f'expected a str, got "{type(filestr)}"')

    return filestr.translate(str.maketrans(_glob_specials))


def list_of_dictionaries(arg_list, /, arg_function=lambda x: x):
    assert callable(arg_function)
    if isinstance(arg_list, list):
        _map_func = partial(lambda f, d: f(d) if isinstance(d, dict) else d, arg_function)
        return (True, list(map(_map_func, arg_list)),)
    return (False, arg_list,)


def mkdir_p(arg_path, /, *, mode=0o777):
    '''
        Reminder: mode only affects the last directory
    '''
    dirpath = Path(arg_path)
    return dirpath.mkdir(mode=mode, parents=True, exist_ok=True)


def multi_key_sort(iterable, specs, /, use_reversed=False, *, item=False, attr=False, key_func=None):
    result = list(iterable)
    if key_func is None:
        # itemgetter is the default
        if item or not (item or attr):
            key_func = itemgetter
        elif attr:
            key_func = attrgetter
    for key, reverse in reversed(specs):
        result.sort(key=key_func(key), reverse=reverse)
    if use_reversed:
        return list(reversed(result))
    return result


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
        'postgresql': dict(pool={
            'max_size': 80, # default: None (static min_size pool)
            'min_size': 8, # default: 4
            'num_workers': 6, # default: 3
            'timeout': 180, # default: 30
        }),
        'mysql': {
            'charset': 'utf8mb4',
        }
    }
    db_overrides = {
        'mysql': {
            'CONN_MAX_AGE': 300,
        },
        'postgresql': dict(),
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
    user_pass_parts = host_parts[0].split(':')
    if len(host_parts) != 2 or len(user_pass_parts) != 2:
        raise DatabaseConnectionError('Database connection string netloc must be in '
                                      'the format of user:pass@host')
    user_pass, host_port = host_parts
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
        raise DatabaseConnectionError('Database connection host must be a hostname or '
                                      'a hostname:port combination')
    if database.startswith('/'):
        database = database[1:]
    if not database:
        raise DatabaseConnectionError('Database connection string path must be a '
                                      'string in the format of /databasename')    
    if '/' in database:
        raise DatabaseConnectionError(f'Database connection string path can only '
                                      f'contain a single string name, got: {database}')
    db_dict = {
        'DRIVER': driver,
        'ENGINE': django_driver,
        'NAME': database,
        'USER': username,
        'PASSWORD': password,
        'HOST': hostname,
        'PORT': port,
        'CONN_HEALTH_CHECKS': True,
        'CONN_MAX_AGE': 0,
        'OPTIONS': backend_options.get(driver),
    }
    db_dict.update(db_overrides.get(driver))
    
    return db_dict


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


def seconds_to_timestr(seconds):
    seconds = seconds % (24 * 3600)
    hour = seconds // 3600
    seconds %= 3600
    minutes = seconds // 60
    seconds %= 60
    return '{:02d}:{:02d}:{:02d}'.format(hour, minutes, seconds)


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


def django_queryset_generator(query_set, /, *,
    page_size=100,
    chunk_size=None,
    use_chunked_fetch=False,
):
    qs = query_set.values_list('pk', flat=True)
    # Avoid the `UnorderedObjectListWarning`
    if not query_set.ordered:
        qs = qs.order_by('pk')
    collecting = gc.isenabled()
    gc.disable()
    if use_chunked_fetch:
        for key in qs._iterator(use_chunked_fetch, chunk_size):
            yield query_set.filter(pk=key)[0]
            key = None
            gc.collect(generation=1)
        key = None
    else:
        for page in iter(Paginator(qs, page_size)):
            for key in page.object_list:
                yield query_set.filter(pk=key)[0]
                key = None
                gc.collect(generation=1)
            key = None
            page = None
            gc.collect()
        page = None
    qs = None
    gc.collect()
    if collecting:
        gc.enable()

