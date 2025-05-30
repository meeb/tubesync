from huey import Huey, TaskWrapper
from huey.storage import SqliteStorage
from django_huey import db_task, task # noqa


class CompatibleTaskWrapper(TaskWrapper):
    pass
CompatibleTaskWrapper.now = CompatibleTaskWrapper.call_local


class BGTaskHuey(Huey):
    def get_task_wrapper_class(self):
        return CompatibleTaskWrapper

def background(name=None, schedule=None, queue=None, remove_existing_tasks=False, **kwargs):
    fn = None
    if name and callable(name):
        fn = name
        name = None
    _priority = None
    if isinstance(schedule, dict):
        _priority = schedule.get('priority')
    if _priority and kwargs.pop('nice_priority_ordering'):
        _priority = 1_000_000 - _priority
    _retry_delay = max(
        (5+(2**4)),
        kwargs.pop('retry_delay') or 0,
    )
    def _decorator(fn):
        _name = name
        if not _name:
            _name = '%s.%s' % (fn.__module__, fn.__name__)
        # retries=0, retry_delay=0,
        # priority=None, context=False,
        # name=None, expires=None,
        _huey_decorator = db_task(
            context=kwargs.pop('context') or False,
            expires=kwargs.pop('expires') or None,
            name=_name,
            priority=_priority,
            queue=queue,
            retries=kwargs.pop('retries') or 0,
            retry_delay=_retry_delay,
        )
        return _huey_decorator
    if fn:
        wrapper = _decorator(fn)
        wrapper.now = wrapper.call_local
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

