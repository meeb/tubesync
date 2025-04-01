import os
import uuid
from django.utils.translation import gettext_lazy as _
from django.core.management.base import BaseCommand, CommandError
from django.db.transaction import atomic
from common.logger import log
from sync.models import Source, Media, MediaServer
from sync.tasks import schedule_media_servers_update


class Command(BaseCommand):

    help = _('Deletes a source by UUID')

    def add_arguments(self, parser):
        parser.add_argument('--source', action='store', required=True, help=_('Source UUID'))

    def handle(self, *args, **options):
        source_uuid_str = options.get('source', '')
        try:
            source_uuid = uuid.UUID(source_uuid_str)
        except Exception as e:
            raise CommandError(f'Failed to parse source UUID: {e}')
        log.info(f'Deleting source with UUID: {source_uuid}')
        # Fetch the source by UUID
        try:
            source = Source.objects.get(uuid=source_uuid)
        except Source.DoesNotExist:
            raise CommandError(f'Source does not exist with '
                               f'UUID: {source_uuid}')
        # Reconfigure the source to not update the disk or media servers
        with atomic(durable=True):
            source.deactivate()
        # Delete the source, triggering pre-delete signals for each media item
        log.info(f'Found source with UUID "{source.uuid}" with name '
                 f'"{source.name}" and deleting it, this may take some time!')
        log.info(f'Source directory: {source.directory_path}')
        with atomic(durable=True):
            source.delete()
            schedule_media_servers_update()
        # All done
        log.info('Done')
