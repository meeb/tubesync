from django import db
from pprint import pp
from django.utils.translation import gettext_lazy as _
from django.core.management.base import BaseCommand, CommandError
from common.logger import log


def SQLTable(arg_table):
    assert isinstance(arg_table, str), type(arg_table)
    assert arg_table.startswith('sync_'), _('Invalid table name')
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
            metavar='TABLE',
            type=SQLTable,
            help=_('SQL table name'),
        )

    def handle(self, *args, **options):
        if 'mysql' != db.connection.vendor:
            raise CommandError(_(
                'An invalid database vendor is configured'
                f': {db.connection.vendor}'
            ))
        if not db.connection.mysql_is_mariadb():
            raise CommandError(_('Not conbected to a MariaDB database server.'))

        uuid_columns = options.get('uuid-columns')
        table_names = options.get('delete-table', list())

        if options['uuid-columns']:
            self.stdout.write('Time to update the columns!')

        pp( table_names )

        # All done
        log.info('Done')
