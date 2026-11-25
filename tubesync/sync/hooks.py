from __future__ import annotations

import contextlib
import functools
import json
import os
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
from sync.utils import filter_response


@dataclass
class QueueState:
    dir: str
    path: Path
    conn: sqlite3.Connection | None = None
    created_at: float = 0.0
    last_used_at: float = 0.0
    last_flush_at: float = 0.0
    buffer: list[dict[str, Any]] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)


# Global state instance
_state: QueueState | None = None

progress_hook = {
    'status': dict(),
}

postprocessor_hook = {
    'status': dict(),
}


def init_queue_db():
    global _state
    q_dir = tempfile.mkdtemp(prefix='sync_hooks_')
    q_path = Path(q_dir) / 'queue.db'
    
    with sqlite3.connect(q_path) as conn:
        conn.execute('PRAGMA auto_vacuum = INCREMENTAL;')
        conn.execute('PRAGMA journal_mode = WAL;')
        conn.execute('PRAGMA journal_size_limit = 0;')
        conn.execute('VACUUM;')

    with sqlite3.connect(q_path) as conn:
        conn.execute('PRAGMA synchronous = 3;')
        conn.execute("""
            CREATE TABLE IF NOT EXISTS queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                payload TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS media (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT NOT NULL CHECK (0 < length(trim(key))),
                uuid TEXT CHECK (uuid IS NULL OR 0 < length(trim(uuid)))
            )
        """)
        conn.execute('PRAGMA user_version = 1;')
    
    _state = QueueState(dir=q_dir, path=q_path)
    
    threading.Thread(target=_connection_reaper, daemon=True).start()

def _connection_reaper():
    """Background thread that closes connections idle for more than 10 minutes."""
    if _state is not None:
        while _state.conn is None:
            time.sleep(1)
    while _state is not None:
        time.sleep(60)
        if _state.conn is None:
            continue
        with _state.lock:
            if _state.conn is not None and (600 < (time.monotonic() - _state.last_used_at)):
                _state.conn.close()
                _state.conn = None

def _flush_buffer(state: QueueState):
    """Writes the current buffer to SQLite using an IMMEDIATE transaction."""
    if not state.buffer or state.conn is None:
        return

    in_transaction = False
    try:
        # BEGIN IMMEDIATE prevents other connections from starting a write 
        # transaction, avoiding SQLITE_BUSY during high contention.
        state.conn.execute('BEGIN IMMEDIATE;')
        in_transaction = True
        
        payloads = [(json.dumps(p),) for p in state.buffer]
        state.conn.executemany('INSERT INTO queue (payload) VALUES (?)', payloads)
        
        state.conn.execute('COMMIT;')
        in_transaction = False
        state.buffer.clear()
        state.last_flush_at = time.monotonic()
    except sqlite3.Error:
        if in_transaction:
            with contextlib.suppress(sqlite3.Error):
                state.conn.execute('ROLLBACK;')
                in_transaction = False
        raise
    finally:
        if in_transaction is not False and state.conn is not None:
            with contextlib.suppress(sqlite3.Error):
                state.conn.close()
            state.conn = None
        in_transaction = False


