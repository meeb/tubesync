import uuid
from django.core.management.base import BaseCommand, CommandError
from django.db.transaction import atomic
from django.utils.translation import gettext_lazy as _
from common.logger import log
from sync.models import Source
from sync.tasks import schedule_media_servers_update


class Command(BaseCommand):

    help = 'Deletes a source by UUID'

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
        try:
            with atomic(durable=True):
                source.deactivate()
        except (Source.NotUpdated, Source.DoesNotExist):
            raise CommandError(f'Source {source_uuid} was removed by another '
                               f'process before it could be deleted')
        # Delete the source, triggering pre-delete signals for each media item
        log.info(f'Found source with UUID "{source.uuid}" with name '
                 f'"{source.name}" and deleting it, this may take some time!')
        log.info(f'Source directory: {source.directory_path}')
        with atomic(durable=True):
            deleted_count = source.delete()[0]
            # Update any media servers
            schedule_media_servers_update()
        if not deleted_count:
            log.info(f'Source {source_uuid} was already gone')
        # All done
        log.info('Done')
