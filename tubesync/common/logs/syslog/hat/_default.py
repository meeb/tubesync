import collections
import contextlib
import logging
import math
import os
import queue
import random
import socket
import ssl
import threading
import time

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone as dt_timezone
from typing import Optional, Tuple

from ._logger import logger

try:
    from hat.syslog import common, encoder
    from hat.syslog.handler import (
        SyslogHandler as hat_syslog_handler_SyslogHandler,
        _ThreadState,
        _create_dropped_msg,
        _record_to_msg,
    )
except ImportError:
    handler = None
else:
    handler = True

default_formatter = logging.Formatter()

logger = logger()

__all__ = ['default_formatter', 'default_handler', 'handler']

if not handler:
    # Create only enough for tests to fail instead of creating hard to diagnose errors
    from ..std import default_handler as std_default_handler, handler
    class MockSyslogHandler(handler):
        def __init__(self, host, port, comm_type, queue_size, reconnect_delay, *args, **kwargs):
            self.host = host
            self.port = port
            self.comm_type = comm_type
            self.queue_size = queue_size
            self.reconnect_delay = reconnect_delay
            args = ()
            kwargs = {}
            kwargs['address'] = std_default_handler.address
            kwargs['facility'] = std_default_handler.facility
            super().__init__(*args, **kwargs)
    handler = MockSyslogHandler
    default_handler = handler('127.0.0.1', 6514, 'UDP', 1024, 5)