class BaseStatus:
    status_dict: ClassVar[dict[str, BaseStatus]] = dict()
    valid = frozenset()

    @staticmethod
    def event_key(event: dict) -> str | None:
        expected_structure = (
            isinstance(event, dict) and
            'info_dict' in event and
            isinstance(event['info_dict'], dict)
        )  # fmt: skip
        key = None
        if expected_structure:
            key = event['info_dict'].get('display_id', key)
            if key is None:
                key = event['info_dict'].get('id', key)
        return key

    @classmethod
    def get(cls, key: str) -> BaseStatus | None:
        return cls.status_dict.get(key, None)

    @classmethod
    def valid_status(cls, event: dict) -> bool:
        if not isinstance(event, dict):
            return False
        status: str | None = event.get('status', None)
        return status is not None and status in cls.valid

    def __init__(self, /, hook_status_dict: dict | None = None, *, filename: str | None = None, info_dict: dict | None = None, status: str | None = None):
        self._registered_keys = set()
        if hook_status_dict is None:
            self._status_dict = self.status_dict
        else:
            self._status_dict = hook_status_dict
        if info_dict is None:
            info_dict = dict()
        fn = info_dict.get('filename', None)
        resolved_fn = fn if filename is None else filename
        self.filename = resolved_fn
        self.info = info_dict
        self.filepath = None if resolved_fn is None else Path(resolved_fn)
        self.media_key = None
        self.media_uuid = None
        self.task_status = '[Started: 0%]'
        self.task_verbose_name = None

    def register(self, *args):
        additions = {key: self for key in args if key is not None}
        self._registered_keys.update(additions)
        self._status_dict.update(additions)
        if _state is None:
            self.launch_worker()

    def cleanup(self):
        # Discarded alternative: rebuild the dictionary
        # self._status_dict = {
        #     k: v
        #     for k, v in self._status_dict.items()
        #     if k not in self._registered_keys
        # }
        for key in self._registered_keys:
            self._status_dict.pop(key, None)

    def update_task(self):
        if _state is None or (self.media_key is None and self.media_uuid is None):
            return
            
        with _state.lock:
            now = time.monotonic()
            
            # 1. Connection Lifecycle (Max Age 10m)
            if _state.conn is not None and (600 < (now - _state.created_at)):
                _state.conn.close()
                _state.conn = None

            # 2. Lazy Init (isolation_level=None for manual transaction control)
            if _state.conn is None:
                _state.conn = sqlite3.connect(_state.path, isolation_level=None)
                _state.conn.execute('PRAGMA synchronous = 1;')
                _state.created_at = now
                with _state.conn.cursor() as cursor:
                    cursor.execute('PRAGMA user_version;')
                    row = cursor.fetchone()
                    if row and 0 < row[0]:
                        cursor.execute('PRAGMA wal_checkpoint(PASSIVE);')
                        cursor.execute('PRAGMA incremental_vacuum(1000);')
                        cursor.execute('PRAGMA wal_checkpoint(TRUNCATE);')
            
            _state.last_used_at = now
            if self.media_uuid is None and hasattr(self, 'media_rowid'):
                with _state.conn.cursor() as cursor:
                    cursor.execute('SELECT uuid FROM media WHERE id = ?', (self.media_rowid,))
                    row = cursor.fetchone()
                    if row and row[0] is not None:
                        self.media_uuid = row[0]
            elif self.media_uuid is None:
                with _state.conn.cursor() as cursor:
                    cursor.execute('INSERT INTO media (key) VALUES (?)', (self.media_key,))
                    self.media_rowid = cursor.lastrowid

            # 3. Buffer the payload
            _state.buffer.append({
                'media_key': self.media_key,
                'media_rowid': getattr(self, 'media_rowid', 0),
                'media_uuid': self.media_uuid,
                'task_status': self.task_status,
                'task_verbose_name': self.task_verbose_name,
            })
            
            # 4. Throttled Flush: Trigger if buffer >= 100 items or 1 second has passed
            if (100 <= len(_state.buffer)) or (1.0 < (now - _state.last_flush_at)):
                _flush_buffer(_state)

    def launch_worker(self, monitor_parent: bool = True):
        """Launches the worker. monitor_parent=True passes os.getpid()."""
        global _state

        if _state is not None and not _state.path.exists():
            _state = None
        if _state is None:
            init_queue_db()

        cmd = ['/app/manage.py', 'sync_yt_dlp_hooks_consumer', '--temp-dir', _state.dir]
        if monitor_parent:
            cmd.extend(['--pid', str(os.getpid())])
        
        subprocess.Popen(cmd)

class ProgressHookStatus(BaseStatus):
    status_dict = progress_hook['status']
    valid = frozenset((
        'downloading',
        'finished',
        'error',
    ))

    def __init__(self, *args, filename=None, info_dict=None, status=None, **kwargs):
        super().__init__(self.status_dict, filename=filename, info_dict=info_dict, status=status)
        self.download_progress = 0
        self._percentage_lock = threading.Lock()

    @property
    def lock(self):
        return self._percentage_lock

    def next_progress(self):
        if 0 == self.download_progress:
            return 0
        return 1 + self.download_progress


class PPHookStatus(BaseStatus):
    status_dict = postprocessor_hook['status']
    valid = frozenset((
        'started',
        'processing',
        'finished',
    ))

    def __init__(self, *args, postprocessor=None, filename=None, info_dict=None, status=None, **kwargs):
        super().__init__(self.status_dict, filename=filename, info_dict=info_dict, status=status)
        self.media_name = None
        self.name = postprocessor


