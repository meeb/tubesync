from django.core.management.base import BaseCommand
from sync.models import Media


from common.logger import log


class Command(BaseCommand):

    help = 'Resets all media item metadata'

    def handle(self, *args, **options):
        log.info('Resettings all media metadata...')
        # Delete all metadata
        Media.objects.update(metadata=None)
        # Trigger the save signal on each media item
        for item in Media.objects.all():
            item.save()
        log.info('Done')
