from functools import wraps

from django import db

from yt_dlp.utils import RetryManager


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
