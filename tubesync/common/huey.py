from __future__ import annotations

import contextlib
import datetime
import os
import socket
import subprocess
import threading
import time
import uuid

from functools import partial
from pathlib import Path
from select import select
from types import SimpleNamespace
from typing import ClassVar

from huey import (
    CancelExecution, Huey as huey_Huey,
    signals, utils,
)
from huey.api import Task, TaskLock
from huey.exceptions import TaskLockedException
from huey.serializer import Serializer
from huey.storage import SqliteStorage as huey_SqliteStorage

from .timestamp import datetime_to_timestamp, timestamp_to_datetime
from .utils import get_usable_cpu_count
from .yt_dlp import retry_django_db


def _set_acquired(self, value=True):
    if value is not True:
        return self.clear()
    try:
        self.__enter__()
    except TaskLockedException:
        return False
    else:
        return True
#TaskLock._set_acquired = _set_acquired
TaskLock.acquired = property(
    TaskLock.is_locked,
    _set_acquired,
    TaskLock.clear,
)


class SqliteStorage(huey_SqliteStorage):
    begin_sql = 'BEGIN IMMEDIATE'

    auto_vacuum_dict: ClassVar[dict[str, int]] = {'NONE': 0, 'FULL': 1, 'INCREMENTAL': 2}
    pragma_settings = SimpleNamespace(
        auto_vacuum = 'INCREMENTAL',
        journal_size_limit = 1024 * 1024 * 64,
        wal_autocheckpoint = 100,
        vacuum_pages = 10,
    )

    broker_settings = SimpleNamespace(
        # Max length of the queue of pending TCP connections
        SOCKET_BACKLOG = 128,

        # Chunk size in bytes for reading from socket stream buffers
        BUFFER_SIZE = 4,

        # Idle duration before select() yields to evaluate loop health
        SELECT_TIMEOUT_SEC = 60.0,

        # Network deadline for client connections to prevent blocking web threads
        PRODUCER_TIMEOUT_SEC = 1.5,

        # Bind globally to all interfaces on an OS-assigned ephemeral port
        BIND_ADDR = ('0.0.0.0', 0),

        # Start probing after 1 hour idle.
        TCP_KEEPALIVE_IDLE_SEC=3600,
        # Probe once per minute.
        TCP_KEEPALIVE_INTERVAL_SEC=60,
        # Give up after 5 unanswered probes.
        TCP_KEEPALIVE_COUNT=5,

        STORAGE_KEY_FMT = 'broker_endpoint:{}',
    )

    def __init__(self, name, *args, blocking=False, **kwargs):
        self.blocking = blocking
        super().__init__(name, *args, **kwargs)

        self._forked_child = False
        self._local = threading.local()
        self._queued = threading.Semaphore(0)
        self._queued_lock = threading.Lock()
        self._serializer = Serializer()
        self._stopping = threading.Event()
        self._storage_key = self.broker_settings.STORAGE_KEY_FMT.format(self.name)
        self.deserialize = self._serializer.deserialize
        self.serialize = self._serializer.serialize

        if callable(register_func := getattr(os, 'register_at_fork', None)):
            register_func(
                before=self._fork_parent_before,
                after_in_parent=self._fork_parent_after,
                after_in_child=self._fork_child_after
            )

        try:
            self.sock_consumer, self.sock_broker = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        except (AttributeError, ValueError, OSError):
            self.sock_consumer, self.sock_broker = socket.socketpair(socket.AF_INET, socket.SOCK_STREAM)

        self.start_broker_services()

    def _fork_parent_before(self):
        """Acquire locks to freeze storage in the parent process before cloning."""
        self.lock.acquire()

    def _fork_parent_after(self):
        """Release storage locks back to the parent process."""
        self.lock.release()

    def _fork_child_after(self):
        """Isolate the child process context after a fork occurs."""
        self._forked_child = True

        # Prevent garbage collection in the child
        self._local.inherited = set()
        self._local.inherited.add(getattr(self, '_conn', None))
        self._local.inherited.add(getattr(self._local, 'sock', None))

        # Clean up tracking variables first while the lock is still securely held
        self._conn = None
        self._local.sock = None
        self._local.addr = None

        self.lock.release()

    def _create_connection(self):
        conn = super()._create_connection()
        conn.execute(f'PRAGMA auto_vacuum = {self.pragma_settings.auto_vacuum}')
        conn.execute('PRAGMA foreign_keys = ON')
        conn.execute(f'PRAGMA journal_size_limit = {self.pragma_settings.journal_size_limit}')
        conn.execute('PRAGMA user_version = 1')
        conn.execute(f'PRAGMA wal_autocheckpoint={self.pragma_settings.wal_autocheckpoint}')
        # copied from huey_SqliteHuey to use EXTRA or NORMAL
        # instead of FULL or OFF
        conn.execute('pragma synchronous=%s' % (3 if self._fsync else 1))
        # take at most vacuum_pages off the free list
        conn.execute(f'PRAGMA incremental_vacuum({self.pragma_settings.vacuum_pages})')
        return conn

    def _cleanup_socket(self, sock, inputs_set):
        """Safely tears down a socket descriptor and untracks it from the active set."""
        if callable(close_func := getattr(sock, 'close', None)):
            with contextlib.suppress(Exception):
                close_func()
        inputs_set.discard(sock)

    def _configure_tcp_keepalive(self, sock):
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)

        # Linux uses TCP_KEEPIDLE; macOS and some other systems use TCP_KEEPALIVE.
        idle_option = getattr(
            socket,
            'TCP_KEEPIDLE',
            getattr(socket, 'TCP_KEEPALIVE', None),
        )
        options = (
            (idle_option, self.broker_settings.TCP_KEEPALIVE_IDLE_SEC),
            (
                getattr(socket, 'TCP_KEEPINTVL', None),
                self.broker_settings.TCP_KEEPALIVE_INTERVAL_SEC,
            ),
            (
                getattr(socket, 'TCP_KEEPCNT', None),
                self.broker_settings.TCP_KEEPALIVE_COUNT,
            ),
        )

        for option, value in options:
            if option is not None:
                with contextlib.suppress(OSError):
                    sock.setsockopt(socket.IPPROTO_TCP, option, value)

    def _get_pooled_socket(self, current_addr):
        """Manages thread-local socket reuse, ensuring configuration drift triggers updates safely."""
        cached_sock = getattr(self._local, 'sock', None)
        cached_addr = getattr(self._local, 'addr', None)

        if cached_sock and cached_addr != current_addr:
            with contextlib.suppress(Exception):
                cached_sock.close()
            cached_sock = None

        if cached_sock is None:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self._configure_tcp_keepalive(sock)
                sock.settimeout(self.broker_settings.PRODUCER_TIMEOUT_SEC)
                sock.connect(current_addr)

                self._local.sock = sock
                self._local.addr = current_addr
                return sock
            # ruff: ignore[BLE001]
            except Exception:
                return None

        return cached_sock

    def _get_primary_network_ip(self):
        """Resolves the host's actual network interface IP address by checking
        the routing table path to the secondary DNS anycast address.
        """
        with contextlib.suppress(Exception), socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(('8.8.4.4', 53))
            l_addr, _ =  s.getsockname()
            return l_addr
        return '127.0.0.1'

    def _get_remote_broker_address(self):
        """Fetches and unpacks the cached connection tuple from storage using Huey's native hooks."""
        data = self.peek_data(self._storage_key)
        if data:
            with contextlib.suppress(Exception):
                return self.deserialize(data)
        return None

    def _run_tcp_and_discovery_service(self):
        """Binds globally to all interfaces and registers its discoverable multi-host location."""
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind(self.broker_settings.BIND_ADDR)

        _, bound_port = server.getsockname()
        server.listen(self.broker_settings.SOCKET_BACKLOG)

        # Store the exact (ip, port) tuple directly using Huey's built-in serialization API
        addr_tuple = (self._get_primary_network_ip(), bound_port)
        self.put_data(self._storage_key, self.serialize(addr_tuple))
        self.sock_broker.sendall(b'1')

        inputs_set = {server}
        set_mutated = True
        while not self._stopping.is_set():
            if set_mutated:
                cached_inputs_list = list(inputs_set)
                set_mutated = False

            readable, _, _ = select(cached_inputs_list, [], [], self.broker_settings.SELECT_TIMEOUT_SEC)

            for sock in readable:
                if sock is server:
                    client, _ = sock.accept()
                    self._configure_tcp_keepalive(client)
                    inputs_set.add(client)
                    set_mutated = True
                else:
                    try:
                        if sock.recv(self.broker_settings.BUFFER_SIZE):
                            self.sock_broker.sendall(b'1')
                        else:
                            self._cleanup_socket(sock, inputs_set)
                            set_mutated = True
                    # ruff: ignore[BLE001]
                    except Exception:
                        self._cleanup_socket(sock, inputs_set)
                        set_mutated = True
        addr_tuple = ('0.0.0.0', bound_port)
        self.put_data(self._storage_key, self.serialize(addr_tuple))
        self.sock_broker.sendall(b'1')
        cached_inputs_list = list(inputs_set)
        for sock in cached_inputs_list:
            self._cleanup_socket(sock, inputs_set)

    def _unix_socket_handler(self):
        """Wakes up instantly via the local Unix gate to re-balance capacities to true DB depth."""
        first_time = r = True
        while not self._stopping.is_set() and r:
            if first_time:
                first_time = False
            else:
                self.sock_consumer.recv(self.broker_settings.BUFFER_SIZE)

            with self._queued_lock:
                ready_tasks = self.queue_size()

                # drain
                while self._queued.acquire(blocking=False):
                    pass

                # refill
                for _ in range(ready_tasks):
                    self._queued.release()

            r, _, _ = select([self.sock_consumer], [], [])
        self._queued.release()

    def close(self):
        self._stopping.set()
        self._queued.release()
        return super().close()

    def dequeue(self):
        if not self.blocking:
            with self._queued_lock:
                return super().dequeue()

        while self._queued.acquire():
            task = None
            try:
                with self._queued_lock:
                    if self._stopping.is_set():
                        return task
                    task = super().dequeue()
                    if task is not None:
                        return task
            finally:
                if task is None:
                    self._queued.release()

    def enqueue(self, *args, **kwargs):
        with self._queued_lock:
            res = super().enqueue(*args, **kwargs)

        addr = self._get_remote_broker_address()
        if addr and '0.0.0.0' != addr[0]:
            sock = self._get_pooled_socket(addr)
            if sock:
                try:
                    sock.sendall(b'w')
                # ruff: ignore[BLE001]
                except Exception:
                    self._local.addr = None
                    with contextlib.suppress(Exception):
                        sock.close()
                    self._local.sock = None

                    if (retry_sock := self._get_pooled_socket(addr)):
                        with contextlib.suppress(Exception):
                            retry_sock.sendall(b'w')
        return res

    def initialize_schema(self):
        super().initialize_schema()
        configured = self.pragma_settings.auto_vacuum
        valid = set(self.auto_vacuum_dict.values()) | set(self.auto_vacuum_dict.keys())
        assert configured in valid, 'auto_vacuum was invalid'
        current = self.sql('PRAGMA auto_vacuum', results=True)
        vacuum_db = True
        try:
            current = int(current[0][0])
            expected = int(self.auto_vacuum_dict.get(configured, configured))
        except (TypeError, ValueError,):
            pass
        else:
            vacuum_db = (expected != current)
        with self.db(close=True) as curs:
            curs.execute('PRAGMA wal_checkpoint(TRUNCATE)')
            if vacuum_db:
                curs.execute(f'PRAGMA auto_vacuum = {configured}')
                curs.execute('VACUUM')

    def start_broker_services(self):
        """Spawns background network loops if this process is the manager parent."""
        if self.blocking and self._forked_child is False:
            threading.Thread(target=self._run_tcp_and_discovery_service, daemon=True).start()
            threading.Thread(target=self._unix_socket_handler, daemon=True).start()