def close_db_after(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        with contextlib.closing(db.connection):
            return fn(*args, **kwargs)
    return wrapper


@close_db_after
def yt_dlp_progress_hook(event):
    if not ProgressHookStatus.valid_status(event):
        log.warning(f'[youtube-dl] unknown progress event: {event!r}')
        return

    key = ProgressHookStatus.event_key(event)
    filepath = Path(event.get('filename', '???'))
    filename = filepath.name
    if 'error' == event['status']:
        log.error(f'[youtube-dl] error occured downloading: {filename}')
    elif 'downloading' == event['status']:
        # get or create the status for filepath
        status = ProgressHookStatus.get(str(filepath))
        if status is None:
            status = ProgressHookStatus(**event)
            status.register(key, filename, str(filepath))

        downloaded_bytes = event.get('downloaded_bytes') or 0
        total_bytes_estimate = event.get('total_bytes_estimate') or 0
        total_bytes = event.get('total_bytes') or total_bytes_estimate
        fragment_index = event.get('fragment_index') or 0
        fragment_count = event.get('fragment_count') or 0
        eta = event.get('_eta_str', '?').strip()
        percent_str = event.get('_percent_str', '?').strip()
        speed = event.get('_speed_str', '?').strip()
        total = event.get('_total_bytes_str', '?').strip()
        percent = None
        with contextlib.suppress(Exception):
            percent = int(float(percent_str.rstrip('%')))
        if 0 <= fragment_index and 0 < fragment_count:
            percent = round(100 * fragment_index / fragment_count)
        elif downloaded_bytes >= 0 and total_bytes > 0:
            percent = round(100 * downloaded_bytes / total_bytes)

        accept_percent = False
        with status.lock:
            accept_percent = (
                percent and
                (status.next_progress() < percent) and
                (0 == (percent % 5))
            )  # fmt: skip
            if accept_percent:
                status.download_progress = percent
        if accept_percent:
            percent_str = f'{percent}%' if '?' == percent_str else percent_str
            if key:
                status.media_key = key
            status.task_status = f'[Downloading: {percent_str}]'
            status.update_task()
            log.info(f'[youtube-dl] downloading: {filename} - {percent_str} '
                     f'of {total} at {speed}, {eta} remaining')
    elif 'finished' == event['status']:
        # update the status for filepath to the finished value
        status = ProgressHookStatus.get(str(filepath))
        if status is None:
            status = ProgressHookStatus(**event)
            status.register(key, filename, str(filepath))
        status.download_progress = 100
        if key:
            status.media_key = key
        status.task_status = f'[Downloaded: {status.download_progress}%]'
        status.update_task()

        total_size_str = event.get('_total_bytes_str', '?').strip()
        elapsed_str = event.get('_elapsed_str', '?').strip()
        log.info(f'[youtube-dl] finished downloading: {filename} - '
                 f'{total_size_str} in {elapsed_str}')

        status.cleanup()


@close_db_after
def yt_dlp_postprocessor_hook(event):
    if not PPHookStatus.valid_status(event):
        log.warning(f'[youtube-dl] unknown postprocessor event: {event!r}')
        return

    name = 'Unknown'
    key = PPHookStatus.event_key(event)
    if key is None:
        key = name
    filepath = Path(event.get('filename', '???'))
    filename = filepath.name

    postprocessor = event.get('postprocessor', None)
    title = event['info_dict'].get('fulltitle', None)
    if title is None:
        title = event['info_dict'].get('title', None)
    if title:
        name = f'{key}: {title}'

    combined_key = f'{key}: {postprocessor}: {filepath.parent!s}'
    status = PPHookStatus.get(combined_key)
    if status is None:
        status = PPHookStatus(**event)
        status.register(key, combined_key, postprocessor, filename, str(status.filepath))

    status.media_name = name

    if 'started' == event['status']:
        remove_keys = (
            'formats',
            'automatic_captions',
        )
        logged_dict = filter_response(event['info_dict'], True)
        for ktr in remove_keys:
            logged_dict.pop(ktr, None)
        log.debug(repr(logged_dict))

    if 'Unknown' != key:
        status.media_key = key
    status.task_status = f'[{postprocessor}: {event["status"]}]'
    status.update_task()

    log.info(f'[{postprocessor}] {event["status"]} for: {name}')
    if 'started' == event['status'] and 'Merger' == postprocessor:
        files_to_merge = event['info_dict'].get('__files_to_merge') or list()
        log.info(f'[{postprocessor}] Files to merge: {files_to_merge}')
        from .models import Media

        db.close_old_connections()
        try:
            media = Media.objects.get(uuid=status.media_uuid)
            value = dict()
            value.update(media.new_metadata.value)
            value['requested_formats'] = event['info_dict'].get('requested_formats')
            value['requested_subtitles'] = event['info_dict'].get('requested_subtitles')
            media.new_metadata.value = value
            media.new_metadata.save()
        except Media.DoesNotExist:
            pass
        # ruff: ignore[BLE001]
        except Exception:
            log.exception('Failed to update metadata for: %s', str(status.media_uuid))
        finally:
            db.close_old_connections()
    elif 'finished' == event['status']:
        status.cleanup()


progress_hook.update({
    'class': ProgressHookStatus,
    'function': yt_dlp_progress_hook,
})

postprocessor_hook.update({
    'class': PPHookStatus,
    'function': yt_dlp_postprocessor_hook,
})

