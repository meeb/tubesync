from __future__ import annotations

import atexit
import contextlib
import functools
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
import threading
import time

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

from django import db

from common.logger import log
from common.utils import remove_enclosed
from sync.utils import filter_response


FLUSH_INTERVAL = 1.0
IDLE_ROTATION_INTERVAL = 600.0
SUPERVISOR_INTERVAL = 0.2
MAX_FLUSH_RETRIES = 5
BATCH_SIZE = 100


@dataclass
class QueueState:
    generation_id: str
    dir: Path
    path: Path
    conn: sqlite3.Connection | None = None
    process: subprocess.Popen | None = None
    lifecycle: str = 'active'
    created_at: float = field(default_factory=time.monotonic)
    last_activity: float = field(default_factory=time.monotonic)
    last_flush_at: float = field(default_factory=time.monotonic)
    flush_retries: int = 0
    buffer: list[dict[str, Any]] = field(default_factory=list)
    resolutions: dict[str, str] = field(default_factory=dict)
    lock: threading.RLock = field(default_factory=threading.RLock)


_state: QueueState | None = None
_retired: list[QueueState] = []
_root_dir: Path | None = None
_coordination_path: Path | None = None
_supervisor_thread: threading.Thread | None = None
_shutdown = False

# Lock order: _lifecycle_lock, then QueueState.lock.
_lifecycle_lock = threading.RLock()
_token_lock = threading.Lock()
_sequence_lock = threading.Lock()

_sequences: dict[str, int] = {}
_token_counter = 0
_active_download_token: str | None = None
_active_media_key: str | None = None

progress_hook = dict(status=dict())
postprocessor_hook = dict(status=dict())


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(
        path,
        isolation_level=None,
        timeout=30,
        check_same_thread=False,
    )
    conn.execute('PRAGMA busy_timeout = 30000')
    return conn


