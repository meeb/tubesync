from django import db
from io import BytesIO, TextIOWrapper
from django.utils.translation import gettext_lazy
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from common.logger import log


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

def check_migration_status(migration_str, /, *, needle=None):
    if needle is None:
        needle = 'No planned migration operations.'
    wrap_stderr, wrap_stdout = _mk_wrapper(), _mk_wrapper()
    try:
        call_command(
            'migrate', '-v', '3', '--plan', 'sync',
            migration_str,
            stderr=wrap_stderr,
            stdout=wrap_stdout,
        )
    except db.migrations.exceptions.NodeNotFoundError:
        return (False, None, None,)
    wrap_stderr.seek(0, 0)
    stderr_lines = wrap_stderr.readlines()
    wrap_stdout.seek(0, 0)
    stdout_lines = wrap_stdout.readlines()
    return (
        bool([ line for line in stdout_lines if needle in line ]),
        stderr_lines,
        stdout_lines,
    )

def db_columns(table_str, /):
    columns = list()
    db_gtd = db.connection.introspection.get_table_description
    with db.connection.cursor() as cursor:
        columns.extend(db_gtd(cursor, table_str))
    return columns


class Command(BaseCommand):

    help = _('Fixes MariaDB database issues')
    output_transaction = True
    requires_migrations_checks = False

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            default=False,
            help=_('Only show the SQL; do not apply it to the database'),
        )
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
            help=_('SQL table name to be deleted'),
        )

    def _using_char(self, table_str, column_str='uuid', /):
        cols = db_columns(table_str)
        char_sizes = { 32, 36, }
        char_types = { 'char', 'varchar', }
        return column_str in [
            c.name for c in cols if c.data_type in char_types and c.display_size in char_sizes
        ]

    def _column_type(self, table_str, column_str='uuid', /):
        cols = db_columns(table_str)
        found = [
            f'{c.data_type}({c.display_size})' for c in cols if column_str.lower() == c.name.lower()
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
        schema = db.connection.schema_editor(collect_sql=True)
        quote_name = schema.quote_name

        log.info('Start')


        if options['uuid_columns']:
            if 'uuid' != db.connection.data_types.get('UUIDField', ''):
                raise CommandError(_(
                    f'The {display_name} database server does not support UUID columns.'
                ))
            uuid_column_type_str = 'uuid(36)'
            both_tables = (
                self._using_char('sync_source', 'uuid') and
                self._using_char('sync_media', 'uuid')
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

                schema.execute('SET foreign_key_checks=0', None)
                #schema.execute(remove_fk, None)
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
                #schema.execute(add_fk, None)
                schema.execute('SET foreign_key_checks=1', None)


        if table_names:
            # Check that the migration is at an appropriate step
            at_30, err_30, out_30 = check_migration_status( '0030_alter_source_source_vcodec' )
            at_31, err_31, out_31 = check_migration_status( '0031_metadata_metadataformat' )
            at_31s, err_31s, out_31s = check_migration_status( '0031_squashed_metadata_metadataformat' )
            after_31, err_31a, out_31a = check_migration_status(
                '0030_alter_source_source_vcodec',
                needle='Undo Rename table for metadata to sync_media_metadata',
            )

            should_delete = (
                not (at_31s or after_31) and
                (at_30 or at_31)
            )
            if not should_delete:
                raise CommandError(_(
                    'Deleting metadata tables that are in use is not safe!'
                ))
            
            for table in table_names:
                schema.execute(
                    schema.sql_delete_table % dict(
                        table=quote_name(table),
                    ),
                    None,
                )

        if options['dry_run']:
            log.info('Done')
            return '\n'.join(schema.collected_sql)
        else:
            with db.connection.schema_editor(collect_sql=False) as schema_editor:
                for sql in schema.collected_sql:
                    schema_editor.execute(sql, None)


        # All done
        log.info('Done')
