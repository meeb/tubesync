import importlib
from django.conf import settings
from django.db.backends.utils import CursorWrapper


def patch_ensure_connection():
    for name, config in settings.DATABASES.items():
        module = importlib.import_module(config['ENGINE'] + '.base')

        def ensure_connection(self):
            if self.connection is not None:
                try:
                    with CursorWrapper(self.create_cursor(), self) as cursor:
                        cursor.execute('SELECT 1;')
                    return
                except Exception:
                    pass

            with self.wrap_database_errors:
                self.connect()

        module.DatabaseWrapper.ensure_connection = ensure_connection
