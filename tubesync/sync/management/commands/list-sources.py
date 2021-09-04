import os
from django.core.management.base import BaseCommand, CommandError
from common.logger import log
from sync.models import Source, Media, MediaServer


class Command(BaseCommand):

    help = ('Lists sources')

    def handle(self, *args, **options):
        log.info('Listing sources...')
        for source in Source.objects.all():
            log.info(f' - {source.uuid}: {source.name}')
        log.info('Done')
