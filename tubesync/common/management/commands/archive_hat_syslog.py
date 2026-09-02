import sqlite3
import tempfile
import time
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Copies a number of rows from a live or stopped source SQLite syslog database into a new file using safety constraints.'
    avg_row_size_bytes: int = 768
    batch_size: int = 1000
    batch_sleep: float = 0.05

    def add_arguments(self, parser):
        parser.add_argument(
            '--stopped',
            action='store_true',
            default=False,
            help='Source service is stopped. Allows raw attached-db file transfers instead of safe live streaming.',
        )

        parser.add_argument(
            '--vacuum',
            action='store_true',
            default=False,
            help='Optimize the database after all the rows were added (Only applies to --stopped)',
        )

        parser.add_argument('source_db_path', type=str, help='Path to the source SQLite database file')

        parser.add_argument('destination_path', type=str, help='Arbitrary destination directory path for the new directory')

        parser.add_argument('limit', type=int, help='The maximum number of rows to copy from the source table')

    def handle(self, *args, **options):
        row_limit: int = options['limit']
        if not (200 <= row_limit <= 10_000_000):
            raise CommandError(f'Invalid row limit: {row_limit:,}. Must be between 200 and 10,000,000.')

        source_path: Path = Path(options['source_db_path'])
        try:
            source_path = source_path.resolve(strict=True)
        except (FileNotFoundError, OSError) as e:
            raise CommandError(f'Source database file not found or inaccessible at: {source_path}. Error: {e}')

        destination_path: Path = Path(options['destination_path']).resolve(strict=False)
        if not destination_path.exists():
            raise CommandError(f'Destination path is not a valid directory or does not exist: {destination_path}')

        blocked_bytes: tuple[int, ...] = (39, 34, 0, 42, 63, 58, 60, 62, 124, 96, 59)

        # Create the unique temporary directory INSIDE the specified arbitrary destination path
        temp_dir: str = tempfile.mkdtemp(prefix='tmp_', dir=destination_path)
        target_path: Path = Path(temp_dir) / source_path.name

        resolved_target: str = str(target_path.resolve(strict=False))
        if any(b in blocked_bytes for b in resolved_target.encode('utf-8')):
            self._cleanup_temp_dir(temp_dir)
            raise CommandError('Operation aborted! Resolved target path contains invalid filesystem or quote bytes.')

        self.stdout.write(self.style.SUCCESS(f'Created temp directory: {temp_dir}'))
        self.stdout.write(f'Target database file: {target_path}')

        if options['stopped']:
            self.stdout.write('Service stopped flag detected. Executing attached legacy migration pathway...')
            self._handle_stopped(source_path, target_path, temp_dir, row_limit, options['vacuum'])
        else:
            self.stdout.write('Service active. Executing un-locked in-memory streaming loop pipeline...')
            self._handle_live(source_path, target_path, temp_dir, row_limit)

    def _cleanup_temp_file(self, path: Path | str) -> None:
        path = Path(path)
        if path.exists():
            try:
                path.unlink()
            except OSError:
                pass

    def _cleanup_temp_dir(self, directory: Path | str) -> None:
        directory = Path(directory)
        try:
            for p in directory.iterdir():
                if p.is_dir():
                    self._cleanup_temp_dir(p)
                elif p.is_symlink():
                    # symbolic links may not "exist"
                    p.unlink()
                else:
                    self._cleanup_temp_file(p)
            directory.rmdir()
        except OSError:
            pass

    def _handle_stopped(self, source_path: Path, target_path: Path, temp_dir: str, row_limit: int, run_vacuum: bool) -> None:
        """Legacy configuration pathway optimized for an explicitly stopped service context."""
        conn = None
        try:
            # Establish connection to the new target database file
            conn = sqlite3.connect(target_path, isolation_level=None)
            cursor = conn.cursor()

            # Set auto_vacuum on the completely blank disk database file
            cursor.execute('PRAGMA auto_vacuum = FULL;')

            # Attach the old source database strictly as read-only using URI mode
            cursor.execute(f"ATTACH DATABASE 'file:{source_path}?mode=ro' AS old;")

            # Dynamically discover the active logging table name from the attached schema
            cursor.execute(
                "SELECT name, sql FROM old.sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
            table_info = cursor.fetchone()
            if table_info is None:
                conn.close()
                self._cleanup_temp_file(target_path)
                raise CommandError('Source database does not contain any user tables.')

            table_name: str
            create_schema_sql: str
            table_name, create_schema_sql = table_info

            # Discover and save all associated indexes for deferred execution AFTER insertion
            cursor.execute(f"SELECT sql FROM old.sqlite_schema WHERE type='index' AND tbl_name='{table_name}' AND sql IS NOT NULL;")
            index_sqls: list[str] = [row.__getitem__(0) for row in cursor.fetchall()]

            # Gather the rest of the column names cleanly, filtering out rowid metadata structures
            cursor.execute(f"PRAGMA old.table_info('{table_name}');")
            cols = [row.__getitem__(1) for row in cursor.fetchall() if row.__getitem__(1) != 'rowid']
            col_string = ', '.join(cols)

            # Lock down the exact starting rowid boundary for our target subset
            cursor.execute(f'''
                SELECT MIN(rowid), MAX(rowid) FROM (
                    SELECT rowid FROM old.{table_name}
                    ORDER BY rowid DESC
                    LIMIT {row_limit}
                )
            ''')
            boundary_res = cursor.fetchone()
            if boundary_res is None or boundary_res.__getitem__(0) is None:
                conn.close()
                self._cleanup_temp_file(target_path)
                raise CommandError(f"Source table '{table_name}' is empty.")

            start_rowid: int = boundary_res.__getitem__(0)
            max_rowid: int = boundary_res.__getitem__(1)

            # Create a temporary staging table by attaching a specialized in-memory database
            cursor.execute("ATTACH DATABASE ':memory:' AS mem;")

            staging_table: str = 'tmp_staging_log_table'
            modified_sql = create_schema_sql.replace(table_name, f'mem.{staging_table}', 1).replace('(', '(rowid INTEGER PRIMARY KEY, ', 1)
            cursor.execute(modified_sql)

            # Re-create the actual clean table layout matching the original structure exactly inside the main disk file
            cursor.execute(create_schema_sql)

            # Step forward chronologically from the lowest bounded rowid up to the maximum rowid
            self.stdout.write(f"Streaming {row_limit:,} log records chronologically from '{table_name}' in batches of {self.batch_size}...")

            current_chunk_start: int = start_rowid
            while current_chunk_start <= max_rowid:
                current_chunk_end: int = min(current_chunk_start + self.batch_size - 1, max_rowid)

                # Batch Step 1: Read a chronological chunk from the source directly into attached RAM database
                cursor.execute(f'''
                    INSERT INTO mem.{staging_table} (rowid, {col_string})
                    SELECT rowid, {col_string} FROM old.{table_name}
                    WHERE rowid BETWEEN ? AND ?
                    ORDER BY rowid ASC
                ''', (current_chunk_start, current_chunk_end))

                # Batch Step 2: Flush from the attached RAM database directly into the clean main disk table
                cursor.execute(f'''
                    INSERT INTO main.{table_name} (rowid, {col_string})
                    SELECT rowid, {col_string} FROM mem.{staging_table}
                    ORDER BY rowid ASC
                ''')

                # Batch Step 3: Clear the memory staging table completely for the next iteration pass
                cursor.execute(f'DELETE FROM mem.{staging_table}')

                current_chunk_start += self.batch_size

            # Success: Close files handles and drop the source database link as early as possible
            cursor.execute('DETACH DATABASE old;')

            # Securely drop and detach the memory container from the operational workspace
            cursor.execute(f'DROP TABLE mem.{staging_table}')
            cursor.execute('DETACH DATABASE mem;')

            # Performance Win: Rebuild all indexes in a single sequential pass now that clean data is loaded
            if index_sqls:
                self.stdout.write('Rebuilding index structures...')
                for index_sql in index_sqls:
                    cursor.execute(index_sql)

            conn.commit()
            if run_vacuum:
                self.stdout.write('Optimizing database structure...')
                cursor.execute('VACUUM;')
            conn.close()
            conn = None

            self.stdout.write(self.style.SUCCESS(f'Successfully archived database to: {target_path}'))

        except sqlite3.Error as e:
            raise CommandError(f'SQLite error occurred during migration: {e}')
        finally:
            if conn:
                conn.close()
                self._cleanup_temp_file(target_path)
            if not target_path.exists():
                self._cleanup_temp_dir(temp_dir)

    def _handle_live(self, source_path: Path, target_path: Path, temp_dir: str, rows_limit: int) -> None:
        """Safe execution path optimized for a live, un-locked running hat-syslog-server environment."""
        src_conn = sqlite3.connect(source_path, isolation_level=None)
        src_cursor = src_conn.cursor()

        calculated_kib: int = (max(rows_limit, self.batch_size) * self.avg_row_size_bytes) // 1024
        src_cursor.execute(f'PRAGMA cache_size = -{calculated_kib}')

        src_cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        table_info = src_cursor.fetchone()
        if table_info is None:
            src_conn.close()
            self._cleanup_temp_dir(temp_dir)
            raise CommandError('Source database does not contain any user tables.')

        table_name: str
        create_schema_sql: str
        table_name, create_schema_sql = table_info

        src_cursor.execute(f"SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name='{table_name}' AND sql IS NOT NULL")
        index_sqls: list[str] = [row.__getitem__(0) for row in src_cursor.fetchall()]

        src_cursor.execute(f'SELECT MAX(rowid) FROM {table_name}')
        res = src_cursor.fetchone()

        if res is None or (max_rowid := res.__getitem__(0)) is None:
            src_conn.close()
            self._cleanup_temp_dir(temp_dir)
            raise CommandError(f"Source table '{table_name}' is empty.")

        min_needed_rowid: int = 1 + max_rowid - rows_limit

        mem_conn = sqlite3.connect(':memory:', isolation_level=None)
        mem_cursor = mem_conn.cursor()

        staging_table: str = 'tmp_staging_log_table'
        modified_schema_sql: str = create_schema_sql.replace(table_name, staging_table, 1).replace('(', '(rowid INTEGER PRIMARY KEY,', 1)
        mem_cursor.execute(modified_schema_sql)

        current_start_rowid: int = min_needed_rowid
        total_copied: int = 0

        try:
            while current_start_rowid <= max_rowid:
                current_end_rowid: int = min(current_start_rowid + self.batch_size - 1, max_rowid)

                src_cursor.execute(f'SELECT rowid, * FROM {table_name} WHERE rowid BETWEEN ? AND ?', (current_start_rowid, current_end_rowid))
                rows = src_cursor.fetchall()

                if rows:
                    mem_cursor.execute(f'SELECT COUNT(*) FROM {staging_table}')
                    pre_count: int = mem_cursor.fetchone().__getitem__(0)

                    placeholders: str = ','.join(['?'] * len(rows.__getitem__(0)))
                    mem_cursor.executemany(f'INSERT INTO {staging_table} VALUES ({placeholders})', rows)

                    mem_cursor.execute(f'SELECT COUNT(*) FROM {staging_table}')
                    post_count: int = mem_cursor.fetchone().__getitem__(0)

                    inserted_in_batch: int = post_count - pre_count
                    if not (inserted_in_batch == len(rows)):
                        src_conn.close()
                        mem_conn.close()
                        self._cleanup_temp_dir(temp_dir)
                        raise CommandError(f'Data insertion mismatch! Expected {len(rows)} inserts, but only {inserted_in_batch} committed.')

                    total_copied += inserted_in_batch

                current_start_rowid += self.batch_size
                time.sleep(self.batch_sleep)

        finally:
            src_conn.close()

        if 0 < total_copied:
            mem_cursor.execute(create_schema_sql)

            mem_cursor.execute(f"SELECT name FROM pragma_table_info('{table_name}')")
            col_list: str = ','.join([row.__getitem__(0) for row in mem_cursor.fetchall()])

            mem_cursor.execute(f'INSERT INTO {table_name} (rowid, {col_list}) SELECT rowid, {col_list} FROM {staging_table}')
            mem_cursor.execute(f'DROP TABLE {staging_table}')

            for index_sql in index_sqls:
                mem_cursor.execute(index_sql)

        if 0 < total_copied:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            mem_cursor.execute(f"VACUUM main INTO '{str(target_path.resolve(strict=False))}'")
            self.stdout.write(self.style.SUCCESS(f'Successfully streamed database archive to: {target_path}'))
        else:
            self.stdout.write('No rows matched within the live boundaries; target archive empty.')

        mem_conn.close()
