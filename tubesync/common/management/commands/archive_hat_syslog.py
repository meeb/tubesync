import tempfile
import sqlite3
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError

class Command(BaseCommand):
    help = 'Copies a number of rows from a source SQLite syslog database into a new file inside a temp folder at an arbitrary destination.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--vacuum',
            action='store_true',
            default=False,
            help='Optimize the database after all the rows were added',
        )

        parser.add_argument('source_db_path', type=str, help='Path to the source SQLite database file')

        parser.add_argument('destination_path', type=str, help='Arbitrary destination directory path for the new directory')

        parser.add_argument('limit', type=int, help='The maximum number of rows to copy from the source table')

    def handle(self, *args, **options):
        source_path = Path(options['source_db_path']).resolve(strict=False)
        destination_path = Path(options['destination_path']).resolve(strict=False)
        row_limit = options['limit']

        # Validation checks
        if row_limit < 200:
            raise CommandError('The row limit argument must be a positive integer greater than 200.')

        if not source_path.exists():
            raise CommandError(f'Source database file not found at: {source_path}')

        if not destination_path.exists():
            raise CommandError(f'Destination path is not a valid directory or does not exist: {destination_path}')

        # Create the unique temporary directory INSIDE the specified arbitrary destination path
        temp_dir = tempfile.mkdtemp(prefix='tmp_', dir=destination_path)
        target_path = Path(temp_dir) / source_path.name

        self.stdout.write(self.style.SUCCESS(f'Created temp directory: {temp_dir}'))
        self.stdout.write(f'Target database file: {target_path}')

        conn = None
        try:
            # Establish connection to the new target database file
            conn = sqlite3.connect(target_path)
            cursor = conn.cursor()

            # Set auto_vacuum on the completely blank database file
            cursor.execute('PRAGMA auto_vacuum = FULL;')

            # Attach the old source database strictly as read-only using URI mode
            cursor.execute(f"ATTACH DATABASE 'file:{source_path}?mode=ro' AS old;")

            # Extract the original schema dynamically
            cursor.execute("SELECT sql FROM old.sqlite_schema WHERE tbl_name='log' AND type='table';")
            schema_result = cursor.fetchone()
            if not schema_result or not schema_result[0]:
                raise CommandError('Could not find a table named "log" in the source database.')

            original_sql = schema_result[0]

            # Inject 'rowid INTEGER PRIMARY KEY' to align the physical rowid slots
            modified_sql = original_sql.replace('(', '(rowid INTEGER PRIMARY KEY, ', 1)
            cursor.execute(modified_sql)

            # Extract and duplicate any indexes associated with the table
            cursor.execute("SELECT sql FROM old.sqlite_schema WHERE tbl_name='log' AND type='index';")
            for index_row in cursor.fetchall():
                if index_row and index_row[0]:
                    cursor.execute(index_row[0])

            # Gather the rest of the column names cleanly, filtering out rowid metadata structures
            cursor.execute("PRAGMA table_info('log');")
            cols = [row[1] for row in cursor.fetchall() if row[1] != 'rowid']
            col_string = ', '.join(cols)

            # Execute the data transfer with stable rowids mapping preserved using the dynamic limit
            self.stdout.write(f'Transferring the newest {row_limit:,} log records...')
            insert_query = f'INSERT INTO main.log (rowid, {col_string}) SELECT rowid, {col_string} FROM old.log ORDER BY rowid DESC LIMIT {row_limit};'
            cursor.execute(insert_query)

            conn.commit()
            if options['vacuum']:
                self.stdout.write('Optimizing database structure...')
                cursor.execute('VACUUM;')

            self.stdout.write(self.style.SUCCESS(f'Successfully archived database to: {target_path}'))

        except sqlite3.Error as e:
            # Clean up the partial artifacts if the processing sequence breaks
            if target_path.exists():
                target_path.unlink()
            raise CommandError(f'SQLite error occurred during migration: {e}')

        finally:
            if conn:
                conn.close()
            try:
                Path(temp_dir).rmdir()
            except OSError:
                pass
