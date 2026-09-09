import importlib
from django.conf import settings
from django.db import DatabaseError


def patch_ensure_connection():
    for config in settings.DATABASES.values():
        db_engine = config['ENGINE']

        # Only patch for MariaDB/MySQL
        if 'django.db.backends.mysql' != db_engine:
            continue

        module = importlib.import_module(f'{db_engine}.base')

        def ensure_connection(self):
            with self.wrap_database_errors:
                self.close_if_unusable_or_obsolete()
                if not (self.connection is None or self.is_usable()):
                    try:
                        with self.wrap_database_errors:
                            self.validate_thread_sharing()
                            raw_cursor = self.create_cursor()
                            with self.make_cursor(raw_cursor) as cursor:
                                cursor.execute('SELECT 1;')
                    except DatabaseError:
                        self.close()

            super().ensure_connection()

        module.DatabaseWrapper.ensure_connection = ensure_connection
