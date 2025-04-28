import datetime


posix_epoch = datetime.datetime.utcfromtimestamp(0)
utc_tz = datetime.timezone.utc


def add_epoch(seconds):
    assert seconds is not None
    assert seconds >= 0, 'seconds must be a positive number'

    return datetime.timedelta(seconds=seconds) + posix_epoch

def subtract_epoch(arg_dt, /):
    assert isinstance(arg_dt, datetime.datetime)
    epoch = posix_epoch.astimezone(utc_tz)
    utc_dt = arg_dt.astimezone(utc_tz)

    return utc_dt - epoch

def datetime_to_timestamp(arg_dt, /, *, integer=True):
    timestamp = subtract_epoch(arg_dt).total_seconds()

    if not integer:
        return timestamp
    return round(timestamp)

def timestamp_to_datetime(seconds, /):
    return add_epoch(seconds=seconds).astimezone(utc_tz)

