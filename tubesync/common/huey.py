

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

