import contextlib
import json
import os
import shutil
import sqlite3
import time

from pathlib import Path

from django import db
from django.core.management.base import BaseCommand

from common.batched import batched
from common.utils import remove_enclosed
from sync.models import Media
from sync.tasks import get_media_download_task


class Command(BaseCommand):
    help = 'Processes hook updates with DB throttling via SQLite WAL queue'

    def add_arguments(self, parser):
        parser.add_argument('--temp-dir', type=Path, required=True)
        parser.add_argument('--pid', type=int, default=0, help='Optional PID to monitor for lifecycle')
        parser.add_argument('--threshold', type=int, default=100)

    def handle(self, *args, **options):
        temp_dir = options['temp_dir']
        db_path = temp_dir / 'queue.db'
        self.db_path = db_path
        monitor_pid = options['pid']
        pid_alive = True
        threshold = max(5, options['threshold'])
        
        update_buffer = {}
        last_flush_time = time.monotonic()
        flush_interval = 0.5 
        consecutive_empty = 0
        batch_size = 100
        sql_full_batch = f"DELETE FROM queue WHERE id IN ({', '.join('?' * batch_size)})"

        try:
            while consecutive_empty < threshold and pid_alive:
                has_data = False
                try:
                    with self.sqlite3_db(transaction=True) as conn:
                        with contextlib.closing(
                            conn.execute('SELECT id, payload FROM queue ORDER BY id')
                        ) as cursor:
                            rows = cursor.fetchall()
                            has_data = bool(rows)
                        
                        if has_data:
                            ids_to_delete = {row[0] for row in rows}
                            for _, payload_json in rows:
                                payload = json.loads(payload_json)
                                cache_key = payload.get('media_uuid') or payload.get('media_key')
                                update_buffer[cache_key] = payload
                            
                            try:
                                for batch in batched(tuple(ids_to_delete), batch_size, strict=True):
                                    try:
                                        self.sqlite3_run(conn, sql_full_batch, batch)
                                        ids_to_delete.difference_update(batch)
                                    except ValueError as exc:
                                        exc._from_loop_body = True
                                        raise
                            except ValueError as exc:
                                if getattr(exc, '_from_loop_body', False):
                                    raise

                                # batched generated this exception
                                partial_batch = tuple(ids_to_delete)
                                sql_partial_batch = sql_full_batch.split('?', 1)[0] + ', '.join('?' * len(partial_batch)) +')'
                                self.sqlite3_run(conn, sql_partial_batch, partial_batch)
                except sqlite3.OperationalError:
                    pass

                if has_data:
                    consecutive_empty = 0
                else:
                    consecutive_empty += 1

                # Throttled Flush
                now = time.monotonic()
                update_buffer.pop(None, None)
                if update_buffer and (flush_interval < (now - last_flush_time)):
                    self.flush_to_db(update_buffer)
                    update_buffer.clear()
                    last_flush_time = now

                # --- Exit Logic ---
                if 1 < monitor_pid <= (1<<22):
                    # Mode: Process Monitoring
                    # Only exit if the process is dead AND the queue/buffer are drained
                    pid_alive = False
                    with contextlib.suppress(OSError):
                        os.kill(monitor_pid, 0)
                        pid_alive = True
                    
                    if not pid_alive and (has_data or update_buffer):
                        pid_alive = True
                
                time.sleep(0.1)

        finally:
            # Ensure final buffer is flushed before deleting the temp dir
            if update_buffer:
                self.flush_to_db(update_buffer)
            shutil.rmtree(temp_dir, ignore_errors=True)

    def flush_to_db(self, buffer):
        db.close_old_connections()
        for data in buffer.values():
            media_key = data['media_key']
            media_rowid = data['media_rowid']
            try:
                media_rowid = int(media_rowid)
            except (TypeError, ValueError):
                media_rowid = int()
            media_uuid = data['media_uuid']
            task_status = data['task_status']
            verbose_name_raw = data['task_verbose_name']

            media = task = None
            if media_uuid:
                try:
                    media = Media.objects.get(uuid=media_uuid)
                    task = get_media_download_task(str(media.pk))
                except Media.DoesNotExist:
                    continue
            elif media_key:
                mqs = Media.objects.exclude(
                    skip=True, manual_skip=True, downloaded=True
                ).filter(
                    source__download_media=True, can_download=True, key=media_key
                )
                for m in mqs:
                    t = get_media_download_task(str(m.pk))
                    if t:
                        media, task = m, t
                        break
                if media and 0 < media_rowid:
                    with (
                        contextlib.suppress(sqlite3.Error),
                        self.sqlite3_db(transaction=False) as conn,
                    ):
                        sql = 'UPDATE media SET uuid = ? WHERE id = ?'
                        self.sqlite3_run(conn, sql, (str(media.uuid), media_rowid))

            if media and task:
                if verbose_name_raw is None:
                    verbose_name_raw = remove_enclosed(task.verbose_name, '[', ']', ' ')
                task.verbose_name = f'{task_status} {verbose_name_raw}'
                task.save()

        db.close_old_connections()

    @staticmethod
    def sqlite3_run(connection, /, sql, args=()):
        # close the unassigned cursor
        with contextlib.closing(connection.execute(sql, args)):
            pass

    @contextlib.contextmanager
    def sqlite3_db(self, /, transaction: bool = False):
        with contextlib.closing(
            sqlite3.connect(self.db_path, isolation_level=None),
        ) as connection, connection:
            if transaction:
                self.sqlite3_run(connection, 'BEGIN IMMEDIATE')
            yield connection

