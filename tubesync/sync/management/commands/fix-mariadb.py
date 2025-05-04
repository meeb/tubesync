from django import db
from django.utils.translation import gettext_lazy as _
from django.core.management.base import BaseCommand, CommandError
from common.logger import log


class Command(BaseCommand):

    help = _('Fixes MariaDB database issues')
    requires_migrations_checks = True

    def add_arguments(self, parser):
        parser.add_argument(
            '--uuid-columns',
            action='store_true',
            required=False,
            help=_('Switch to the native UUID column type'),
        )
        parser.add_argument(
            '--delete-table',
            action='store',
            required=False,
            help=_('Table name'),
        )

    def handle(self, *args, **options):
        if 'mysql' != db.connection.vendor:
            raise CommandError(
                _('An invalid database vendor is configured')
                f': {db.connection.vendor}'
            )
        if not db.connection.mysql_is_mariadb():
            raise CommandError(_('Not conbected to a MariaDB database server.'))

        uuid_columns = options.get('uuid-columns', False)
        table_name_str = options.get('delete-table', '')

        # All done
        log.info('Done')
