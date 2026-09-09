#!/usr/bin/env python3

import argparse
import asyncio
import hashlib
import io
import json
import logging
import lzma
import os
import random
import re
import sqlite3
import sys
import time
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, BinaryIO, TextIO
from urllib.parse import urljoin

# --- THIRD PARTY LIBRARIES (Requires Installation) ---
# pip install aiohttp hat-syslog
import aiohttp

try:
    from hat.syslog.common import Facility, Severity
except ImportError:
    Facility = None
    Severity = None


@dataclass(frozen=True)
class _Settings:
    """Unified configuration for easy review and adjustment."""

    BATCH_SIZE: int = 250
    BUSY_TIMEOUT: float = 30.0
    COOPERATIVE_SLEEP: float = 0.5
    DEFAULT_RETRIES: int = 100
    HASH_CHUNK_SIZE: int = (1024) * 32 # KiB
    INITIAL_BACKOFF: float = 0.2
    MAX_BACKOFF: float = 15.0
    USER_AGENT: str = 'hat-syslog_tool/1.2'


@dataclass(frozen=True)
class _SqlTemplates:
    """Consolidated SQL templates to maintain schema synchronization."""

    create_log: str = '''
        CREATE TABLE IF NOT EXISTS log (
            entry_timestamp REAL, facility INTEGER, severity INTEGER,
            version INTEGER, msg_timestamp REAL, hostname TEXT,
            app_name TEXT, procid TEXT, msgid TEXT, data TEXT, msg TEXT
        );'''

    create_index: str = (
        'CREATE INDEX IF NOT EXISTS idx_entry_ts '
        'ON log (entry_timestamp DESC);'
    )

    create_staging: str = '''
        CREATE TEMPORARY TABLE staging_rows (
            entry_timestamp REAL, facility INTEGER, severity INTEGER,
            version INTEGER, msg_timestamp REAL, hostname TEXT,
            app_name TEXT, procid TEXT, msgid TEXT, data TEXT, msg TEXT,
            ext_id_ref INTEGER
        );'''

    create_tracker: str = '''
        CREATE TEMPORARY TABLE file_tracker (
            ext_id INTEGER PRIMARY KEY,
            log_rowid INTEGER DEFAULT 0,
            committed BOOLEAN DEFAULT 0
        );'''

    check_file_id: str = (
        'SELECT 1 FROM file_tracker WHERE ext_id = ? LIMIT 1'
    )

    check_log_exists: str = (
        'SELECT rowid FROM log '
        'WHERE entry_timestamp = ? AND msg = ? LIMIT 1'
    )

    insert_staging: str = (
        'INSERT INTO staging_rows VALUES '
        '(?,?,?,?,?,?,?,?,?,?,?,?)'
    )

    insert_tracker: str = (
        'INSERT INTO file_tracker (ext_id, committed) VALUES (?, 0)'
    )

    insert_tracker_skip: str = (
        'INSERT INTO file_tracker '
        '(ext_id, log_rowid, committed) VALUES (?, ?, 1)'
    )

    move_staging_to_log: str = '''
        INSERT INTO log (
            entry_timestamp, facility, severity, version, msg_timestamp,
            hostname, app_name, procid, msgid, data, msg
        )
        SELECT
            entry_timestamp, facility, severity, version, msg_timestamp,
            hostname, app_name, procid, msgid, data, msg
        FROM staging_rows'''

    update_tracker_committed: str = '''
        UPDATE file_tracker
        SET log_rowid = (
            SELECT l.rowid
            FROM log l
            JOIN staging_rows s
                ON l.entry_timestamp = s.entry_timestamp
                AND l.msg = s.msg
            WHERE s.ext_id_ref = file_tracker.ext_id
        ),
        committed = 1
        WHERE committed = 0
        AND EXISTS (
            SELECT 1
            FROM log l
            JOIN staging_rows s
                ON l.entry_timestamp = s.entry_timestamp
                AND l.msg = s.msg
            WHERE s.ext_id_ref = file_tracker.ext_id
        )'''

    clear_staging: str = 'DELETE FROM staging_rows'
    count_log: str = 'SELECT COUNT(*) FROM log'
    count_verified: str = (
        'SELECT COUNT(*) FROM file_tracker '
        'WHERE committed = 1 AND log_rowid > 0'
    )

    select_export_logs: str = '''
        SELECT facility, severity, app_name, procid, msg
        FROM log
        ORDER BY rowid ASC;'''


