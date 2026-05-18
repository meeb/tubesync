import logging
from logging.handlers import SysLogHandler


default_formatter = logging.Formatter(
    '%(asctime)s [%(name)s/%(levelname)s] %(message)s'
)
default_handler = logging.StreamHandler()
default_handler.setFormatter(default_formatter)
default_handler.setLevel(logging.INFO)

syslog_formatter = logging.Formatter(
    '%(asctime)s %(name)s: %(message)s',
    '%b %d %H:%M:%S',
)
syslog_handler = SysLogHandler(
    address='/dev/log',
    facility=SysLogHandler.LOG_LOCAL0,
)
syslog_handler.setFormatter(syslog_formatter)
syslog_handler.setLevel(logging.DEBUG)

