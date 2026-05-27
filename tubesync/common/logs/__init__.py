from . import syslog
from ._default import default_formatter, default_handler
from ._filters import RemoveSpecificLogFilter
from ._logger import app_logger, logger


logger = logger(__name__)

__all__ = [
    'app_logger',
    'default_formatter',
    'default_handler',
    'logger',
    'syslog',
    'RemoveSpecificLogFilter',
]