# Module-level instances
_CFG = _Settings()
_SQL = _SqlTemplates()


class OutputManager:
    """Uses class attributes to lock in original streams at module load time."""

    _ORIGINAL_STDOUT: TextIO = sys.stdout
    _ORIGINAL_STDERR: TextIO = sys.stderr

    def _base_print(
        self,
        lines: str | Iterable[str],
        stream: TextIO,
    ) -> None:
        if isinstance(lines, str):
            lines = (lines,)

        for line in lines:
            print(line, file=stream)

    def stdout_print(self, lines: str | Iterable[str]) -> None:
        self._base_print(lines, self._ORIGINAL_STDOUT)

    def stderr_print(self, lines: str | Iterable[str]) -> None:
        self._base_print(lines, self._ORIGINAL_STDERR)


def get_text_labels() -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return text labels for matching numerical tokens to strings."""

    facility_labels = (
        'KERN',
        'USER',
        'MAIL',
        'DAEMON',
        'AUTH',
        'SYSLOG',
        'LPR',
        'NEWS',
        'UUCP',
        'CRON',
        'AUTHPRIV',
        'FTP',
        'NTP',
        'AUDIT',
        'ALERT',
        'CLOCK',
        'LOCAL0',
        'LOCAL1',
        'LOCAL2',
        'LOCAL3',
        'LOCAL4',
        'LOCAL5',
        'LOCAL6',
        'LOCAL7',
    )

    severity_labels = (
        'EMERGENCY',
        'ALERT',
        'CRITICAL',
        'ERROR',
        'WARNING',
        'NOTICE',
        'INFORMATIONAL',
        'DEBUG',
    )

    return facility_labels, severity_labels


def get_fac_sev_mappers(
) -> tuple[Callable[[str], int], Callable[[str], int]]:
    """Return mapping functions for facility and severity strings."""

    if Facility is not None and Severity is not None:
        return (
            lambda label: Facility[label].value,
            lambda label: Severity[label].value,
        )

    facility_labels, severity_labels = get_text_labels()

    facility_map = {
        key: value for value, key in enumerate(facility_labels)
    }
    severity_map = {
        key: value for value, key in enumerate(severity_labels)
    }

    return (
        lambda label: facility_map.get(label, 1),
        lambda label: severity_map.get(label, 6),
    )


def extract_numeric_pid(procid: int | str | None) -> int | None:
    """Validate the input token and return a clean integer PID or None, if non-numeric."""

    if procid is None or isinstance(procid, int):
        return procid

    procid_str = procid.strip()

    if procid_str.isdigit():
        return int(procid_str)

    return None


def format_syslog_prefix(
    facility: int,
    severity: int,
    msg_str: str,
) -> str:
    """Prepend human-readable facility and severity labels to the message body."""

    facility_labels, severity_labels = get_text_labels()

    facility_text = (
        facility_labels[facility]
        if 0 <= facility < len(facility_labels)
        else str(facility)
    )

    severity_text = (
        severity_labels[severity]
        if 0 <= severity < len(severity_labels)
        else str(severity)
    )

    return f'[{facility_text}.{severity_text}] {msg_str}'


def fetch_scalar(
    cur: sqlite3.Cursor,
    query: str,
    params: Iterable[Any] = (),
) -> Any:
    """Execute a query and return its first column or None."""

    result = cur.execute(query, params).fetchone()

    if result is not None:
        return result[0]

    return None


def execute_with_backoff(
    retries: int,
    func: Callable[..., Any],
    *args: Any,
) -> Any:
    backoff = _CFG.INITIAL_BACKOFF
    max_attempts = 1 if 0 >= retries else retries

    for attempt in range(max_attempts):
        try:
            return func(*args)
        except sqlite3.OperationalError as exc:
            if 0 == retries or max_attempts - 1 == attempt:
                raise

            error_text = str(exc).lower()

            if not ('locked' in error_text or 'busy' in error_text):
                raise

            time.sleep(backoff + random.uniform(0, 0.1))
            backoff = min(backoff * 2, _CFG.MAX_BACKOFF)

    raise sqlite3.OperationalError(
        f'Database locked after {max_attempts} attempts.'
    )


def init_db(
    db_path: str,
    clean_requested: bool = False,
) -> sqlite3.Connection:
    if clean_requested and os.path.exists(db_path):
        raise FileExistsError(
            f"Safety Error: '{db_path}' exists. "
            "Specify a name that doesn't exist."
        )

    conn = sqlite3.connect(
        db_path,
        timeout=_CFG.BUSY_TIMEOUT,
    )

    with conn:
        conn.execute(_SQL.create_log)
        conn.execute(_SQL.create_index)

    return conn


def commit_batch(cur: sqlite3.Cursor) -> None:
    cur.execute(_SQL.move_staging_to_log)
    cur.execute(_SQL.update_tracker_committed)
    cur.execute(_SQL.clear_staging)
    cur.connection.commit()


def setup_logger(
    name: str,
    filename: str,
    log_dir: str,
    log_level: int = logging.DEBUG,
) -> logging.Logger:
    """Create a logger writing raw lines at or above the specified level."""

    filepath = os.path.join(log_dir, filename)
    handler = logging.FileHandler(
        filepath,
        mode='a',
        encoding='utf-8',
    )

    logger = logging.getLogger(name)
    logger.setLevel(log_level)
    logger.addHandler(handler)

    return logger


def process_and_route_log(
    facility: int,
    severity: int,
    app_name: str,
    procid: int | str | None,
    msg: Any,
    n_acc: logging.Logger,
    n_err: logging.Logger,
    g_acc: logging.Logger,
    g_err: logging.Logger,
    msg_log: logging.Logger,
) -> None:
    """Classify and route logs using strict numerical facility boundaries (17=local1, 18=local2)."""

    if not msg:
        return

    app_lower = app_name.lower() if app_name else ''
    msg_str = str(msg).strip()
    validated_pid = extract_numeric_pid(procid)

    procid_msg = (
        msg_str
        if validated_pid is None
        else f'(PID: {validated_pid}) {msg_str}'
    )

    # --- ROUTE NGINX (LOCAL1 = 17) ---
    if 17 == facility:
        if 'nginx' in app_lower:
            if 4 >= severity:
                n_err.info(msg_str)
            else:
                n_acc.info(msg_str)
        else:
            msg_log.info(
                format_syslog_prefix(
                    facility,
                    severity,
                    procid_msg,
                )
            )

    # --- ROUTE GUNICORN (LOCAL2 = 18) ---
    elif 18 == facility:
        if 'gunicorn' in app_lower:
            if 'access' in app_lower:
                g_acc.info(msg_str)
            else:
                g_err.info(msg_str)
        else:
            msg_log.info(
                format_syslog_prefix(
                    facility,
                    severity,
                    procid_msg,
                )
            )

    # --- ROUTE UNMATCHED FACILITIES ---
    else:
        msg_log.info(
            format_syslog_prefix(
                facility,
                severity,
                procid_msg,
            )
        )


def export_mode(db_path: str, log_dir: str) -> None:
    """Export database records from an existing hat-syslog SQLite file into reconstructed flat text log files."""

    out = OutputManager()

    if not os.path.exists(db_path):
        out.stderr_print(
            f'[-] Error: Target database file not found at "{db_path}".'
        )
        sys.exit(1)

    if os.path.exists(log_dir):
        out.stderr_print(
            f'[-] Safety Error: Target export directory "{log_dir}" '
            'already exists. Specify a brand new directory.'
        )
        sys.exit(1)

    os.makedirs(log_dir)

    nginx_access = setup_logger(
        'nginx_access',
        'nginx_access.log',
        log_dir,
    )
    nginx_error = setup_logger(
        'nginx_error',
        'nginx_error.log',
        log_dir,
    )
    gunicorn_access = setup_logger(
        'gunicorn_access',
        'gunicorn_access.log',
        log_dir,
    )
    gunicorn_error = setup_logger(
        'gunicorn_error',
        'gunicorn_error.log',
        log_dir,
    )
    messages_log = setup_logger(
        'messages',
        'messages.log',
        log_dir,
    )

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute(_SQL.select_export_logs)
        records = cursor.fetchall()

        for facility, severity, app_name, procid, msg in records:
            process_and_route_log(
                facility,
                severity,
                app_name,
                procid,
                msg,
                nginx_access,
                nginx_error,
                gunicorn_access,
                gunicorn_error,
                messages_log,
            )

        out.stdout_print(
            f'[+] Export complete. {len(records)} records distributed '
            f'inside: "{log_dir}"'
        )
    except sqlite3.Error as exc:
        out.stderr_print(
            f'[-] Error during database query execution: "{exc}"'
        )
        sys.exit(1)
    finally:
        conn.close()


class ByteTracker(io.BufferedIOBase):
    def __init__(self, raw: BinaryIO):
        self._raw = raw
        self.bytes_read = 0

    def read(self, size: int = -1) -> bytes:
        data = self._raw.read(size)
        self.bytes_read += len(data)
        return data


def convert_mode(
    stream: BinaryIO,
    db_path: str,
    retries: int,
    clean: bool,
    show_stats: bool,
) -> None:
    start_time = time.time()
    out = OutputManager()
    facility_labels, severity_labels = get_text_labels()
    get_facility, get_severity = get_fac_sev_mappers()

    def get_facility_text(facility: int) -> str:
        if 0 <= facility < len(facility_labels):
            return facility_labels[facility]
        return str(facility)

    def get_severity_text(severity: int) -> str:
        if 0 <= severity < len(severity_labels):
            return severity_labels[severity]
        return str(severity)

    head = stream.read(6)
    is_xz = head.startswith(b'\xfd7zXZ')
    data_io = ByteTracker(io.BytesIO(head + stream.read()))

    if is_xz:
        input_stream = lzma.open(data_io, 'rt')
    else:
        input_stream = io.TextIOWrapper(
            data_io,
            encoding='utf-8',
        )

    stats: dict[str, Any] = {
        'new': 0,
        'skipped': 0,
        'errors': 0,
        'uncompressed_bytes': 0,
        'tracker_seen': 0,
    }

    with execute_with_backoff(
        retries,
        init_db,
        db_path,
        clean,
    ) as conn:
        execute_with_backoff(
            retries,
            lambda: conn.executescript(
                f'{_SQL.create_staging}{_SQL.create_tracker}'
            ),
        )

        try:
            cur = conn.cursor()

            execute_with_backoff(
                retries,
                lambda: cur.execute('BEGIN IMMEDIATE'),
            )

            for line in input_stream:
                if not line.strip():
                    continue

                stats['uncompressed_bytes'] += len(
                    line.encode('utf-8')
                )

                try:
                    raw = json.loads(line)
                    ext_id = raw.get('id')
                    timestamp = raw.get('timestamp')
                    message_object = raw.get('msg', {})
                    message_text = message_object.get('msg', '')

                    if ext_id is not None:
                        stats['tracker_seen'] += 1

                        if fetch_scalar(
                            cur,
                            _SQL.check_file_id,
                            (ext_id,),
                        ) is not None:
                            stats['skipped'] += 1
                            continue

                    if timestamp is not None:
                        row_id = fetch_scalar(
                            cur,
                            _SQL.check_log_exists,
                            (timestamp, message_text),
                        )

                        if row_id is not None:
                            if ext_id is not None:
                                cur.execute(
                                    _SQL.insert_tracker_skip,
                                    (ext_id, row_id),
                                )

                            stats['skipped'] += 1
                            continue

                    fallback_facility = 1
                    facility_value = message_object.get(
                        'facility',
                        fallback_facility,
                    )

                    try:
                        if isinstance(facility_value, str):
                            facility_number = get_facility(
                                facility_value.strip().upper()
                            )
                        elif isinstance(facility_value, int):
                            facility_number = get_facility(
                                get_facility_text(facility_value)
                            )
                        else:
                            facility_number = fallback_facility
                    except (
                        KeyError,
                        TypeError,
                        ValueError,
                        IndexError,
                    ):
                        facility_number = fallback_facility

                    fallback_severity = 6
                    severity_value = message_object.get(
                        'severity',
                        fallback_severity,
                    )

                    try:
                        if isinstance(severity_value, str):
                            severity_number = get_severity(
                                severity_value.strip().upper()
                            )
                        elif isinstance(severity_value, int):
                            severity_number = get_severity(
                                get_severity_text(severity_value)
                            )
                        else:
                            severity_number = fallback_severity
                    except (
                        KeyError,
                        TypeError,
                        ValueError,
                        IndexError,
                    ):
                        severity_number = fallback_severity

                    cur.execute(
                        _SQL.insert_staging,
                        (
                            timestamp,
                            facility_number,
                            severity_number,
                            message_object.get('version'),
                            message_object.get('timestamp'),
                            message_object.get('hostname'),
                            message_object.get('app_name'),
                            message_object.get('procid'),
                            message_object.get('msgid'),
                            json.dumps(message_object.get('data')),
                            message_text,
                            ext_id,
                        ),
                    )

                    if ext_id is not None:
                        cur.execute(
                            _SQL.insert_tracker,
                            (ext_id,),
                        )

                    stats['new'] += 1

                    if 0 == stats['new'] % _CFG.BATCH_SIZE:
                        commit_batch(cur)
                        time.sleep(_CFG.COOPERATIVE_SLEEP)

                        execute_with_backoff(
                            retries,
                            lambda: cur.execute('BEGIN IMMEDIATE'),
                        )

                # ruff: ignore[BLE001]
                except Exception:
                    # A malformed record must not abort the full conversion.
                    stats['errors'] += 1
                    continue

            commit_batch(cur)

            total_rows = fetch_scalar(
                cur,
                _SQL.count_log,
            )

            stats['committed_tracker'] = fetch_scalar(
                cur,
                _SQL.count_verified,
            )

        except (OSError, sqlite3.Error, ValueError) as exc:
            conn.rollback()
            out.stderr_print(
                f'[-] Fatal conversion error: {exc}'
            )
            sys.exit(1)
        finally:
            input_stream.close()

    if show_stats:
        duration = time.time() - start_time
        raw_total = data_io.bytes_read

        ratio = (
            stats['uncompressed_bytes'] / raw_total
            if raw_total > 0
            else 0.0
        )

        throughput = (
            stats['new'] / duration
            if duration > 0
            else 0.0
        )

        out.stdout_print(
            [
                '',
                '[+] Statistics Report:',
                f'    New Rows:          {stats["new"]}',
                f'    Skipped:           {stats["skipped"]}',
                f'    Errors:            {stats["errors"]}',
                f'    Database Total:    {total_rows}',
                f'    Tracker Verified:  '
                f'{stats.get("committed_tracker", 0)}',
                f'    Duration:          {duration:.2f}s '
                f'({throughput:.1f} rows/s)',
                f'    Data Processed:    '
                f'{stats["uncompressed_bytes"] / 1024 / 1024:.2f} MiB',
                f'    Source Processed:  '
                f'{raw_total / 1024 / 1024:.2f} MiB',
            ]
        )

        if is_xz:
            out.stdout_print(
                f'    Expansion Ratio:   {ratio:.2f}x'
            )

    expected_tracker_rows = stats.get('tracker_seen', 0)
    committed_tracker_rows = stats.get('committed_tracker', 0)

    if expected_tracker_rows != committed_tracker_rows:
        out.stderr_print(
            [
                '',
                '!' * 80,
                '!!! CRITICAL INTEGRITY FAILURE DETECTED !!!'.center(80),
                '!' * 80,
                f'Expected committed rows: {expected_tracker_rows}',
                f'Verified committed rows: {committed_tracker_rows}',
                '',
                'SITUATION: Tracker count does not match database. '
                'Inconsistency likely.',
                '!' * 80,
                '',
            ]
        )
        sys.exit(2)


def verify_mode(
    stream: BinaryIO,
    filename: str | None,
) -> tuple[bool, BinaryIO]:
    out = OutputManager()
    hasher = hashlib.sha512()
    buffer = io.BytesIO()

    while chunk := stream.read(_CFG.HASH_CHUNK_SIZE):
        hasher.update(chunk)
        buffer.write(chunk)

    digest = hasher.hexdigest()
    buffer.seek(0)

    if filename and '-' != filename:
        match = re.search(
            r'\.([a-f0-9]{6})\.([a-f0-9]{6})\.',
            filename,
        )

        if match:
            start, end = match.groups()

            if not (
                digest.startswith(start)
                and digest.endswith(end)
            ):
                out.stderr_print(
                    f'[-] Integrity Failure: Hash '
                    f'({digest[:6]}..{digest[-6:]}) != '
                    f'tag ({start}.{end})'
                )
                return False, buffer

    try:
        head = buffer.read(6)
        buffer.seek(0)

        if head.startswith(b'\xfd7zXZ'):
            with lzma.open(buffer, 'rt') as decompressed:
                json.loads(decompressed.readline())
        else:
            wrapper = io.TextIOWrapper(
                buffer,
                encoding='utf-8',
            )
            json.loads(wrapper.readline())
            wrapper.detach()

        buffer.seek(0)

    except (
        json.JSONDecodeError,
        UnicodeDecodeError,
        lzma.LZMAError,
        OSError,
        ValueError,
    ) as exc:
        out.stderr_print(f'[-] Format Failure: {exc}')
        return False, buffer

    out.stdout_print(
        f'[+] Verification passed: '
        f'{filename if filename else "stdin"}'
    )

    return True, buffer


def get_file_hex_digest(filename: str) -> str:
    """Read a file in chunks and return its SHA-512 hex digest."""

    hasher = hashlib.sha512()

    with open(filename, 'rb') as file:
        while chunk := file.read(_CFG.HASH_CHUNK_SIZE):
            hasher.update(chunk)

    return hasher.hexdigest()


@contextmanager
def input_stream(filename: str) -> Iterator[BinaryIO]:
    """Yield stdin or an opened file without closing stdin."""

    if filename == '-':
        yield sys.stdin.buffer
        return

    with open(filename, 'rb') as file:
        yield file


async def backup_mode(
    url: str,
    output_dir: str | None,
) -> None:
    now_string = datetime.now(timezone.utc).strftime(
        '%Y%m%dT%H%M%SZ'
    )

    out = OutputManager()
    filename = f'syslog_{now_string}.{{tag}}.jsonl.xz'
    headers = {'User-Agent': _CFG.USER_AGENT}

    target_url = urljoin(
        f'{url.rsplit("/index.html", 1)[0]}/',
        'backup',
    )

    temporary_path = (
        os.path.join(output_dir, filename)
        if output_dir
        else filename
    )

    path = temporary_path

    if os.path.exists(path):
        raise FileExistsError(
            f"Safety Error: '{path}' already exists."
        )

    try:
        async with (
            aiohttp.ClientSession(headers=headers) as session,
            session.get(target_url) as response,
        ):
            response.raise_for_status()

            with lzma.open(path, 'wb', preset=9) as compressed_output:
                out.stdout_print(
                    f'[*] Streaming live to {path}...'
                )

                async for line in response.content:
                    compressed_output.write(line)

        # Now that the file is closed and flushed, hash the compressed file
        # Build tag: 6 chars from start, 6 from end
        digest = get_file_hex_digest(path)
        tag = f'{digest[:6]}.{digest[-6:]}'
        path = temporary_path.format(tag=tag)

        if os.path.exists(path):
            raise FileExistsError(
                f"Safety Error: '{path}' already exists."
            )

        os.rename(temporary_path, path)

        if os.path.exists(path):
            out.stdout_print(
                f'[+] Backup saved to: {path}'
            )

    except (
        aiohttp.ClientError,
        asyncio.TimeoutError,
        OSError,
        lzma.LZMAError,
    ) as exc:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)

        out.stderr_print(f'[-] Backup failed: {exc}')
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description='hat-syslog Backup/Restoration Tool'
    )

    parser.add_argument(
        'input',
        help='URL for backup, path to logs backup/DB file, or "-"',
    )

    parser.add_argument(
        '--out',
        '-o',
        help=(
            'Database (.db) path for convert OR '
            'directory for backup/export'
        ),
    )

    parser.add_argument(
        '--backup',
        action='store_true',
        default=True,
    )

    parser.add_argument(
        '--convert',
        '--import',
        action='store_true',
        help='Import logs from a backup file into a database file',
    )

    parser.add_argument(
        '--export',
        '--split',
        action='store_true',
        help='Export logs into individual files from an existing database',
    )

    parser.add_argument(
        '--verify',
        action='store_true',
    )

    parser.add_argument(
        '--clean',
        action='store_true',
        help='Error out if target database exists',
    )

    parser.add_argument(
        '--retries',
        type=int,
        default=_CFG.DEFAULT_RETRIES,
    )

    parser.add_argument(
        '--stats',
        action='store_true',
        help=(
            'Report statistics about conversion from a logs backup '
            'file to a database'
        ),
    )

    args = parser.parse_args()
    out = OutputManager()

    if args.backup and not args.input.startswith(
        ('http://', 'https://')
    ):
        args.backup = False

    match args:
        case _ if args.export:
            if not args.input:
                out.stderr_print(
                    '[-] Error: input database file path is required '
                    'for export mode.'
                )
                sys.exit(1)

            if not args.out:
                out.stderr_print(
                    '[-] Error: --out directory parameter is required '
                    'for export mode.'
                )
                sys.exit(1)

            export_mode(args.input, args.out)

        case _ if args.verify and not args.convert:
            if not args.input:
                out.stderr_print(
                    '[-] Error: Input path reference or "-" is required '
                    'to verify.'
                )
                sys.exit(1)

            with input_stream(args.input) as raw_buffer:
                success, _ = verify_mode(
                    raw_buffer,
                    args.input,
                )

            sys.exit(0 if success else 1)

        case _ if args.convert:
            if not args.input:
                out.stderr_print(
                    '[-] Error: Input path reference or "-" is required '
                    'for conversion.'
                )
                sys.exit(1)

            if not args.out:
                out.stderr_print(
                    '[-] Error: --out is required for conversion.'
                )
                sys.exit(1)

            try:
                with input_stream(args.input) as raw_buffer:
                    success, verified_buffer = verify_mode(
                        raw_buffer,
                        args.input,
                    )

                if not success:
                    sys.exit(1)

                convert_mode(
                    verified_buffer,
                    args.out,
                    args.retries,
                    args.clean,
                    args.stats,
                )

            except (
                OSError,
                sqlite3.Error,
                ValueError,
            ) as exc:
                out.stderr_print(f'[-] Error: {exc}')

        case _ if args.backup:
            if not args.input:
                out.stderr_print(
                    '[-] Error: URL path configuration is required '
                    'for backup streaming.'
                )
                sys.exit(1)

            asyncio.run(
                backup_mode(
                    args.input,
                    args.out,
                )
            )

        case _:
            out.stderr_print(
                '[-] Error: Specify URL for backup, --convert for '
                'local backup files, or --export to process a database.'
            )
            sys.exit(1)


if '__main__' == __name__:
    main()

