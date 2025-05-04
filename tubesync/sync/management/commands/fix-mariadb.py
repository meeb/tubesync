from django import db
from pprint import pp
from django.utils.translation import gettext_lazy
from django.core.management.base import BaseCommand, CommandError
from common.logger import log


def _(arg_str):
    return str(gettext_lazy(arg_str))

def SQLTable(arg_table):
    if not isinstance(arg_table, str):
        raise TypeError(type(arg_table))
    tables = db.connection.introspection.table_names(include_views=False)
    valid_table_name = (
        arg_table.startswith('sync_') and
        arg_table in tables
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
            self.stdout.write('Time to update the columns!')

        self.stdout.write('Tables to delete:')
        pp( table_names )

        # All done
        log.info('Done')
