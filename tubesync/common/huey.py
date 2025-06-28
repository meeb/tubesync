import os
from functools import wraps
from huey import (
    CancelExecution, SqliteHuey as huey_SqliteHuey,
    signals, utils,
)


class SqliteHuey(huey_SqliteHuey):
    def _emit(self, signal, task, *args, **kwargs):
        kwargs['huey'] = self
        super()._emit(signal, task, *args, **kwargs)


def CancelExecution_init(self, *args, retry=None, **kwargs):
    self.retry = retry
    super(CancelExecution, self).__init__(*args, **kwargs)
CancelExecution.__init__ = CancelExecution_init


def delay_to_eta(delay, /):
    return utils.normalize_time(delay=delay)


def h_q_dict(q, /):
    return dict(
        scheduled=(q.scheduled_count(), q.scheduled(),),
        pending=(q.pending_count(), q.pending(),),
        running=q._tasks_in_flight,
        results=(q.result_count(), list(q.all_results().keys()),),
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

# Configuration convenience helpers

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


def sqlite_tasks(key, /, prefix=None, thread=None, workers=None):
    name_fmt = 'huey_{}'
    if prefix:
        name_fmt = f'huey_{prefix}_' + '{}'
    name = name_fmt.format(key)
    thread = thread is True
    try:
        workers = int(workers)
    except TypeError:
        workers = 2
    finally:
        if 0 >= workers:
            workers = os.cpu_count()
        elif 1 == workers:
            thread = False
    return dict(
        huey_class='common.huey.SqliteHuey',
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
            workers=workers if thread else 1,
            worker_type='thread' if thread else 'process',
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

# Decorators

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

# Signal handlers shared between queues

def on_interrupted(signal_name, task_obj, exception_obj=None, /, *, huey=None):
    if signals.SIGNAL_INTERRUPTED != signal_name:
        return
    assert exception_obj is None
    assert hasattr(huey, 'enqueue') and callable(huey.enqueue)
    huey.enqueue(task_obj)

def historical_task(signal_name, task_obj, exception_obj=None, /, *, huey=None):
    signal_time = utils.time_clock()

    add_to_elapsed_signals = frozenset((
        signals.SIGNAL_INTERRUPTED,
        signals.SIGNAL_CANCELED,
        signals.SIGNAL_LOCKED,
        signals.SIGNAL_ERROR,
        signals.SIGNAL_RETRYING,
        signals.SIGNAL_COMPLETE,
    ))
    recorded_signals = frozenset((
        signals.SIGNAL_REVOKED,
        signals.SIGNAL_EXPIRED,
        signals.SIGNAL_EXECUTING,
    )) | add_to_elapsed_signals
    storage_key = f'task_history:{task_obj.id}'
    task_obj_attr = '_signals_history'

    history = getattr(task_obj, task_obj_attr, None)
    if history is None:
        # pull it from storage, or initialize it
        history = huey.get(
            key=storage_key,
            peek=True,
        ) or dict(
            data=task_obj.data,
            elapsed=0,
            module=task_obj.__module__,
            name=task_obj.name,
        )
        setattr(task_obj, task_obj_attr, history)
    assert history is not None

    if signal_name in recorded_signals:
        history[signal_name] = signal_time
    if signal_name in add_to_elapsed_signals and signals.SIGNAL_EXECUTING in history:
        history['elapsed'] += signal_time - history[signals.SIGNAL_EXECUTING]
    if signals.SIGNAL_COMPLETE in history:
        huey.get(key=storage_key)
    else:
        huey.put(key=storage_key, data=history)

# Registration of shared signal handlers

def register_huey_signals():
    from django_huey import DJANGO_HUEY, signal
    for qn in DJANGO_HUEY.get('queues', dict()):
        signal(signals.SIGNAL_INTERRUPTED, queue=qn)(on_interrupted)
        signal(queue=qn)(historical_task)

