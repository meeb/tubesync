from datetime import datetime, timedelta
from huey import Huey
from huey.api import TaskWrapper
from huey.storage import SqliteStorage


class CompatibleTaskWrapper(TaskWrapper):
    def __call__(self, *args, **kwargs):
        kwargs.pop('creator', None)
        kwargs.pop('queue', None)
        kwargs.pop('repeat', None)
        repeat_until = kwargs.pop('repeat_until', None)
        schedule = kwargs.pop('schedule', None)
        _ret_saved = None if not hasattr(self, '_background_args') else self._background_args[3]
        self.remove_existing_tasks = kwargs.pop('remove_existing_tasks', _ret_saved)
        self.verbose_name = kwargs.pop('verbose_name', None)
        _delay = None
        _eta = None
        _priority = kwargs.pop('priority', None)
        if _priority and self._nice_priority_ordering:
            _priority = 1_000_000 - _priority
        if isinstance(schedule, dict):
            _delay = schedule.get('run_at')
            _priority = schedule.get('priority')
        elif isinstance(schedule, (int, timedelta, datetime)):
            _delay = schedule
        if isinstance(_delay, datetime):
            _eta = _delay
            _delay = None
        kwargs.update(dict(
            eta=_eta,
            expires=kwargs.get('expires', repeat_until),
            delay=_delay,
            priority=_priority,
        ))
        return self.huey.enqueue(self.s(*args, **kwargs))
    pass
CompatibleTaskWrapper.now = CompatibleTaskWrapper.call_local


class BGTaskHuey(Huey):
    def get_task_wrapper_class(self):
        return CompatibleTaskWrapper

def background(name=None, schedule=None, queue=None, remove_existing_tasks=False, **kwargs):
    from django_huey import db_task, task # noqa
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
    _nice_priority_ordering = kwargs.pop('nice_priority_ordering', None)
    if _priority and _nice_priority_ordering:
        _priority = 1_000_000 - _priority
    _retry_delay = max(
        (5+(2**4)),
        kwargs.pop('retry_delay', 0),
    )
    def _decorator(fn):
        _name = name
        if not _name:
            _name = '%s.%s' % (fn.__module__, fn.__name__)
        # retries=0, retry_delay=0,
        # priority=None, context=False,
        # name=None, expires=None,
        return db_task(
            context=kwargs.pop('context', False),
            delay=_delay,
            eta=_eta,
            expires=kwargs.pop('expires', None),
            name=_name,
            priority=_priority,
            queue=queue,
            retries=kwargs.pop('retries', 0),
            retry_delay=_retry_delay,
        )(fn)
    if fn:
        wrapper = _decorator(fn)
        wrapper.now = wrapper.call_local
        wrapper._background_args = _background_args
        wrapper._nice_priority_ordering = _nice_priority_ordering
        return wrapper
    return _decorator


class SqliteBGTaskHuey(BGTaskHuey):
    storage_class = SqliteStorage


def original_background(*args, **kwargs):
    from background_task.tasks import tasks
    return tasks.background(*args, **kwargs)


def sqlite_tasks(key, /, prefix=None):
    name_fmt = 'huey_{}'
    if prefix is None:
        prefix = ''
    if prefix:
        name_fmt = f'huey_{prefix}_' + '{}'
    name = name_fmt.format(key)
    return dict(
        huey_class='common.huey.SqliteBGTaskHuey',
        name=name,
        immediate=False,
        results=True,
        store_none=False,
        utc=True,
        compression=True,
        connection=dict(
            filename=f'/config/tasks/{name}.db',
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

