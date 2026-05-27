import logging
from django.conf import settings
from .logs import app_logger, default_handler
from .logs.syslog.std import default_handler as syslog_default_handler


log = app_logger

default_handler.setLevel(logging.INFO)
if settings.DEBUG:
    default_handler.setLevel(logging.DEBUG)

app_logger.propagate = False
app_logger.addHandler(default_handler)
app_logger.addHandler(syslog_default_handler)

if (
    hasattr(settings, 'DATABASES') and
    'default' in settings.DATABASES.keys() and
    '_msgs' in settings.DATABASES.get('default', dict()).keys() and
    ( _msgs := settings.DATABASES.get('default', dict()).pop('_msgs', False) )
):
    for _spec in _msgs:
        try:
            _level, _msg = _spec
        except ValueError:
            _level, _msg = logging.INFO, next(iter(_spec))
        app_logger.log(_level, _msg)

