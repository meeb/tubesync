from django import db
from io import BytesIO, TextIOWrapper
from pprint import pp
from django.utils.translation import gettext_lazy
from django.core.management import call_command
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
sql_statements = db.connection.ops.prepare_sql_script

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

def _mk_wrapper():
    return TextIOWrapper(
        BytesIO(),
        line_buffering=True,
        write_through=True,
    )

def check_migration_status(migration_str, /):
    needle = 'No planned migration operations.'
    wrap_stderr, wrap_stdout = _mk_wrapper(), _mk_wrapper()
    call_command(
        'migrate', '-v', '3', '--plan', 'sync',
        migration_str,
        stderr=wrap_stderr,
        stdout=wrap_stdout,
    )
    wrap_stderr.seek(0, 0)
    stderr_lines = wrap_stderr.readlines()
    wrap_stdout.seek(0, 0)
    stdout_lines = wrap_stdout.readlines()
    return (
        bool([ line.decode() for line in stdout_lines if needle in line ]),
        stderr_lines,
        stdout_lines,
    )


class Command(BaseCommand):

    help = _('Fixes MariaDB database issues')
    requires_migrations_checks = False

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
        return 'uuid' in [
            f.name for f in fields if 'varchar' == f.data_type and 32 == f.display_size
        ]

    def _column_type(self, table_str, column_str='uuid', /):
        fields = self._get_fields(table_str)
        found = [
            f'{f.data_type}({f.display_size})' for f in fields if column_str.lower() == f.name.lower()
        ]
        if not found:
            return str()
        return found[0]

    def handle(self, *args, **options):
        if 'mysql' != db.connection.vendor:
            raise CommandError(
                _('An invalid database vendor is configured')
                + f': {db.connection.vendor}'
            )

        db_is_mariadb = (
            hasattr(db.connection, 'mysql_is_mariadb') and
            db.connection.is_usable() and
            db.connection.mysql_is_mariadb
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
            uuid_column_type_str = 'uuid(36)'
            both_tables = (
                self._using_char_for_uuid('sync_source') and
                self._using_char_for_uuid('sync_media')
            )
            if not both_tables:
                if uuid_column_type_str == self._column_type('sync_source', 'uuid').lower():
                    log.info('The source table is already using a native UUID column.')
                elif uuid_column_type_str == self._column_type('sync_media', 'uuid').lower():
                    log.info('The media table is already using a native UUID column.')
                elif uuid_column_type_str == self._column_type('sync_media', 'source_id').lower():
                    log.info('The media table is already using a native UUID column.')
                else:
                    raise CommandError(_(
                        'The database is not in an appropriate state to switch to '
                        'native UUID columns. Manual intervention is required.'
                    ))
            else:
                self.stdout.write('Time to update the columns!')

                schema = db.connection.schema_editor(collect_sql=True)
                quote_name = schema.quote_name
                media_table_str = quote_name('sync_media')
                source_table_str = quote_name('sync_source')
                fk_name_str = quote_name('sync_media_source_id_36827e1d_fk_sync_source_uuid')
                source_id_column_str = quote_name('source_id')
                uuid_column_str = quote_name('uuid')
                uuid_type_str = 'uuid'.upper()
                remove_fk = schema.sql_delete_fk % dict(
                    table=media_table_str,
                    name=fk_name_str,
                )
                add_fk = schema.sql_create_fk % dict(
                    table=media_table_str,
                    name=fk_name_str,
                    column=source_id_column_str,
                    to_table=source_table_str,
                    to_column=uuid_column_str,
                    deferrable='',
                )

                schema.execute(remove_fk, None)
                schema.execute(
                    schema.sql_alter_column % dict(
                        table=media_table_str,
                        changes=schema.sql_alter_column_not_null % dict(
                            type=uuid_type_str,
                            column=uuid_column_str,
                        ),
                    ),
                    None,
                )
                schema.execute(
                    schema.sql_alter_column % dict(
                        table=media_table_str,
                        changes=schema.sql_alter_column_not_null % dict(
                            type=uuid_type_str,
                            column=source_id_column_str,
                        ),
                    ),
                    None,
                )
                schema.execute(
                    schema.sql_alter_column % dict(
                        table=source_table_str,
                        changes=schema.sql_alter_column_not_null % dict(
                            type=uuid_type_str,
                            column=uuid_column_str,
                        ),
                    ),
                    None,
                )
                schema.execute(add_fk, None)

                pp( schema.collected_sql )

        if table_names:
            pp( check_migration_status( '0029', ) )
            pp( check_migration_status(
                '0030_alter_source_source_vcodec',
            ))
            pp( check_migration_status(
                '0031_squashed_metadata_metadataformat',
            ))
            pp( check_migration_status( '0032_metadata_transfer', ))
            if check_migration_status('0032_metadata_transfer')[0]:
                raise CommandError(_(
                    'Deleting tables that are in use is not safe!'
                ))
            
            self.stdout.write('Tables to delete:')
            pp( table_names )

        # All done
        log.info('Done')