class Huey(huey_Huey):
    # do not use __len__ (pending_count) for bool
    def __bool__(self):
        return (self._registry._registry or self._registry._periodic_tasks)

    def _emit(self, signal, task, *args, **kwargs):
        kwargs['huey'] = self
        super()._emit(signal, task, *args, **kwargs)

    def create_consumer(self, **options):
        consumer = super().create_consumer(**options)
        suffix = f'worker.{consumer.worker_type}'
        consumer._logger = consumer._logger.getChild(suffix)
        return consumer

    def reschedule(self, task_id, eta):
        pc = self.pending_count()
        found = [
            t
            for t in self.pending(100)
            if t.id == task_id
        ]
        if not found and pc > 100:
            found = [
                t
                for t in self.pending()
                if t.id == task_id
            ]
        if not found:
            found = [
                t
                for t in self.scheduled()
                if t.id == task_id
            ]
        if not found:
            return False
        for t in found:
            self.revoke(t, revoke_once=True)
        task_eta = utils.normalize_time(eta=eta, utc=self.utc)
        for t in found:
            previous_id = t.id
            t.eta = task_eta
            t.id = t.create_id()
            t.revoke_id = f'r:{t.id}'
            try:
                from common.models import TaskHistory

                th = TaskHistory.objects.get(task_id=previous_id)
            # ruff: ignore[S110]
            except:
                pass
            else:
                # clone the old task history
                th.pk = None
                th._state.adding = True
                th.task_id = t.id
                th.save()
            self.enqueue(t)
        return True

    def scheduled_at_from_task(self, task_obj, /):
        scheduled_at = None
        if not (hasattr(task_obj, 'eta') and task_obj.eta):
            return None
        if self.utc:
            scheduled_at = task_obj.eta.replace(tzinfo=datetime.timezone.utc)
        else: # this path is unlikely
            scheduled_at = timestamp_to_datetime(
                datetime_to_timestamp(task_obj.eta, integer=False),
            ).astimezone(tz=datetime.timezone.utc)
        return scheduled_at


