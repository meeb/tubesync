from datetime import datetime, timedelta
from huey import Huey
from huey.api import TaskWrapper
from huey.storage import SqliteStorage


class CompatibleTaskWrapper(TaskWrapper):
    def backoff(self, attempt, /):
        return (5+(attempt**4))

    def backoff_list(self, retries, /):
        if not self._backoff_list:
            self._backoff_list = [ self.backoff(a) for a in range(retries, -1, -1) ]
        return self._backoff_list

    def __call__(self, *args, **kwargs):
        kwargs.pop('creator', None)
        kwargs.pop('queue', None)
        # TODO: tcely: actually implement repeat using the scheduler
        self.repeat = kwargs.pop('repeat', None)
        self.repeat_until = kwargs.pop('repeat_until', None)
        schedule = kwargs.pop('schedule', None)
        _ret_saved = None if not hasattr(self, '_background_args') else self._background_args[3]
        self.remove_existing_tasks = kwargs.pop('remove_existing_tasks', _ret_saved)
        self.verbose_name = kwargs.pop('verbose_name', None)
        _delay = None
        _eta = None
        _priority = kwargs.pop('priority', None)
        if _priority and self._nice_priority_ordering:
            _priority = 1_000_000_000 - _priority
            if _priority < 0:
                _priority = 0
        if isinstance(schedule, dict):
            _delay = schedule.get('run_at')
            _priority = schedule.get('priority')
        elif isinstance(schedule, (int, timedelta, datetime)):
            _delay = schedule
        if isinstance(_delay, datetime):
            _eta = _delay
            _delay = None
        _retries = kwargs.pop('retries', 0)
        _retry_delay = max(
            self.backoff_list(_retries)[_retries],
            kwargs.pop('retry_delay', 0),
        )
        kwargs.update(dict(
            eta=_eta,
            expires=kwargs.get('expires', self.repeat_until),
            delay=_delay,
            priority=_priority,
            retries=None if _retries <= 0 else _retries,
            retry_delay=_retry_delay,
        ))
        return self.huey.enqueue(self.s(*args, **kwargs))
    pass
CompatibleTaskWrapper.now = CompatibleTaskWrapper.call_local


class BGTaskHuey(Huey):
    def get_task_wrapper_class(self):
        return CompatibleTaskWrapper

def background(name=None, schedule=None, queue=None, remove_existing_tasks=False, **kwargs):
    from django.conf import settings
    from django_huey import db_task, task # noqa
    def backoff(attempt, /):
        return (5+(attempt**4))
    def backoff_list(retries, /):
        return [ backoff(a) for a in range(retries, -1, -1) ]
    fn = None
    if name and callable(name):
        fn = name
        name = None
    _background_args = (name, schedule, queue, remove_existing_tasks,)
    _delay = None
    _eta = None
    _priority = None
    if isinstance(schedule, dict):
        _delay = schedule.get('run_at')
        _priority = schedule.get('priority')
    elif isinstance(schedule, (int, timedelta, datetime)):
        _delay = schedule
    if isinstance(_delay, datetime):
        _eta = _delay
        _delay = None
    _max_attempts = getattr(settings, 'MAX_ATTEMPTS', 25)
    _nice_priority_ordering = (
        'ASC' == getattr(settings, 'BACKGROUND_TASK_PRIORITY_ORDERING', 'DESC')
    )
    if _priority and _nice_priority_ordering:
        _priority = 1_000_000_000 - _priority
        # This was a crazy low priority to set,
        # but we can just use our lowest value instead.
        if _priority < 0:
            _priority = 0
    _retries = kwargs.pop('retries', 0)
    _retry_delay = max(
        backoff_list(_retries)[_retries],
        kwargs.pop('retry_delay', 0),
    )
    def _decorator(fn):
        # retries=0, retry_delay=0,
        # priority=None, context=False,
        # name=None, expires=None,
        return db_task(
            context=kwargs.pop('context', False),
            delay=_delay,
            eta=_eta,
            expires=kwargs.pop('expires', None),
            name=name,
            priority=_priority,
            queue=queue,
            retries=None if _retries <= 0 else _retries,
            retry_delay=_retry_delay,
        )(fn)
    if fn:
        wrapper = _decorator(fn)
        wrapper.now = wrapper.call_local
        wrapper._background_args = _background_args
        wrapper._backoff_list = backoff_list(_retries)
        wrapper._max_attempts = _max_attempts
        wrapper._nice_priority_ordering = _nice_priority_ordering
        return wrapper
    return _decorator


class SqliteBGTaskHuey(BGTaskHuey):
    storage_class = SqliteStorage


def original_background(*args, **kwargs):
    from background_task.tasks import tasks
    return tasks.background(*args, **kwargs)


def sqlite_tasks(
    key, /, directory='/config/tasks',
    huey_class='SqliteBGTaskHuey', prefix=None,
):
    cls_name = huey_class
    if '.' not in cls_name and cls_name in globals().keys():
        from inspect import getmodule
        _module = getmodule(eval(cls_name))
        if _module and hasattr(_module, '__name__'):
            if '__main__' != _module.__name__:
                cls_name = f'{_module.__name__}.{huey_class}'
    name_fmt = 'huey'
    if prefix is not None:
        name_fmt += f'_{prefix}'
    name_fmt += '_{}'
    name = name_fmt.format(key)
    return dict(
        huey_class=cls_name,
        name=name,
        immediate=False,
        results=True,
        store_none=False,
        utc=True,
        compression=True,
        connection=dict(
            filename=f'{directory}/{name}.db',
            fsync=True,
            strict_fifo=True,
        ),
        consumer=dict(
            workers=1,
            worker_type='process',
            max_delay=20.0,
            flush_locks=True,
            scheduler_interval=10,
            simple_log=False,
            # verbose has three positions:
            # DEBUG: True
            # INFO: None
            # WARNING: False
            verbose=False,
        ),
    )