def _init_coordination_db(path: Path) -> None:
    with contextlib.closing(_connect(path)) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS download_map (
                download_token TEXT PRIMARY KEY,
                media_key TEXT NOT NULL,
                media_uuid TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS download_state (
                download_token TEXT PRIMARY KEY,
                last_sequence INTEGER NOT NULL
            )
        """)


def _init_generation_db(state: QueueState) -> None:
    state.dir.mkdir(parents=True, exist_ok=True)
    with contextlib.closing(_connect(state.path)) as conn:
        conn.execute('PRAGMA journal_mode = WAL')
        conn.execute('PRAGMA synchronous = NORMAL')
        conn.execute("""
            CREATE TABLE IF NOT EXISTS queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                payload TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS download_map (
                download_token TEXT PRIMARY KEY,
                media_key TEXT NOT NULL,
                media_uuid TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES ('lifecycle', 'active')"
        )
        conn.execute('PRAGMA user_version = 2')


def _ensure_root_locked() -> None:
    global _root_dir, _coordination_path

    if _root_dir is not None and _root_dir.exists():
        return

    _root_dir = Path(tempfile.mkdtemp(prefix='sync_hooks_'))
    _coordination_path = _root_dir / 'coordination.db'
    _init_coordination_db(_coordination_path)


def _start_consumer(state: QueueState) -> None:
    if _coordination_path is None:
        raise RuntimeError('Queue coordination database is not initialized')

    command = [
        '/app/manage.py',
        'sync_yt_dlp_hooks_consumer',
        '--temp-dir', str(state.dir),
        '--generation', state.generation_id,
        '--coordination-db', str(_coordination_path),
        '--pid', str(os.getpid()),
    ]
    state.process = subprocess.Popen(command)

    # Catch immediate startup failures before publishing this state.
    time.sleep(0.05)
    if state.process.poll() is not None:
        raise RuntimeError(
            'Queue consumer exited during startup for generation '
            f'{state.generation_id}'
        )


def _new_generation_locked() -> QueueState:
    _ensure_root_locked()
    assert _root_dir is not None

    generation_id = f'{time.monotonic_ns():x}'
    generation_dir = _root_dir / generation_id
    state = QueueState(
        generation_id=generation_id,
        dir=generation_dir,
        path=generation_dir / 'queue.db',
    )

    try:
        _init_generation_db(state)
        _start_consumer(state)
    except Exception:
        if state.process is not None and state.process.poll() is None:
            state.process.terminate()
            with contextlib.suppress(Exception):
                state.process.wait(timeout=5)
        shutil.rmtree(generation_dir, ignore_errors=True)
        raise

    return state


def _read_coordination_uuid(download_token: str) -> str | None:
    if _coordination_path is None or not _coordination_path.exists():
        return None
    try:
        with contextlib.closing(_connect(_coordination_path)) as conn:
            row = conn.execute(
                'SELECT media_uuid FROM download_map WHERE download_token = ?',
                (download_token,),
            ).fetchone()
        return row[0] if row else None
    except sqlite3.Error:
        log.warning('Could not read a cached media UUID for a queue event')
        return None


def _ensure_active_locked() -> QueueState:
    global _state

    if _state is None:
        _state = _new_generation_locked()
    elif 'active' != _state.lifecycle:
        _rotate_locked('active state was not active')
        assert _state is not None

    _ensure_supervisor_locked()
    return _state


def init_queue_db() -> None:
    """Idempotently initialize the queue and its single process-wide supervisor."""
    with _lifecycle_lock:
        _ensure_active_locked()


def launch_worker(monitor_parent: bool = True) -> None:
    """Compatibility wrapper; the worker is started once per generation."""
    del monitor_parent
    init_queue_db()


def _flush_buffer(state: QueueState) -> None:
    if not state.buffer:
        return

    if state.conn is None:
        state.conn = _connect(state.path)

    conn = state.conn
    began = False
    try:
        conn.execute('BEGIN IMMEDIATE')
        began = True

        rows = [
            (json.dumps(payload, separators=(',', ':'), ensure_ascii=False),)
            for payload in state.buffer
        ]
        conn.executemany('INSERT INTO queue(payload) VALUES (?)', rows)

        for payload in state.buffer:
            token = payload['download_token']
            key = str(payload['media_key'])
            media_uuid = payload.get('media_uuid')
            conn.execute(
                """
                INSERT INTO download_map(download_token, media_key, media_uuid)
                VALUES (?, ?, ?)
                ON CONFLICT(download_token) DO UPDATE SET
                    media_key = excluded.media_key,
                    media_uuid = COALESCE(
                        excluded.media_uuid,
                        download_map.media_uuid
                    )
                """,
                (token, key, media_uuid),
            )

        conn.execute('COMMIT')
        began = False
        state.buffer.clear()
        state.last_flush_at = time.monotonic()
        state.flush_retries = 0

    except sqlite3.Error:
        if began:
            with contextlib.suppress(sqlite3.Error):
                conn.execute('ROLLBACK')
        state.flush_retries += 1
        log.warning(
            'SQLite queue flush failed for generation %s (retry %d)',
            state.generation_id,
            state.flush_retries,
        )
        if state.flush_retries >= MAX_FLUSH_RETRIES:
            with contextlib.suppress(sqlite3.Error):
                conn.close()
            state.conn = None
        raise


def _copy_known_mappings(old: QueueState, new: QueueState) -> None:
    if not old.path.exists():
        return

    with contextlib.closing(_connect(old.path)) as old_conn:
        rows = old_conn.execute(
            'SELECT download_token, media_key, media_uuid FROM download_map'
        ).fetchall()

    if not rows:
        return

    with contextlib.closing(_connect(new.path)) as new_conn:
        new_conn.executemany(
            """
            INSERT OR REPLACE INTO download_map(
                download_token, media_key, media_uuid
            ) VALUES (?, ?, ?)
            """,
            rows,
        )

    for token, _, media_uuid in rows:
        if media_uuid:
            new.resolutions[token] = media_uuid


def _set_generation_lifecycle(state: QueueState, lifecycle: str) -> None:
    if not state.path.exists():
        return
    with contextlib.closing(_connect(state.path)) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES ('lifecycle', ?)",
            (lifecycle,),
        )


