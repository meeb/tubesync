from functools import wraps

from django import db

from yt_dlp.utils import LazyList, RetryManager


def eager_list(list_like, /) -> list:
    from .logger import log

    arg_type = type(list_like)
    result_list = None

    if isinstance(list_like, list):
        result_list = list_like
    elif callable(exhaust := getattr(list_like, 'exhaust', None)):
        # convert LazyList to a list using its own exhaust method
        result_list = exhaust()
        log.debug(f'called exhaust(): {len(result_list)=} {arg_type=}')
    elif isinstance(list_like, LazyList):
        log.warning('a yt_dlp.utils.LazyList did not have exhaust()')
    else:
        log.warning(f'an unexpected type was passed: {arg_type=}')

    return list(list_like) if result_list is None else result_list

def retry_django_db(max_retries=15, *, callback_func=None, **settings):
    if callback_func is None:
        callback_func = RetryManager.report_retry
        settings.setdefault('info', lambda m: None)
        settings.setdefault('warn', lambda m: None)
        settings.setdefault('sleep_func', 0.05)

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for retry in RetryManager(max_retries, callback_func, **settings):
                try:
                    return func(*args, **kwargs)
                # django.db.utils.OperationalError: database is locked
                except db.utils.OperationalError as e:
                    if str(e).endswith('database is locked'):
                        retry.error = e
                        continue
                    raise

        return wrapper

    return decorator
