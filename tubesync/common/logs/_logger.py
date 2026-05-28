import logging
import os


logger = lambda name=None: logging.getLogger(
    __name__.rsplit('.', 1)[0] if name is None else name
)

app_logger = logger()
app_name = os.getenv('DJANGO_SETTINGS_MODULE', str()).strip()
if app_name:
    first_part = app_name.split('.', 1)[0]
    app_logger = logger(first_part)
app_logger.setLevel(logging.DEBUG)

__all__ = ['app_logger', 'logger']