def _rotate_locked(reason: str, *, failed: bool = False) -> None:
    """Caller holds _lifecycle_lock."""
    global _state

    old = _state
    new = _new_generation_locked()

    if old is None:
        _state = new
        return

    try:
        with old.lock:
            _copy_known_mappings(old, new)
            new.buffer.extend(old.buffer)

            # Publish the new generation before flushing the transferred buffer.
            _state = new
            old.lifecycle = 'failed' if failed else 'retiring'

            if not failed:
                with contextlib.suppress(Exception):
                    _set_generation_lifecycle(old, 'retired')

            old.buffer.clear()

            if old.conn is not None:
                with contextlib.suppress(sqlite3.Error):
                    old.conn.close()
                old.conn = None

            _retired.append(old)

        log.info(
            'Rotated hook queue generation %s to %s (%s)',
            old.generation_id,
            new.generation_id,
            reason,
        )

        # A failed generation's persisted rows are intentionally not replayed.
        with new.lock:
            _flush_buffer(new)

    except Exception:
        # If setup failed before publishing, keep the previous generation active.
        if _state is not new:
            if new.process is not None and new.process.poll() is None:
                new.process.terminate()
            shutil.rmtree(new.dir, ignore_errors=True)
        raise


def _cleanup_retired_locked() -> None:
    keep: list[QueueState] = []

    for state in _retired:
        process = state.process
        if process is not None and process.poll() is None:
            keep.append(state)
            continue

        with state.lock:
            if state.conn is not None:
                with contextlib.suppress(sqlite3.Error):
                    state.conn.close()
                state.conn = None

        shutil.rmtree(state.dir, ignore_errors=True)

    _retired[:] = keep


def _supervisor() -> None:
    while not _shutdown:
        time.sleep(SUPERVISOR_INTERVAL)

        try:
            with _lifecycle_lock:
                state = _state
                if state is None:
                    continue

                now = time.monotonic()
                process_dead = (
                    state.process is None or state.process.poll() is not None
                )
                path_missing = not state.dir.exists() or not state.path.exists()

                if process_dead or path_missing:
                    _rotate_locked(
                        'consumer exited or active database path disappeared',
                        failed=True,
                    )
                elif (
                    IDLE_ROTATION_INTERVAL > 0
                    and now - state.last_activity >= IDLE_ROTATION_INTERVAL
                ):
                    _rotate_locked('idle rotation')
                else:
                    with state.lock:
                        if (
                            state.buffer
                            and now - state.last_flush_at >= FLUSH_INTERVAL
                        ):
                            try:
                                _flush_buffer(state)
                            except sqlite3.Error:
                                if state.flush_retries >= MAX_FLUSH_RETRIES:
                                    _rotate_locked(
                                        'repeated queue flush failures',
                                        failed=True,
                                    )
                        elif (
                            state.conn is not None
                            and now - state.last_activity >= 600
                        ):
                            with contextlib.suppress(sqlite3.Error):
                                state.conn.close()
                            state.conn = None

                _cleanup_retired_locked()

        except Exception:
            log.exception('Hook queue supervisor iteration failed')


def _ensure_supervisor_locked() -> None:
    global _supervisor_thread

    if _supervisor_thread is not None and _supervisor_thread.is_alive():
        return

    _supervisor_thread = threading.Thread(
        target=_supervisor,
        name='sync-hook-queue-supervisor',
        daemon=True,
    )
    _supervisor_thread.start()


def _next_sequence(download_token: str) -> int:
    with _sequence_lock:
        sequence = 1 + _sequences.get(download_token, 0)
        _sequences[download_token] = sequence
        return sequence


def _enqueue(
    download_token: str,
    media_key: str,
    media_uuid: str | None,
    task_status: str,
    task_verbose_name: str | None,
) -> None:
    payload = {
        'download_token': download_token,
        'media_key': str(media_key),
        'media_uuid': media_uuid,
        'sequence': _next_sequence(download_token),
        'task_status': task_status,
        'task_verbose_name': task_verbose_name,
    }

    with _lifecycle_lock:
        state = _ensure_active_locked()
        with state.lock:
            now = time.monotonic()
            state.last_activity = now
            if media_uuid:
                state.resolutions[download_token] = media_uuid
            else:
                cached_uuid = (
                    state.resolutions.get(download_token)
                    or _read_coordination_uuid(download_token)
                )
                if cached_uuid:
                    payload['media_uuid'] = cached_uuid
                    state.resolutions[download_token] = cached_uuid

            state.buffer.append(payload)

            if len(state.buffer) >= BATCH_SIZE:
                try:
                    _flush_buffer(state)
                except sqlite3.Error:
                    # The supervisor retries; retain the uncommitted payloads.
                    pass


