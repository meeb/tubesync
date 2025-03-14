import os
import uuid
from django.utils.translation import gettext_lazy as _
from django.core.management.base import BaseCommand, CommandError
from django.db.models import signals
from common.logger import log
from sync.models import Source, Media, MediaServer
from sync.signals import media_post_delete
from sync.tasks import rescan_media_server


class Command(BaseCommand):

    help = ('Deletes a source by UUID')

    def add_arguments(self, parser):
        parser.add_argument('--source', action='store', required=True, help='Source UUID')

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
        source.deactivate()
        # Delete the source, triggering pre-delete signals for each media item
        log.info(f'Found source with UUID "{source.uuid}" with name '
                 f'"{source.name}" and deleting it, this may take some time!')
        source.delete()
        # Update any media servers
        for mediaserver in MediaServer.objects.all():
            log.info(f'Scheduling media server updates')
            verbose_name = _('Request media server rescan for "{}"')
            rescan_media_server(
                str(mediaserver.pk),
                priority=0,
                schedule=30,
                verbose_name=verbose_name.format(mediaserver),
                remove_existing_tasks=True
            )
        # All done
        log.info('Done')
