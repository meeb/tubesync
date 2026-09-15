import logging


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
        except (TypeError, ValueError):
            self.line_number = None

        # Normalize the log level input to a Python integer
        try:
            if isinstance(level, str):
                self.level_number = logging.getLevelName(level.upper())
            else:
                self.level_number = int(level or None)
        except (TypeError, ValueError):
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
        pass_the_record = (

            # If no arguments were configured, let everything pass through
            self.no_criteria or

            # Check Message Content Start
            (self.msg_starts_with and not record.getMessage().startswith(self.msg_starts_with)) or

            # Check Logger Name Path
            (self.logger_name and record.name != self.logger_name) or

            # Check Function Name
            (self.func_name and record.funcName != self.func_name) or

            # Check Line Number
            (self.line_number is not None and record.lineno != self.line_number) or

            # Check Log Level
            (self.level_number is not None and record.levelno != self.level_number) or

            False

        )

        # Drop the log if all active criteria are met
        return pass_the_record


__all__ = [
    'RemoveSpecificLogFilter',
]

