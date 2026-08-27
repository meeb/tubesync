import logging
from logging.handlers import SysLogHandler

handler = SysLogHandler
facility = SysLogHandler.LOG_LOCAL0

default_formatter = logging.Formatter(
    '%(asctime)s %(name)s: %(message)s',
    '%b %d %H:%M:%S',
)

default_handler = handler(
    address='/dev/log',
    facility=facility,
)
default_handler.setFormatter(default_formatter)
default_handler.setLevel(logging.DEBUG)

__all__ = ['default_formatter', 'default_handler', 'handler']
