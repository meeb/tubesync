import datetime
import math


utc_tz = datetime.timezone.utc
posix_epoch = datetime.datetime.fromtimestamp(0, tz=utc_tz)


def add_epoch(seconds):
    assert seconds is not None
    assert seconds >= 0, 'seconds must be a positive number'

    return datetime.timedelta(seconds=seconds) + posix_epoch

def subtract_epoch(arg_dt, /):
    assert isinstance(arg_dt, datetime.datetime)
    if arg_dt.utcoffset() is None: # naive
        return arg_dt - datetime.datetime.fromtimestamp(0, tz=None)

    utc_dt = arg_dt.astimezone(utc_tz)

    return utc_dt - posix_epoch

def datetime_to_timestamp(arg_dt, /, *, integer=True):
    timestamp = subtract_epoch(arg_dt).total_seconds()

    if not integer:
        return timestamp
    return math.ceil(timestamp)

def timestamp_to_datetime(seconds, /):
    return add_epoch(seconds=seconds).astimezone(utc_tz)

