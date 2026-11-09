import logging
import sys
import threading

from typing import Any

from .syslog.std import facility, handler as syslog_handler

class LogStrFormatAdapter(logging.LoggerAdapter):
    def log(
        self,
        level: int,
        msg: Any,
        *args: Any,
        exc_info: Any = None,
        stack_info: bool = False,
        stacklevel: int = 1,
        extra: dict[str, Any] | None = None,
        **kwargs: Any
    ) -> None:
        if self.isEnabledFor(level):
            # Safely duplicate base context and layer on optional inline 'extra'
            extra_data = dict(self.extra)
            extra_data.update(extra or {})

            # Inject precise thread information
            current_thread = threading.current_thread()
            extra_data.update({
                'thread_name': current_thread.name,
                'thread_id': current_thread.ident,
                'is_main': current_thread is threading.main_thread(),
                'is_daemon': current_thread.daemon
            })

            # Native curly-brace string formatting using remaining kwargs
            if isinstance(msg, str):
                msg = msg.format(*args, **kwargs)

            # Pass to the logging engine
            self.logger.log(
                level, 
                msg, 
                exc_info=exc_info, 
                stack_info=stack_info, 
                stacklevel=stacklevel, 
                extra=extra_data
            )

# --- Fully Isolated Setup ---

name = 'yt-dlp'
# Create a dedicated logger instance
yt-dlp_logger = logging.getLogger(name)
yt-dlp_logger.setLevel(logging.DEBUG)

# CRITICAL: Prevent logs from bubbling up to the global root logger
yt-dlp_logger.propagate = False

# Create an isolated handler
yt-dlp_handler = syslog_handler(
    address='/dev/log',
    facility=facility,
)

# Attach a specific curly-brace formatter to this handler only
yt-dlp_formatter = logging.Formatter(
    fmt='[{tag}] {asctime} [Main: {is_main} | Daemon: {is_daemon} | Thread: {thread_name}] - {message}',
    style='{'
)
yt-dlp_handler.setFormatter(yt-dlp_formatter)

# Add the handler to our raw logger
yt-dlp_logger.addHandler(yt-dlp_handler)

# Wrap with our adapter
yt_dlp = LogStrFormatAdapter(yt-dlp_logger, {'tag': name})

# --- Verification ---

# This runs strictly through our isolated format layout
# yt_dlp.info("Isolated component {name} initialized.", name="Networking-Stack")
