from functools import wraps
from huey import CancelExecution


def CancelExecution_init(self, *args, retry=None, **kwargs):
    self.retry = retry
    super(CancelExecution, self).__init__(*args, **kwargs)
CancelExecution.__init__ = CancelExecution_init


def delay_to_eta(delay, /):
    from huey.utils import normalize_time
    return normalize_time(delay=delay)


def h_q_dict(q, /):
    return dict(
        scheduled=(q.scheduled_count(), q.scheduled(),),
        pending=(q.pending_count(), q.pending(),),
        result=(q.result_count(), list(q.all_results().keys()),),
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


def h_q_reset_tasks(q, /, *, maint_func=None):
    if isinstance(q, str):
        from django_huey import get_queue
        q = get_queue(q)
    # revoke to prevent pending tasks from executing
    for t in q._registry._registry.values():
        q.revoke_all(t, revoke_until=delay_to_eta(600))
    # clear scheduled tasks
    q.storage.flush_schedule()
    # clear pending tasks
    q.storage.flush_queue()
    # run the maintenance function
    def default_maint_func(queue, /, exception=None, status=None):
        if status is None:
            return
        if 'exception' == status and exception is not None:
            # log, but do not raise an exception
            from huey import logger
            logger.error(
                f'{queue.name}: maintenance function exception: {exception}'
            )
            return
        return True
    maint_result = None
    if maint_func is None:
        maint_func = default_maint_func
    if maint_func and callable(maint_func):
        try:
            maint_result = maint_func(q, status='started')
        except Exception as exc:
            maint_result = maint_func(q, exception=exc, status='exception')
            pass
        finally:
            maint_func(q, status='finished')
    # clear everything now that we are done
    q.storage.flush_all()
    q.flush()
    # return the results from the maintenance function
    return maint_result


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


def dynamic_retry(task_func=None, /, *args, **kwargs):
    if task_func is None:
        from django_huey import task as huey_task
        task_func = huey_task
    backoff_func = kwargs.pop('backoff_func', None)
    def default_backoff(attempt, /):
        return (5+(attempt**4))
    if backoff_func is None or not callable(backoff_func):
        backoff_func = default_backoff
    def deco(fn):
        @wraps(fn)
        def inner(*a, **kwa):
            backoff = backoff_func
            # the scoping becomes complicated when reusing functions
            try:
                _task = kwa.pop('task')
            except KeyError:
                pass
            else:
                task = _task
            try:
                return fn(*a, **kwa)
            except Exception as exc:
                try:
                    task is not None
                except NameError:
                    raise exc
                for attempt in range(1, 240):
                    if backoff(attempt) > task.retry_delay:
                        task.retry_delay = backoff(attempt)
                        break
                    # insanity, but handle it anyway
                    if 239 == attempt:
                        task.retry_delay = backoff(attempt)
                raise exc
        kwargs.update(dict(
            context=True,
            retry_delay=backoff_func(1),
        ))
        return task_func(*args, **kwargs)(inner)
    return deco