def _new_download_token(media_key: str) -> str:
    global _token_counter

    with _token_lock:
        _token_counter += 1
        return (
            f'{os.getpid()}:{media_key}:'
            f'{time.monotonic_ns()}:{_token_counter}'
        )


def _token_for_event(media_key: str, *, new_download: bool = False) -> str:
    global _active_download_token, _active_media_key

    with _token_lock:
        if (
            new_download
            or _active_download_token is None
            or _active_media_key != media_key
        ):
            _active_download_token = _new_download_token(media_key)
            _active_media_key = media_key
        return _active_download_token


def _finish_active_token(download_token: str) -> None:
    global _active_download_token, _active_media_key

    with _token_lock:
        if _active_download_token == download_token:
            _active_download_token = None
            _active_media_key = None


class BaseStatus:
    status_dict: ClassVar[dict[str, 'BaseStatus']] = {}
    valid = frozenset()

    @staticmethod
    def event_key(event: dict) -> str | None:
        info_dict = event.get('info_dict')
        if not isinstance(info_dict, dict):
            return None

        key = info_dict.get('display_id')
        if key is None:
            key = info_dict.get('id')
        return None if key is None else str(key)

    @classmethod
    def get(cls, key: str) -> 'BaseStatus | None':
        return cls.status_dict.get(key)

    @classmethod
    def valid_status(cls, event: dict) -> bool:
        return (
            isinstance(event, dict)
            and event.get('status') in cls.valid
        )

    def __init__(
        self,
        *,
        media_key: str,
        download_token: str,
        info_dict: dict | None = None,
        filename: str | None = None,
    ):
        info_dict = info_dict or {}
        self.media_key = media_key
        self.download_token = download_token
        self.media_uuid = info_dict.get('media_uuid')
        self.task_status = '[Started: 0%]'
        self.task_verbose_name = None
        self.info = info_dict
        self.filename = filename or info_dict.get('filename')
        self._status_dict = type(self).status_dict
        self._registered_keys: set[str] = set()

    def register(self, *keys: str | None) -> None:
        for key in keys:
            if key is not None:
                self._registered_keys.add(key)
                self._status_dict[key] = self

    def cleanup(self) -> None:
        for key in self._registered_keys:
            if self._status_dict.get(key) is self:
                self._status_dict.pop(key, None)

    def update_task(self) -> None:
        if not self.media_key:
            return
        _enqueue(
            self.download_token,
            self.media_key,
            self.media_uuid,
            self.task_status,
            self.task_verbose_name,
        )


class ProgressHookStatus(BaseStatus):
    status_dict = progress_hook['status']
    valid = frozenset({'downloading', 'finished', 'error'})

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.download_progress = 0
        self._percentage_lock = threading.Lock()

    def next_progress(self) -> int:
        return 0 if 0 == self.download_progress else 1 + self.download_progress


class PPHookStatus(BaseStatus):
    status_dict = postprocessor_hook['status']
    valid = frozenset({'started', 'processing', 'finished'})

    def __init__(self, *, postprocessor: str | None = None, **kwargs):
        super().__init__(**kwargs)
        self.name = postprocessor
        self.media_name = None


