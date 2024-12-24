import os
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from common.logger import log
from sync.models import Source, Media


class Command(BaseCommand):

    help = ('Scans download media directories for media not yet downloaded and ',
            'marks them as downloaded')
    extra_extensions = ['mp3', 'mp4', 'avi']

    def handle(self, *args, **options):
        log.info('Building directory to Source map...')
        dirmap = {}
        for s in Source.objects.all():
            dirmap[s.directory_path] = s
        log.info(f'Scanning sources...')
        file_extensions = list(Source.EXTENSIONS) + self.extra_extensions
        for sourceroot, source in dirmap.items():
            media = list(Media.objects.filter(source=source, downloaded=False,
                                              skip=False))
            if not media:
                log.info(f'Source "{source}" has no missing media')
                continue
            log.info(f'Scanning Source "{source}" directory for media to '
                     f'import: {sourceroot}, looking for {len(media)} '
                     f'undownloaded and unskipped items')
            on_disk = []
            for (root, dirs, files) in os.walk(sourceroot):
                rootpath = Path(root)
                for filename in files:
                    filepart, ext = os.path.splitext(filename)
                    if ext.startswith('.'):
                        ext = ext[1:]
                    ext = ext.strip().lower()
                    if ext not in file_extensions:
                        continue
                    on_disk.append(str(rootpath / filename))
            filemap = {}
            for item in media:
                for filepath in on_disk:
                    if item.key in filepath:
                        # The unique item key is in the file name on disk, map it to
                        # the undownloaded media item
                        filemap[filepath] = item
                        continue
            for filepath, item in filemap.items():
                log.info(f'Matched on-disk file: {filepath} '
                         f'to media item: {item.source} / {item}')
                item.media_file.name = str(Path(filepath).relative_to(item.media_file.storage.location))
                item.downloaded = True
                item.save()
        log.info('Done')
