import re
import sys
from pathlib import Path
from common.logger import log
from common.utils import glob_quote
from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Validates and cleans up temporary playlist postprocessor_*_temp.info.json files efficiently.'

    def add_arguments(self, parser):
        parser.add_argument('playlist_id', type=str, help='The ID of the playlist')
        parser.add_argument('total_entries', type=str, help='The total expected entries count')
        parser.add_argument('fallback_downloaded', type=str, nargs='?', default='NA', 
                            help='Optional default value for downloaded entries')

    def handle(self, *args, **options):
        playlist_id = options['playlist_id']
        total_entries = options['total_entries']
        downloaded_entries = options['fallback_downloaded']

        where_dir = Path(getattr(settings, 'YOUTUBE_DL_CACHEDIR', None) or '/dev/shm')
        search_paths = {Path('/dev/shm'), where_dir}

        exact_match_regex = re.compile(
            rf'postprocessor_\[{re.escape(playlist_id)}\]_(?P<idx>\d+)_{re.escape(total_entries)}_temp\.info\.json$'
        )

        cleanup_pattern = glob_quote(f'postprocessor_[{playlist_id}]_') + '*_temp.info.json'

        for base_path in search_paths:
            playlist_folder = base_path / 'infojson' / 'playlist'
            if not playlist_folder.is_dir():
                continue

            for file_path in playlist_folder.rglob(cleanup_pattern):
                file_name = file_path.name

                match = exact_match_regex.match(file_name)
                if match:
                    downloaded_entries = match.group('idx')

                try:
                    file_path.unlink()
                except FileNotFoundError:
                    pass

        if (
            'NA' != downloaded_entries
            and 'NA' != total_entries
            and downloaded_entries != total_entries
        ):
            log.error('Validation failed: the entire playlist was not available.')
            sys.exit(1)

        log.debug('Playlist validation was completed successfully.')
        sys.exit(0)