def close_db_after(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        finally:
            db.close_old_connections()
    return wrapper


@close_db_after
def yt_dlp_progress_hook(event):
    if not ProgressHookStatus.valid_status(event):
        log.warning('[youtube-dl] unknown progress event')
        return

    media_key = ProgressHookStatus.event_key(event)
    if media_key is None:
        log.warning('[youtube-dl] progress event has no media key')
        return

    status = ProgressHookStatus.get(media_key)
    if status is None:
        token = _token_for_event(media_key, new_download=True)
        info_dict = event.get('info_dict') or {}
        status = ProgressHookStatus(
            media_key=media_key,
            download_token=token,
            info_dict=info_dict,
            filename=event.get('filename'),
        )
        status.register(media_key)

    event_status = event['status']

    if 'error' == event_status:
        log.error('[youtube-dl] download reported an error')
        status.task_status = '[Download error]'
        status.update_task()
        status.cleanup()
        return

    if 'downloading' == event_status:
        downloaded_bytes = event.get('downloaded_bytes') or 0
        total_bytes = (
            event.get('total_bytes')
            or event.get('total_bytes_estimate')
            or 0
        )
        fragment_index = event.get('fragment_index') or 0
        fragment_count = event.get('fragment_count') or 0
        percent_str = (event.get('_percent_str') or '?').strip()
        speed = (event.get('_speed_str') or '?').strip()
        eta = (event.get('_eta_str') or '?').strip()

        percent = None
        with contextlib.suppress(TypeError, ValueError):
            percent = int(float(percent_str.rstrip('%')))

        if 0 < fragment_count:
            percent = round(100 * fragment_index / fragment_count)
        elif 0 < total_bytes:
            percent = round(100 * downloaded_bytes / total_bytes)

        if percent is None:
            return

        with status._percentage_lock:
            accept = (
                status.next_progress() < percent
                and 0 < percent
                and 0 == percent % 5
            )
            if accept:
                status.download_progress = percent

        if accept:
            status.task_status = f'[Downloading: {percent_str}]'
            status.update_task()
            log.info(
                '[youtube-dl] downloading: %s - %s at %s, %s remaining',
                status.filename or 'unknown file',
                percent_str,
                speed,
                eta,
            )

    elif 'finished' == event_status:
        status.download_progress = 100
        status.task_status = '[Downloaded: 100%]'
        status.update_task()
        log.info(
            '[youtube-dl] finished downloading: %s',
            status.filename or 'unknown file',
        )
        # Keep the active token for postprocessor events.
        status.cleanup()


@close_db_after
def yt_dlp_postprocessor_hook(event):
    if not PPHookStatus.valid_status(event):
        log.warning('[youtube-dl] unknown postprocessor event')
        return

    media_key = PPHookStatus.event_key(event)
    if media_key is None:
        log.warning('[youtube-dl] postprocessor event has no media key')
        return

    postprocessor = event.get('postprocessor') or 'Unknown'
    status = PPHookStatus.get(media_key)

    if status is None:
        token = _token_for_event(media_key)
        info_dict = event.get('info_dict') or {}
        status = PPHookStatus(
            media_key=media_key,
            download_token=token,
            info_dict=info_dict,
            filename=event.get('filename'),
            postprocessor=postprocessor,
        )
        status.register(media_key)

    status.task_status = f"[{postprocessor}: {event['status']}]"
    status.update_task()

    info_dict = event.get('info_dict') or {}
    title = info_dict.get('fulltitle') or info_dict.get('title')
    if title:
        log.info(
            '[%s] %s for: %s',
            postprocessor,
            event['status'],
            title,
        )
    else:
        log.info('[%s] %s', postprocessor, event['status'])

    if 'started' == event['status']:
        logged_dict = filter_response(info_dict, True)
        for key in ('formats', 'automatic_captions'):
            logged_dict.pop(key, None)
        log.debug('%r', logged_dict)

        if 'Merger' == postprocessor:
            try:
                from .models import Media

                db.close_old_connections()
                media = Media.objects.get(uuid=status.media_uuid)
                value = dict(media.new_metadata.value)
                value['requested_formats'] = info_dict.get('requested_formats')
                media.new_metadata.value = value
                media.new_metadata.save()
            except Media.DoesNotExist:
                pass
            except Exception:
                log.exception(
                    'Failed to update metadata for a hook event'
                )
            finally:
                db.close_old_connections()

    if 'finished' == event['status']:
        token = status.download_token
        status.cleanup()
        _finish_active_token(token)


def _shutdown_queue() -> None:
    global _shutdown

    _shutdown = True
    with _lifecycle_lock:
        state = _state
        if state is None:
            return

        with state.lock:
            try:
                _flush_buffer(state)
            except Exception:
                log.exception('Final hook queue flush failed')
            with contextlib.suppress(Exception):
                _set_generation_lifecycle(state, 'retired')

    thread = _supervisor_thread
    if thread is not None and thread.is_alive():
        thread.join(timeout=2)


atexit.register(_shutdown_queue)


progress_hook.update({
    'class': ProgressHookStatus,
    'function': yt_dlp_progress_hook,
})

postprocessor_hook.update({
    'class': PPHookStatus,
    'function': yt_dlp_postprocessor_hook,
})

