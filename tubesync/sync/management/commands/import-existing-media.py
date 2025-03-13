import os
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from common.logger import log
from sync.choices import FileExtension
from sync.models import Source, Media


class Command(BaseCommand):

    help = ('Scans download media directories for media not yet downloaded and ',
            'marks them as downloaded')
    extra_extensions = ['mp3', 'mp4', 'avi']

    def handle(self, *args, **options):
        log.info('Building directory to Source map...')
        dirmap = {}
        for s in Source.objects.all():
            dirmap[str(s.directory_path)] = s
        log.info(f'Scanning sources...')
        file_extensions = list(FileExtension.values) + self.extra_extensions
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
                    filepath = Path(rootpath / filename).resolve(strict=True)
                    on_disk.append(str(filepath))
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
                item.downloaded_filesize = Path(filepath).stat().st_size
                # set a reasonable download date
                date = item.metadata_published(Path(filepath).stat().st_mtime)
                if item.published and item.published > date:
                    date = item.published
                if item.has_metadata:
                    metadata_date = item.metadata_published(item.get_metadata_first_value('epoch', 0))
                    if metadata_date and metadata_date > date:
                        date = metadata_date
                if item.download_date and item.download_date > date:
                    date = item.download_date
                item.download_date = date
                item.save()
        log.info('Done')
