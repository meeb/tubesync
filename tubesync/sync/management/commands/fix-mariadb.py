from django import db
from pprint import pp
from django.utils.translation import gettext_lazy
from django.core.management.base import BaseCommand, CommandError
from common.logger import log


db_columns = db.connection.introspection.get_table_description
db_tables = db.connection.introspection.table_names
db_quote_name = db.connection.ops.quote_name
new_tables = {
    'sync_media_metadata_format',
    'sync_media_metadata',
    'sync_metadataformat',
    'sync_metadata',
}

def _(arg_str):
    return str(gettext_lazy(arg_str))

def SQLTable(arg_table):
    assert isinstance(arg_table, str), type(arg_table)
    needle = arg_table
    if needle.startswith('new__'):
        needle = arg_table[len('new__'):]
    valid_table_name = (
        needle in new_tables and
        arg_table in db_tables(include_views=False)
    )
    if not valid_table_name:
        raise ValueError(_('Invalid table name'))
    return str(arg_table)


class Command(BaseCommand):

    help = _('Fixes MariaDB database issues')
    requires_migrations_checks = True

    def add_arguments(self, parser):
        parser.add_argument(
            '--uuid-columns',
            action='store_true',
            default=False,
            help=_('Switch to the native UUID column type'),
        )
        parser.add_argument(
            '--delete-table',
            action='append',
            default=list(),
            metavar='TABLE',
            type=SQLTable,
            help=_('SQL table name'),
        )

    def _get_fields(self, table_str, /):
        columns = list()
        with db.connection.cursor() as cursor:
            columns.extend(db_columns(cursor, table_str))
        return columns

    def _using_char_for_uuid(self, table_str, /):
        fields = self._get_fields(table_str)
        return 'uuid' in [ f.name for f in fields if 'char(32)' == f.type_code ]

    def _column_type(self, table_str, column_str='uuid', /):
        fields = self._get_fields(table_str)
        return [ f.type_code for f in fields if column_str.lower() == f.name.lower() ][0]

    def handle(self, *args, **options):
        if 'mysql' != db.connection.vendor:
            raise CommandError(
                _('An invalid database vendor is configured')
                + f': {db.connection.vendor}'
            )

        db_is_mariadb = (
            hasattr(db.connection, 'mysql_is_mariadb') and
            db.connection.is_usable() and
            db.connection.mysql_is_mariadb()
        )
        if not db_is_mariadb:
            raise CommandError(_('Not conbected to a MariaDB database server.'))

        display_name = db.connection.display_name
        table_names = options.get('delete_table')

        log.info('Start')
        if options['uuid_columns']:
            if 'uuid' != db.connection.data_types.get('UUIDField', ''):
                raise CommandError(_(
                    f'The {display_name} database server does not support UUID columns.'
                ))
            both_tables = (
                self._using_char_for_uuid('sync_source') and
                self._using_char_for_uuid('sync_media')
            )
            if not both_tables:
                if 'uuid' == self._column_type('sync_source', 'uuid').lower():
                    log.notice('The source table is already using a native UUID column.')
                elif 'uuid' == self._column_type('sync_media', 'uuid').lower():
                    log.notice('The media table is already using a native UUID column.')
                elif 'uuid' == self._column_type('sync_media', 'source_id').lower():
                    log.notice('The media table is already using a native UUID column.')
                else:
                    raise CommandError(_(
                        'The database is not in an appropriate state to switch to '
                        'native UUID columns. Manual intervention is required.'
                    ))
            else:
                self.stdout.write('Time to update the columns!')

        self.stdout.write('Tables to delete:')
        pp( table_names )

        # All done
        log.info('Done')