class SqliteHuey(Huey):
    storage_class = SqliteStorage


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


def start_consumer(queue_name):
    assert isinstance(queue_name, str), type(queue_name)
    svc_name = queue_name.replace('_', '-')
    svc_dir = Path('/run') / 'service' / svc_name

    try:
        if not all((
            svc_dir.is_dir(),
            (svc_dir / 'supervise').is_dir(),
            (svc_dir / 'supervise' / 'control').is_fifo(),
        )):
            return
    except PermissionError:
        pass
    else:
        subprocess.Popen(
            [ '/command/s6-svc', '-U', str(svc_dir) ],
            stdout=-1, stderr=-1, start_new_session=True,
        )


def h_q_reset_maint_func(queue, /, exception=None, status=None):
        if status is None:
            return
        elif 'started' == status:
            start_consumer(queue.name)
        elif 'exception' == status and exception is not None:
            # log, but do not raise an exception
            from huey.api import logger
            logger.error(
                f'{queue.name}: maintenance function exception: {exception}'
            )
            return
        return True

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
            from huey.api import logger
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
        # ruff: ignore[BLE001]
        except Exception as exc:
            maint_result = maint_func(q, exception=exc, status='exception')
        finally:
            maint_func(q, status='finished')
    # clear everything now that we are done
    q.storage.flush_all()
    q.flush()
    # return the results from the maintenance function
    return maint_result


