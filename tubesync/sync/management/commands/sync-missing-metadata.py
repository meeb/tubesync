from shutil import copyfile
from django.core.management.base import BaseCommand, CommandError # noqa
from django.db.models import Q
from common.logger import log
from sync.models import Source, Media
from sync.utils import write_text_file


class Command(BaseCommand):

    help = 'Syncs missing metadata (such as nfo files) if source settings are updated'

    def handle(self, *args, **options):
        log.info('Syncing missing metadata...')
        sources = Source.objects.filter(Q(copy_thumbnails=True) | Q(write_nfo=True))
        for source in sources.order_by('name'):
            log.info(f'Finding media for source: {source}')
            for item in Media.objects.filter(source=source, downloaded=True):
                log.info(f'Checking media for missing metadata: {source} / {item}')
                thumbpath = item.thumbpath
                if not thumbpath.is_file():
                    if item.thumb:
                        log.info(f'Copying missing thumbnail from: {item.thumb.path} '
                                 f'to: {thumbpath}')
                        copyfile(item.thumb.path, thumbpath)
                    else:
                        log.error(f'Tried to copy missing thumbnail for {item} but '
                                  f'the thumbnail has not been downloaded')
                nfopath = item.nfopath
                if not nfopath.is_file():
                    log.info(f'Writing missing NFO file: {nfopath}')
                    write_text_file(nfopath, item.nfoxml)
        log.info('Done')
