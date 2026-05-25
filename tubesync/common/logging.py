import logging
from logging.handlers import SysLogHandler


class RemoveSpecificLogFilter(logging.Filter):
    def __init__(
        self,
        *,
        msg_starts_with=None,
        logger_name=None,
        func_name=None,
        line_number=None,
        level=None,
    ):
        super().__init__()

        self.msg_starts_with = msg_starts_with
        self.logger_name = logger_name
        self.func_name = func_name
        try:
            self.line_number = int(line_number) if line_number is not None else None
        except Exception:
            self.line_number = None

        # Normalize the log level input to a Python integer
        try:
            if isinstance(level, str):
                self.level_number = logging.getLevelName(level.upper())
            else:
                self.level_number = int(level)
        except Exception:
            self.level_number = None

        # Track if any filtering rules were actually provided
        self.no_criteria = all([
            self.msg_starts_with is None,
            self.logger_name is None,
            self.func_name is None,
            self.line_number is None,
            self.level_number is None
        ])

    def filter(self, record):
        # If no arguments were configured, let everything pass through
        if self.no_criteria:
            return True

        # Check Message Content Start
        if self.msg_starts_with and not record.getMessage().startswith(self.msg_starts_with):
            return True

        # Check Logger Name Path
        if self.logger_name and record.name != self.logger_name:
            return True

        # Check Function Name
        if self.func_name and record.funcName != self.func_name:
            return True

        # Check Line Number
        if self.line_number is not None and record.lineno != self.line_number:
            return True

        # Check Log Level
        if self.level_number is not None and record.levelno != self.level_number:
            return True

        # Drop the log if all active criteria are met
        return False


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

