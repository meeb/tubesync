from django.core.management.base import BaseCommand
from common.utils import django_queryset_generator as qs_gen
from sync.models import Media, Metadata


from common.logger import log


class Command(BaseCommand):

    help = 'Resets all media item metadata'

    def handle(self, *args, **options):
        log.info('Resettings all media metadata...')
        # Delete all metadata
        Metadata.objects.all().delete()
        # Trigger the save signal on each media item
        for media in qs_gen(Media.objects.filter(metadata__isnull=False)):
            media.metadata_clear(save=True)
        log.info('Done')