def sqlite_tasks(key, /, prefix=None, thread=None, workers=None, *, tasks_dir=None):
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
            workers = max(2, get_usable_cpu_count() // 2)
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
            filename=str(Path(tasks_dir or '/config/tasks') / f'{name}.db'),
            fsync=True,
            isolation_level='IMMEDIATE', # _create_connection sets this to None
            strict_fifo=True,
            timeout=60,
        ),
        consumer=dict(
            workers=workers if thread else 1,
            worker_type='thread' if thread else 'process',
            max_delay=20.0,
            max_tasks=10_000,
            check_worker_health=True,
            health_check_interval=30.0,
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


# Signal handlers shared between queues

def on_executing_remove_duplicates(signal_name, task_obj, exception_obj=None, /, *, huey=None):
    if signals.SIGNAL_EXECUTING != signal_name:
        return
    assert exception_obj is None
    assert huey is not None
    assert hasattr(huey, 'pending') and callable(huey.pending)
    assert hasattr(huey, 'revoke_by_id') and callable(huey.revoke_by_id)
    assert hasattr(huey, 'scheduled') and callable(huey.scheduled)
    assert signals.SIGNAL_EXECUTING == signal_name

    from common.models import TaskHistory

    try:
        th = TaskHistory.objects.get(task_id=str(task_obj.id))
    except TaskHistory.DoesNotExist:
        return
    else:
        if not th.remove_duplicates:
            return

    def task_generator(queue):
        for t in queue.pending():
            yield t
        for t in queue.scheduled():
            yield t

    def waiting_id_generator(queue, task_obj):
        b = task_obj
        for a in task_generator(queue):
            matches = (
                a.name == b.name and
                a.id != b.id and
                # revoke lower priority
                a.priority <= b.priority and
                # revoke tasks that have executed fewer times
                a.retries >= b.retries and
                a.data == b.data
            )
            if matches:
                yield a.id

    for task_id in waiting_id_generator(queue=huey, task_obj=task_obj):
        huey.revoke_by_id(task_id, revoke_once=True)


def on_interrupted(signal_name, task_obj, exception_obj=None, /, *, huey=None):
    if signals.SIGNAL_INTERRUPTED != signal_name:
        return
    assert exception_obj is None
    assert huey is not None
    assert hasattr(huey, 'enqueue') and callable(huey.enqueue)
    huey.enqueue(task_obj)


storage_key_prefix = 'task_history:'


def historical_task(signal_name, task_obj, exception_obj=None, /, *, huey=None):
    signal_time = time.monotonic()
    signal_dt = datetime.datetime.now(datetime.timezone.utc)
    assert huey is not None
    assert hasattr(huey, 'get') and callable(huey.get)
    assert hasattr(huey, 'put') and callable(huey.put)

    from common.models import TaskHistory
    add_to_elapsed_signals = frozenset((
        signals.SIGNAL_TIMEOUT,
        signals.SIGNAL_INTERRUPTED,
        signals.SIGNAL_ERROR,
        signals.SIGNAL_CANCELED,
        signals.SIGNAL_COMPLETE,
    ))
    recorded_signals = frozenset((
        signals.SIGNAL_REVOKED,
        signals.SIGNAL_EXPIRED,
        signals.SIGNAL_LOCKED,
        signals.SIGNAL_EXECUTING,
        signals.SIGNAL_RETRYING,
        signals.SIGNAL_RATE_LIMITED,
    )) | add_to_elapsed_signals
    storage_key = f'{storage_key_prefix}{task_obj.id}'
    task_obj_attr = '_signals_history'

    history = getattr(task_obj, task_obj_attr, None)
    if history is None:
        # pull it from storage, or initialize it
        history = huey.get(
            key=storage_key,
            peek=True,
        ) or dict(
            created=signal_dt,
            data=(task_obj.args, repr(task_obj.kwargs),),
            elapsed=0,
            module=task_obj.__module__,
            name=task_obj.name,
        )
        setattr(task_obj, task_obj_attr, history)
    assert history is not None
    history['modified'] = signal_dt

    if signal_name in recorded_signals:
        history[signal_name] = signal_time
    if signal_name in add_to_elapsed_signals and signals.SIGNAL_EXECUTING in history:
        history['elapsed'] += signal_time - history[signals.SIGNAL_EXECUTING]
    if signals.SIGNAL_COMPLETE in history:
        huey.get(key=storage_key)
    else:
        huey.put(key=storage_key, data=history)
    # created never used
    # ruff: ignore[RUF059]
    th, created = retry_django_db(5)(TaskHistory.objects.get_or_create)(
        task_id=str(task_obj.id),
        name=f'{task_obj.__module__}.{task_obj.name}',
        queue=huey.name,
    )
    th.priority = task_obj.priority
    th.task_params = list((
        list(task_obj.args),
        repr(task_obj.kwargs),
    ))
    if signal_name == signals.SIGNAL_EXECUTING:
        th.attempts += 1
        th.start_at = signal_dt
    elif exception_obj is not None:
        th.failed_at = signal_dt
        th.last_error = str(exception_obj)
    elif signal_name == signals.SIGNAL_ENQUEUED:
        scheduled_at = huey.scheduled_at_from_task(task_obj)
        if scheduled_at:
            th.scheduled_at = scheduled_at
        if not th.verbose_name:
            try:
                from django.core.exceptions import ValidationError
                from sync.models import Media, Source
            # ruff: ignore[S110]
            except:
                pass
            else:
                try:
                    key = task_obj.args[0]
                    instance_uuid_str = str(key)
                    instance_uuid = uuid.UUID(instance_uuid_str)
                except IndexError:
                    key = None
                except RuntimeError:
                    instance_uuid_str = None
                except ValueError:
                    instance_uuid = None
                else:
                    for model in (Source, Media,):
                        try:
                            model_instance = model.objects.get(pk=instance_uuid)
                        except (model.DoesNotExist, ValidationError,):
                            pass
                        else:
                            if hasattr(model_instance, 'key'):
                                th.verbose_name = f'{th.name} with: {model_instance.key}'
                                if hasattr(model_instance, 'name'):
                                    th.verbose_name += f' / {model_instance.name}'
                            break
    elif signal_name == signals.SIGNAL_SCHEDULED:
        scheduled_at = huey.scheduled_at_from_task(task_obj)
        if scheduled_at:
            th.scheduled_at = scheduled_at
    th.end_at = signal_dt
    th.elapsed = history['elapsed']
    th.save()


# Registration of shared signal handlers


def register_huey_signals():
    from django import db
    from django_huey import DJANGO_HUEY, get_queue, pre_execute, post_execute, signal

    def close_db(task, task_value=None, exception=None, /, *, huey=None):
        assert huey is not None
        assert hasattr(huey, 'immediate')
        # Guard against immediate mode and transactions
        if (
            huey is None or getattr(huey, 'immediate', True) or
            any(dbw.in_atomic_block for dbw in db.connections.all())
        ):
            return
        db.close_old_connections()

    for qn in DJANGO_HUEY.get('queues', dict()):
        q = get_queue(qn)

        # hooks to clean up database connections at task boundaries
        pre_execute(queue=qn, name='close_db')(partial(close_db, huey=q))
        post_execute(queue=qn, name='close_db')(partial(close_db, huey=q))

        # signals for tracking / maintenance of tasks
        signal(signals.SIGNAL_INTERRUPTED, queue=qn)(on_interrupted)
        signal(queue=qn)(historical_task)
        signal(signals.SIGNAL_EXECUTING, queue=qn)(on_executing_remove_duplicates)

        # clean up old history and results from storage
        now_time = time.monotonic()
        now_dt = datetime.datetime.now(datetime.timezone.utc)
        # ruff: ignore[SIM118]
        for key in q.all_results().keys():
            if not key.startswith(storage_key_prefix):
                continue
            history = q.get(peek=True, key=key)
            if not isinstance(history, dict):
                continue
            if 'created' not in history:
                # Set an incorrect created time to ensure eventual removal.
                history['created'] = now_dt
                q.put(key=key, data=history)
                # Attempt to calculate an accurate age.
                # This doesn't work all the time,
                # so the created datetime is the fail-safe case.
                seconds = now_time - history.get(signals.SIGNAL_EXECUTING, now_time)
                age = datetime.timedelta(
                    seconds=max(0, seconds),
                )
            else:
                age = now_dt - history['created']
            if age > datetime.timedelta(days=7):
                result_key = key[len(storage_key_prefix) :]
                q.get(peek=False, key=result_key)
                q.get(peek=False, key=key)


class BackoffAlgorithm:
    # ruff: ignore[RUF012]
    _registry = {}
    key = None

    @staticmethod
    def calculate(attempt: int) -> int:
        raise NotImplementedError()

    @classmethod
    def lookup(cls, key: str) -> BackoffAlgorithm | None:
        return cls._registry.get(key, None)

    @classmethod
    def register(cls, algorithm: BackoffAlgorithm) -> str | None:
        """
        Merges a BackoffAlgorithm subclass into the base class registry.
        """
        algorithm_key = issubclass(algorithm, cls) and getattr(algorithm, 'key', cls.key)
        if algorithm_key:
            cls._registry.update({ algorithm_key: algorithm })
            return algorithm_key


class DjangoBackgroundTasksBackoff(BackoffAlgorithm):
    key = 'Django-Background-Tasks'

    @staticmethod
    def calculate(attempt: int) -> int:
        # The exact formula used by django-background-tasks
        return 5 + (attempt ** 4)


class AttemptsTask(Task):
    """
    A Task base class that relies entirely on Task for defaults.
    Resolves algorithms using string keys mapped onto the BackoffAlgorithm base class.
    """

    backoff_base_class = BackoffAlgorithm

    def __init__(self, *args, backoff_class=None, **kwargs):
        super().__init__(*args, **kwargs)

        self.backoff_class = backoff_class or self.backoff_class
        if self.backoff_class:
            # Register directly onto the algorithm base class
            self._backoff_key = self.backoff_base_class.register(self.backoff_class)

        algo_key = getattr(self, '_backoff_key', None)
        retry_backoff = kwargs.get('retry_backoff', None)
        if retry_backoff is None and not self.default_retry_backoff and algo_key:
            self.retry_backoff = 1

    @property
    def retry_delay(self) -> int:
        attempt = getattr(self, '_custom_attempt_counter', 1)
        initial_delay = getattr(self, '_initial_retry_delay', 0)
        retry_backoff = getattr(self, 'retry_backoff', None)

        algo_key = getattr(self, '_backoff_key', None)
        algo_class = self.backoff_base_class.lookup(algo_key)

        if retry_backoff is None or 0 == retry_backoff:
            current_delay = getattr(self, '_retry_delay', initial_delay)
            return current_delay
        elif algo_class and issubclass(algo_class, self.backoff_base_class):
            # Always exceed the initial delay value
            while algo_class.calculate(attempt) <= initial_delay:
                attempt += 1
            self._custom_attempt_counter = attempt
            return algo_class.calculate(attempt)

        # Fallback Mode: Exponential math using Task-resolved defaults
        return initial_delay * (self.retry_backoff ** max(0, attempt - 1))

    @retry_delay.setter
    def retry_delay(self, value):
        current_state = getattr(self, '_custom_attempt_counter', None)

        if current_state is None:
            self._initial_retry_delay = value
            self._custom_attempt_counter = 1
        else:
            self._custom_attempt_counter = 1 + current_state
        self._retry_delay = value
