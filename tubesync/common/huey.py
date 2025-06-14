from functools import wraps


def delay_to_eta(delay, /):
    from huey.utils import normalize_time
    return normalize_time(delay=delay)


def h_q_dict(q, /):
    return dict(
        scheduled=(q.scheduled_count(), q.scheduled(),),
        pending=(q.pending_count(), q.pending(),),
        result=(q.result_count(), q.all_results(),),
    )


def h_q_tuple(q, /):
    if isinstance(q, str):
        from django_huey import get_queue
        q = get_queue(q)
    return (
        q.name,
        list(q._registry._registry.keys()),
        h_q_dict(q),
    )


def sqlite_tasks(key, /, prefix=None):
    name_fmt = 'huey_{}'
    if prefix is None:
        prefix = ''
    if prefix:
        name_fmt = f'huey_{prefix}_' + '{}'
    name = name_fmt.format(key)
    return dict(
        huey_class='huey.SqliteHuey',
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


def exponential_backoff(task_func=None, /, *args, *, **kwargs):
    if task_func is None:
        from django_huey import task as huey_task
        task_func = huey_task
    def backoff(attempt, /):
        return (5+(attempt**4))
    def deco(fn):
        @wraps(fn)
        def inner(*a, **kwa):
            task = kwa.pop('task')
            try:
                return fn(*a, **kwa)
            except Exception as exc:
                attempt = 1
                while task.retry_delay <= backoff(attempt):
                    attempt += 1
                task.retry_delay = backoff(attempt)
                raise exc
        kwargs.update(dict(
            context=True,
            retry_delay=backoff(1),
        ))
        return task_func(*args, **kwargs)(inner)
    return deco

