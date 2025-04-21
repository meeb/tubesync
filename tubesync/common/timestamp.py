import datetime
from django.utils import timezone


posix_epoch = datetime.datetime.utcfromtimestamp(0)
utc_tz = datetime.timezone.utc


def add_epoch(seconds):
    assert seconds is not None
    assert seconds >= 0, 'seconds must be a positive number'

    return timedelta(seconds=seconds) + posix_epoch

def subtract_epoch(arg_dt, /):
    epoch = posix_epoch.astimezone(utc_tz)
    utc_dt = arg_dt.astimezone(utc_tz)

    return utc_dt - epoch

def datetime_to_timestamp(arg_dt, /):
    timestamp = subtract_epoch(arg_dt).total_seconds()

    try:
        timestamp_int = int(timestamp)
    except (TypeError, ValueError,):
        pass
    else:
        return timestamp_int

    return timestamp

def timestamp_to_datetime(seconds, /):
    return add_epoch(seconds=seconds).astimezone(utc_tz)

