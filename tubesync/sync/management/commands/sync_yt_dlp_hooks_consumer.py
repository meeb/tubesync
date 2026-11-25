from __future__ import annotations

import contextlib
import json
import os
import sqlite3
import time

from pathlib import Path

from django import db
from django.core.management.base import BaseCommand

from common.utils import remove_enclosed
from sync.models import Media
from sync.tasks import get_media_download_task


POLL_INTERVAL = 0.1
FLUSH_INTERVAL = 0.5
BATCH_SIZE = 100


class Command(BaseCommand):
    help = 'Consumes generation-based SQLite hook queues'

    def add_arguments(self, parser):
        parser.add_argument('--temp-dir', type=Path, required=True)
        parser.add_argument('--generation', type=str, required=True)
        parser.add_argument('--coordination-db', type=Path, required=True)
        parser.add_argument('--pid', type=int, default=0)

    def handle(self, *args, **options):
        self.temp_dir: Path = options['temp_dir']
        self.db_path = self.temp_dir / "queue.db"
        self.coordination_path: Path = options['coordination_db']
        self.generation = options['generation']
        self.monitor_pid = options['pid']

        self._ensure_coordination_schema()
        update_buffer: dict[str, dict] = {}
        last_flush = time.monotonic()

        try:
            while True:
                rows = []
                try:
                    rows = self._take_rows()
                except sqlite3.Error:
                    self.stderr.write(
                        f'Queue read failed for generation {self.generation}'
                    )
                    time.sleep(POLL_INTERVAL)

                for payload in rows:
                    token = payload.get('download_token')
                    if not token:
                        continue
                    previous = update_buffer.get(token)
                    if (
                        previous is None
                        or payload.get('sequence', 0)
                        >= previous.get('sequence', 0)
                    ):
                        update_buffer[token] = payload

                now = time.monotonic()
                retired = self._is_retired() or self._parent_is_dead()

                if update_buffer and (
                    now - last_flush >= FLUSH_INTERVAL or retired
                ):
                    self.flush_to_db(update_buffer)
                    update_buffer.clear()
                    last_flush = now

                if retired and not rows and not update_buffer:
                    break

                time.sleep(POLL_INTERVAL)

        finally:
            # Do not delete the generation directory here. The producer owns
            # cleanup and waits for this process to exit first.
            db.close_old_connections()

    def _connect(self, path: Path) -> sqlite3.Connection:
        conn = sqlite3.connect(
            path,
            isolation_level=None,
            timeout=30,
        )
        conn.execute('PRAGMA busy_timeout = 30000')
        return conn

    def _ensure_coordination_schema(self) -> None:
        self.coordination_path.parent.mkdir(parents=True, exist_ok=True)
        with contextlib.closing(self._connect(self.coordination_path)) as conn:
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

    def _take_rows(self) -> list[dict]:
        with contextlib.closing(self._connect(self.db_path)) as conn:
            conn.execute('BEGIN IMMEDIATE')
            try:
                rows = conn.execute(
                    'SELECT id, payload FROM queue ORDER BY id LIMIT ?',
                    (BATCH_SIZE,),
                ).fetchall()

                if rows:
                    conn.executemany(
                        'DELETE FROM queue WHERE id = ?',
                        [(row_id,) for row_id, _ in rows],
                    )
                conn.execute('COMMIT')
            except Exception:
                with contextlib.suppress(sqlite3.Error):
                    conn.execute('ROLLBACK')
                raise

        payloads = []
        for _, raw in rows:
            try:
                payload = json.loads(raw)
                if isinstance(payload, dict):
                    payloads.append(payload)
            except (TypeError, ValueError):
                self.stderr.write(
                    f'Invalid queue payload in generation {self.generation}'
                )
        return payloads

    def _is_retired(self) -> bool:
        try:
            with contextlib.closing(self._connect(self.db_path)) as conn:
                row = conn.execute(
                    "SELECT value FROM meta WHERE key = 'lifecycle'"
                ).fetchone()
            return bool(row and row[0] in {'retired', 'failed'})
        except sqlite3.Error:
            return True

    def _parent_is_dead(self) -> bool:
        if not (1 < self.monitor_pid <= (1 << 22)):
            return False
        try:
            os.kill(self.monitor_pid, 0)
            return False
        except OSError:
            return True

    def flush_to_db(self, buffer: dict[str, dict]) -> None:
        for payload in sorted(
            buffer.values(),
            key=lambda item: item.get('sequence', 0),
        ):
            try:
                self._apply_payload(payload)
            except Exception:
                # Queue rows have already been deleted; failed-generation
                # processing is best-effort by design.
                self.stderr.write(
                    'Failed to apply a hook update in generation '
                    f'{self.generation}'
                )
                db.close_old_connections()
            finally:
                db.close_old_connections()

    def _resolve_media(self, media_key: str) -> tuple[Media | None, object | None]:
        candidates = Media.objects.filter(
            source__download_media=True,
            can_download=True,
            key=media_key,
            skip=False,
            manual_skip=False,
            downloaded=False,
        ).order_by('pk')

        for media in candidates:
            task = get_media_download_task(str(media.pk))
            if task:
                return media, task

        return None, None

    def _apply_payload(self, payload: dict) -> None:
        token = payload.get('download_token')
        media_key = payload.get('media_key')
        media_uuid = payload.get('media_uuid')
        sequence = int(payload.get('sequence') or 0)

        if not token or not media_key:
            return

        db.close_old_connections()

        # This transaction serializes updates from old and new consumers.
        # Sequence checks stop a slow retiring consumer from applying stale
        # status after a newer generation has already updated the task.
        with contextlib.closing(
            self._connect(self.coordination_path)
        ) as coordination:
            coordination.execute('BEGIN IMMEDIATE')
            try:
                row = coordination.execute(
                    """
                    SELECT last_sequence
                    FROM download_state
                    WHERE download_token = ?
                    """,
                    (token,),
                ).fetchone()
                if row and sequence <= row[0]:
                    coordination.execute('COMMIT')
                    return

                mapping = coordination.execute(
                    """
                    SELECT media_uuid
                    FROM download_map
                    WHERE download_token = ?
                    """,
                    (token,),
                ).fetchone()

                if mapping and mapping[0]:
                    media_uuid = mapping[0]

                media = None
                task = None

                if media_uuid:
                    try:
                        media = Media.objects.get(uuid=media_uuid)
                        task = get_media_download_task(str(media.pk))
                    except Media.DoesNotExist:
                        media = None
                        task = None
                else:
                    media, task = self._resolve_media(str(media_key))
                    if media is not None:
                        media_uuid = str(media.uuid)
                        coordination.execute(
                            """
                            INSERT INTO download_map(
                                download_token, media_key, media_uuid
                            ) VALUES (?, ?, ?)
                            ON CONFLICT(download_token) DO UPDATE SET
                                media_key = excluded.media_key,
                                media_uuid = excluded.media_uuid
                            """,
                            (token, str(media_key), media_uuid),
                        )

                # Keep the resolved mapping in this generation as well.
                if media_uuid:
                    with contextlib.closing(self._connect(self.db_path)) as gen:
                        gen.execute(
                            """
                            INSERT INTO download_map(
                                download_token, media_key, media_uuid
                            ) VALUES (?, ?, ?)
                            ON CONFLICT(download_token) DO UPDATE SET
                                media_key = excluded.media_key,
                                media_uuid = COALESCE(
                                    excluded.media_uuid,
                                    download_map.media_uuid
                                )
                            """,
                            (token, str(media_key), media_uuid),
                        )

                if media is None or task is None:
                    coordination.execute('COMMIT')
                    return

                verbose_name = payload.get('task_verbose_name')
                if verbose_name is None:
                    verbose_name = remove_enclosed(
                        task.verbose_name, '[', ']', ' '
                    )
                task.verbose_name = (
                    f"{payload.get('task_status', '')} {verbose_name}"
                )
                task.save()

                coordination.execute(
                    """
                    INSERT INTO download_state(download_token, last_sequence)
                    VALUES (?, ?)
                    ON CONFLICT(download_token) DO UPDATE SET
                        last_sequence = excluded.last_sequence
                    """,
                    (token, sequence),
                )
                coordination.execute('COMMIT')

            except Exception:
                with contextlib.suppress(sqlite3.Error):
                    coordination.execute('ROLLBACK')
                raise

