import logging
from django.conf import settings
from .utils import getenv


logging_level = logging.DEBUG if settings.DEBUG else logging.INFO
default_formatter = logging.Formatter(
    '%(asctime)s [%(name)s/%(levelname)s] %(message)s'
)
default_sh = logging.StreamHandler()
default_sh.setFormatter(default_formatter)
default_sh.setLevel(logging_level)


app_name = getenv('DJANGO_SETTINGS_MODULE')
first_part = app_name.split('.', 1)[0]
log = app_logger = logging.getLogger(first_part)
app_logger.addHandler(default_sh)
app_logger.setLevel(logging_level)

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

class NoWaitingForTasksFilter(logging.Filter):
    def filter(self, record):
        return 'waiting for tasks' != record.getMessage()

background_task_name = 'background_task.management.commands.process_tasks'
last_part = background_task_name.rsplit('.', 1)[-1]
background_task_formatter = logging.Formatter(
    f'%(asctime)s [{last_part}/%(levelname)s] %(message)s'
)
background_task_sh = logging.StreamHandler()
background_task_sh.addFilter(NoWaitingForTasksFilter())
background_task_sh.setFormatter(background_task_formatter)
background_task_sh.setLevel(logging_level)
background_task_logger = logging.getLogger(background_task_name)
background_task_logger.addHandler(background_task_sh)
background_task_logger.setLevel(logging_level)
