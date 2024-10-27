import os
from django.core.management.base import BaseCommand
from common.logger import log
from sync.models import Source, Media
import glob
import shutil


class Command(BaseCommand):

    help = 'Updates media when the media format has changed naming/directory'

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            help="Only updates specified source"
        )

        parser.add_argument(
            "--no-rename",
            action="store_true",
            help= "Do not rename the file (only move)"
        )

        parser.add_argument(
            "--dryrun",
            action="store_true", #treats as boolean
            help="Don't make any changes, only print outputs"
        )

    def handle(self, *args, **options):
        filtered_source = options['source']
        dry_run = options['dryrun']
        no_rename = options['no_rename']
        if dry_run:
            log.info('Dry run initiated')

        if filtered_source:
            log.info(f'Searching for source: {filtered_source}')
            sources = Source.objects.filter(name=filtered_source)
        else:
            sources = Source.objects

        for source in sources.order_by('name'):
            log.info(f'Finding media for source: {source}')
            for item in Media.objects.filter(source=source, downloaded=True):
                media_path = os.path.dirname(item.media_file.path) if no_rename else item.media_file.path
                file_path = os.path.dirname(item.filepath) if no_rename else item.filepath
                if str(media_path) != str(file_path):
                    log.info(media_path)
                    log.info(file_path)
                    log.info(f'Checking media and metadata to move: {source} / {item}')
                    media_file_path, media_ext = os.path.splitext(os.path.basename(item.media_file.path))
                    search_path = os.path.join(source.directory_path, '**', media_file_path)
                    log.info(search_path)

                    if not os.path.isdir(os.path.dirname(item.filepath)):
                        os.makedirs(os.path.dirname(item.filepath))

                    if no_rename:
                        new_path = os.path.join(file_path, media_file_path)
                    else:
                        new_path = os.path.splitext(item.filepath)[0]

                    # Find and move media
                    for file in glob.glob(f'{search_path}.*', recursive=True):
                        log.info(f'Matching file found: {file}')
                        ext = "".join(file.rsplit(os.path.splitext(item.media_file.path)[0]))

                        if dry_run:
                            log.info(f'Dry Run: Moving {file} to {new_path}{ext}')
                        else:
                            log.info(f'Moving {file} to {new_path}{ext}')
                            shutil.move(file, f'{new_path}{ext}')

                    if dry_run:
                        log.info(f'Dry Run: Updating db record filepath to: {new_path}{media_ext}')
                    else:
                        log.info(f'Updating db record filepath to: {new_path}{media_ext}')
                        item.media_file.name = f'{new_path}{media_ext}'
                        item.save()
        log.info('Done')