else:
    _SOCKET_FACTORIES = {
        common.CommType.TCP: lambda state, ctx: _create_tcp_socket(state),
        common.CommType.TLS: lambda state, ctx: _create_tcp_socket(state, ctx),
        common.CommType.UDP: lambda state, ctx: _create_udp_socket(state),
    }


    @dataclass
    class _ReconnectionState:
        timeout: float = 5.0
        budget: int = 60
        cap: int = 1000
        snapshot: int = -1
        success: int = 10
        failure: int = 5


    @dataclass(frozen=True)
    class RetryItem:
        """Encapsulates a structured syslog entry in the retry transport pipeline."""
        synthetic: bool
        msg: common.Msg


    @dataclass
    class ThreadScoreboard:
        """Tracks precision execution lifecycles and diagnostic markers for background workers."""
        start: Tuple[float, int] = field(default_factory=lambda: (time.time(), time.monotonic_ns()))
        alive: Optional[Tuple[float, int]] = None
        initialized: Optional[Tuple[float, int]] = None
        previous_start: Optional[Tuple[float, int]] = None


    def _create_tcp_socket(state, ctx=None):
        """Establishes an optimized TCP or wrapped TLS stream transport connection."""
        s = socket.create_connection((state.host, state.port), timeout=5.0)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        if ctx:
            s = ctx.wrap_socket(s)
        return s


    def _create_udp_socket(state):
        """Establishes an un-bonded UDP datagram socket connection endpoint."""
        s = socket.socket(type=socket.SOCK_DGRAM)
        s.connect((state.host, state.port))
        return s


    def _get_exponential_delay(remaining, total, base_delay):
        """
        Dynamically tracks exponential backoff relative to any base delay input.
        """
        ratio = max(0.0, min(1.0, 1.0 - (remaining / total)))

        # Stays proportional: start_mult = 0.1, end_mult = 5.0
        multiplier = 0.1 * (50.0 ** ratio)

        return base_delay * multiplier


    def _item_completed(retry_queue, core_queue, item, reconnect=None):
        """
        Drains the processed item from the retry queue and issues a task acknowledgment
        to the synchronized queue if the item was not synthetically created.
        """
        # SUCCESS: Remove the successfully sent item from the chronological pipeline
        retry_queue.popleft()
        if not item.synthetic:
            core_queue.task_done()
        # Every sent item increases the budget by a single unit.
        # This makes it harder to shutdown because of budget exhaustion
        # when there was a working endpoint before the failure.
        if reconnect is not None:
            reconnect.budget = min(reconnect.cap, 1 + reconnect.budget)


    def _logging_handler_thread(state, shutdown=None, logger=logger):
        """
        Worker thread that drains messages and guarantees strict transport-level delivery
        by checking stateless item origins packed inside RetryItem containers.

        Independent worker thread routine responsible for draining log messages
        from the synchronized queue and streaming them to the remote hat-syslog endpoint.

        Uses an internal thread-local retry queue to maintain precise chronological
        ordering of log messages during transport connection failures.

        Args:
            state (_ThreadState): Thread-safe tracking state containing connection params.
            logger (logging.Logger): Diagnostic logger instance for transport anomalies.
        """
        ctx = None
        if common.CommType.TLS == state.comm_type:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.check_hostname = False
            ctx.verify_mode = ssl.VerifyMode.CERT_NONE

        # Chronological staging queue dedicated to maintaining strict FIFO order during outages
        retry_queue = collections.deque()
        retry_queue_size = 0

        # Reconnection budgetting
        reconnect = _ReconnectionState(
            timeout=state.reconnect_delay,
        )

        # Loop persists on shutdown until the retry queue is fully empty.
        while retry_queue or not state.closed.is_set():
            # the reconnect budget was exhausted, drain the retry queue
            if 0 > reconnect.budget and state.closed.is_set():
                retry_queue_size = len(retry_queue)
                while retry_queue:
                    item = retry_queue.popleft()
                    if not item.synthetic:
                        state.queue.task_done()
                continue

            # connect to the endpoint
            s = None
            try:
                factory = _SOCKET_FACTORIES[state.comm_type]
                s = factory(state, ctx)
            except KeyError:
                raise NotImplementedError(f'Unsupported comm_type: {state.comm_type}')
            except Exception:
                if s is not None:
                    with contextlib.suppress(Exception):
                        s.close()
                if 0 > reconnect.snapshot:
                    reconnect.snapshot = max(10, reconnect.budget)
                reconnect.budget -= reconnect.failure
                if 0 > reconnect.budget:
                    state.closed.set()
                else:
                    reconnect.timeout = _get_exponential_delay(
                        reconnect.budget,
                        reconnect.snapshot,
                        state.reconnect_delay,
                    )
                    # jitter
                    if 1 >= reconnect.timeout:
                        reconnect.timeout = max(1.0, 1.0 + reconnect.timeout)
                    reconnect.timeout = random.uniform(
                        math.floor(reconnect.timeout),
                        reconnect.timeout,
                    )
                    now_dt = datetime.now(tz=dt_timezone.utc)
                    next_retry_time = now_dt + timedelta(seconds=reconnect.timeout)
                    iso_timestamp = next_retry_time.isoformat(timespec='seconds')
                    if reconnect.timeout > state.reconnect_delay:
                        logger.warning(
                            'Persistent failures to connect to: '
                            f'{state.host}:{state.port}/{state.comm_type.name}\n'
                            '\tIs the endpoint service running??\n'
                            '\tRetries remaining: '
                            f'{1 + (reconnect.budget // reconnect.failure)}\n'
                            f'\tNext attempt at: {iso_timestamp}',
                        )
                    time.sleep(reconnect.timeout)
                continue
            else:
                reconnect.snapshot = -1
                reconnect.budget = min(
                    reconnect.cap,
                    reconnect.success + reconnect.budget,
                )

            # Connection successfully established; enter message transmission loop
            # while True optimizes throughput and relies on socket exceptions to break the loop context
            try:
                captured_drops = ()
                drop_payload = None
                item = None
                msg = None
                msg_bytes = None

                while True:
                    # Harvest and process dropped counts
                    # SAFELY EXTRACT AND PROCESS ALL TRACKED OVERFLOWS CHRONOLOGICALLY
                    try:
                        with state.cv:
                            if 1 < len(state.dropped) or 0 < state.dropped[0]:
                                # Freeze and copy the entire sequence array out of shared memory
                                captured_drops = tuple(state.dropped)
                                # Re-instantiate the tracked array to a clean initial state instantly
                                state.dropped.clear()
                                state.dropped.append(0)

                        # Convert captured thresholds into synthetic inline logs inside our local staging worker
                        for chunked_count in captured_drops:
                            if 0 < chunked_count:
                                drop_payload = _create_dropped_msg(
                                    chunked_count, '_logging_handler_thread', 0,
                                )
                                # Appending to the retry queue guarantees strict chronological reporting order
                                retry_queue.append(RetryItem(synthetic=True, msg=drop_payload))
                    finally:
                        captured_drops = ()
                        drop_payload = None

                    # Grab from the main queue if the local transport staging queue is empty
                    # If the retry queue is empty, block and wait for a fresh log message
                    if not retry_queue:
                        try:
                            msg = state.queue.get(timeout=state.reconnect_delay)
                        except queue.Empty:
                            if state.closed.is_set():
                                # The queue is empty and the handler has been explicitly closed.
                                # Break the transmission loop to allow the worker thread to exit cleanly.
                                break
                            continue
                        else:
                            retry_queue.append(RetryItem(synthetic=False, msg=msg))
                        finally:
                            msg = None

                    # Transmit head message and track task lifecycle states
                    try:
                        # Peek at the oldest message without popping it yet
                        item = retry_queue[0]
                        msg_bytes = encoder.msg_to_str(item.msg).encode()

                        if common.CommType.UDP == state.comm_type:
                            s.send(msg_bytes)
                        else:
                            s.send(f'{len(msg_bytes)} '.encode() + msg_bytes)
                    except (TypeError, ValueError):
                        # Message structure failure: Drop item immediately and preserve connection state
                        logger.exception('Dropping un-convertible poison-pill log message')
                        _item_completed(retry_queue, state.queue, item)
                    except UnicodeEncodeError:
                        # String binary processing failure: Drop item immediately and preserve connection state
                        logger.exception('Dropping un-encodable Unicode log message string')
                        _item_completed(retry_queue, state.queue, item)
                    except Exception:
                        # On socket break, tear down this loop context cleanly.
                        # The current message remains cleanly preserved at index 0 of retry_queue.
                        # Because task_done() is skipped, state.queue.join() will continue to block.
                        # Connection lost or infrastructure network failure: Break out loop to trigger socket reconnect
                        # Element stays safe at index 0 of the retry_queue cache.
                        # After reconnecting we will try it again.
                        break
                    else:
                        _item_completed(retry_queue, state.queue, item, reconnect)
                    finally:
                        # Clear references to optimize memory tracking
                        item = None
                        msg_bytes = None
            finally:
                # close the connection to avoid leaking it
                with contextlib.suppress(Exception):
                    s.close()

        # --- DRAIN QUEUE AND SHUTDOWN ---
        # The budget hit 0 (nothing is listening). We must drain everything cleanly
        # to prevent state.queue.join() block-freezing the rest of the application.
        # The retry queue was already cleanly drained inside the while loop.
        if 0 > reconnect.budget:
            state_queue_size = 0
            while True:
                try:
                    state.queue.get_nowait()
                    state.queue.task_done()
                    state_queue_size += 1
                except queue.Empty:
                    break
            logger.warning(
                f'Thread shutdown complete. Purged {retry_queue_size} local retry items '
                f'and {state_queue_size} queued items to prevent application blocks.'
            )
            # Use the callback function when it was provided.
            if shutdown is not None and callable(shutdown):
                shutdown()


    class SyslogHandler(hat_syslog_handler_SyslogHandler):
        """
        A process-safe wrapper for hat.syslog.handler.SyslogHandler.

        Bypasses immutable NamedTuple state constraints on fork boundaries,
        avoids thread-lock corruption from os.fork(), and short-circuits
        the time-blocking flush/close loops during a Huey graceful shutdown.

        A process-safe wrapper subclass for hat.syslog.handler.SyslogHandler.

        Bypasses immutable state limitations on fork boundaries, handles thread-lock
        corruption resulting from os.fork(), and avoids blocking task-execution loops
        during a graceful worker process shutdown.
        """
        def __init__(self, host, port, comm_type, queue_size=1024, reconnect_delay=5, logger=logger, *args, **kwargs):
            """Initializes the wrapper and neutralizes conflicting parent process states."""
            super().__init__(host, port, common.CommType.UDP, queue_size, reconnect_delay, *args, **kwargs)

            state = self._get_parent_attr('__state')

            if state:
                state.closed.set()
                thread = self._get_parent_attr('__thread')
                if thread and thread.is_alive():
                    with state.cv, contextlib.suppress(Exception):
                        state.cv.notify_all()

            # Initialize native, thread-safe sync tracking structures
            self.__state = _ThreadState(
                host=host,
                port=port,
                comm_type=self._determine_comm_type(comm_type),
                queue=queue.Queue(maxsize=queue_size),
                queue_size=queue_size,
                reconnect_delay=reconnect_delay,
                cv=threading.Condition(),
                closed=threading.Event(),
                dropped=list((0,)),
            )

            self.__thread = None
            self._initial_pid = os.getpid()
            self._closing = threading.Event()
            self._logger = logger

            # Save the original arguments
            self.host = host
            self.port = port
            self.comm_type = comm_type
            self.queue_size = queue_size
            self.reconnect_delay = reconnect_delay

        def _alive_thread(self):
            """Thread-safe validator confirming background worker availability."""
            if not (self.__thread and self.__thread.is_alive()):
                return False

            with self.__state.cv:
                if self.__thread and self.__thread.is_alive():
                    if hasattr(self.__thread, '_scoreboard') and self.__thread._scoreboard:
                        self.__thread._scoreboard.alive = (time.time(), time.monotonic_ns())
                    return True
            return False

        def _after_fork(self, current_pid=None):
            """
            Intercepts the Unix process boundary skew. If a fork is identified,
            it cleans old references and initializes fresh process-isolated primitives.
            """

            # Detect if we crossed the Unix fork boundary into Huey's process worker.
            if current_pid is None:
                current_pid = os.getpid()

            if current_pid == self._initial_pid:
                # Return early when we have not forked.
                return

            self._initial_pid = current_pid

            state = self.__state
            new_state = _ThreadState(
                host=state.host,
                port=state.port,
                comm_type=state.comm_type,
                queue=queue.Queue(maxsize=state.queue_size),
                queue_size=state.queue_size,
                reconnect_delay=state.reconnect_delay,
                cv=threading.Condition(),
                closed=threading.Event(),
                dropped=list((0,)),
            )
            self.__state = new_state
            self.__thread = None

        def _create_thread(self):
            """Aligns process states and builds a clean worker thread context."""

            self._after_fork()

            if self._closing.is_set() or self.__state.closed.is_set() or self._alive_thread():
                return

            initial = self.__thread is None
            with self.__state.cv:
                previous = self.__thread
                cb_closing = self._closing
                cb_closed = self.__state.closed
                cb_handler_close = super(hat_syslog_handler_SyslogHandler, self).close
                def shutdown_cb():
                    cb_closing.set()
                    cb_closed.set()
                    cb_handler_close()

                self.__thread = threading.Thread(
                    target=_logging_handler_thread,
                    kwargs=dict(
                        state=self.__state,
                        logger=self._logger,
                        shutdown=shutdown_cb,
                    ),
                    daemon=True,
                )

                scoreboard = ThreadScoreboard()
                self.__thread._scoreboard = scoreboard

                if initial:
                    scoreboard.alive = scoreboard.start
                    scoreboard.initialized = scoreboard.start
                elif previous and hasattr(previous, '_scoreboard') and previous._scoreboard:
                    scoreboard.alive = previous._scoreboard.alive
                    scoreboard.initialized = previous._scoreboard.initialized
                    scoreboard.previous_start = previous._scoreboard.start
                    self._logger.debug(f'Created a replacement thread: {scoreboard=}')

                self.__thread.start()

        def _determine_comm_type(self, comm_type):
            """Maps and cross-checks string connection descriptions to Enumeration definitions."""
            if isinstance(comm_type, str):
                needle = comm_type
                haystack = frozenset(common.CommType.__members__)
                vary = lambda x: {
                    x, x.upper(),
                    x.casefold(), x.casefold().upper(),
                    x.lower(), x.lower().upper(),
                }
                try:
                    matched_elements = tuple(haystack.intersection(vary(needle)))
                    member = matched_elements[0]
                    return common.CommType[member]
                except (IndexError, KeyError) as e:
                    raise ValueError(f'Specify a valid comm_type from this list: {list(haystack)}') from e

            if not isinstance(comm_type, common.CommType):
                raise ValueError('Invalid comm_type argument')

        def _parent_class_name(self):
            return hat_syslog_handler_SyslogHandler.__name__

        def _mangled_name(self, attr_name):
            return f'_{self._parent_class_name()}{attr_name}'

        def _get_parent_attr(self, attr_name):
            """Computes and gets mangled attributes from the super class."""
            return getattr(self, self._mangled_name(attr_name), None)

        def _set_parent_attr(self, attr_name, value):
            """Computes and sets mangled attributes on the super class."""
            setattr(self, self._mangled_name(attr_name), value)

        def emit(self, record):
            """Enqueues new log records and guarantees active connection coverage."""
            if self._closing.is_set():
                with contextlib.suppress(Exception):
                    self._logger.handle(record)
                return

            self._create_thread()

            if not self._alive_thread():
                with contextlib.suppress(Exception):
                    self._logger.handle(record)
                return

            state = self.__state
            if state.closed.is_set():
                self._closing.set()
                self._logger.warning('Closed in emit')
                with contextlib.suppress(Exception):
                    self._logger.handle(record)
                return

            msg = _record_to_msg(record)

            try:
                state.queue.put_nowait(msg)
            except queue.Full:
                # ACQUIRE LOCK ON MAIN THREAD BEFORE INCREMENTING COUNTER SLICES
                with state.cv:
                    dropped_count = state.dropped[-1]
                    if 1_000_000 < dropped_count:
                        state.dropped.append(1)
                    else:
                        state.dropped[-1] = 1 + dropped_count

                self._logger.warning(f'Dropped a log message in emit due to buffer overflow: {msg.msg!r}')
                with contextlib.suppress(Exception):
                    self._logger.handle(record)

        def flush(self):
            """Blocks execution until the internal logging queue is empty."""
            self._create_thread()

            if not self._alive_thread():
                return

            state = self.__state
            with contextlib.suppress(Exception):
                state.queue.join()

        def close(self):
            """
            Gracefully flushes the queue and terminates the background logging thread.
            Cleans up the queue, flags the state as closed, and shuts down
            the background thread without allowing new ones to be generated.
            """

            # Align/verify the background worker thread state immediately
            self._closing.clear()
            self._create_thread()
            state = self.__state
            if state.closed.is_set():
                # Only return early when the thread is alive
                state.closed.clear()
                self._create_thread()
            self._closing.set()

            # The native queue.join() blockade is now perfectly synchronized with the internal
            # tracking flow loop. It will block until retry_queue is 100% empty.
            if self._alive_thread():
                self._logger.debug('Flushing logging queue in close')
                with contextlib.suppress(Exception):
                    state.queue.join()

            # Immediately trip the closed flag to end the networking thread
            self.__state.closed.set()

            # =====================================================================
            # DYNAMIC GRANDPARENT BYPASS VIA MRO
            # Instructs Python to search for close() starting *after* our direct
            # parent class type descriptor. This dynamically resolves grandfather
            # dependencies while completely avoiding the parent class thread-joins.
            # =====================================================================
            super(hat_syslog_handler_SyslogHandler, self).close()


    handler = SyslogHandler
    default_handler = handler(
        comm_type='UDP',
        host='127.0.0.1',
        port=6514,
    )
