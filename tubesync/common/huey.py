from huey import Huey, TaskWrapper
from huey.storage import SqliteStorage


class CompatibleTaskWrapper(TaskWrapper):
    pass
CompatibleTaskWrapper.now = CompatibleTaskWrapper.call_local


class BGTaskHuey(Huey):
    def get_task_wrapper_class(self):
        return CompatibleTaskWrapper


class SqliteBGTaskHuey(BGTaskHuey):
    storage_class = SqliteStorage


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

