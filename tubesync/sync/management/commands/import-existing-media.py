import json
import os
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError # noqa
from common.logger import log
from common.timestamp import timestamp_to_datetime
from sync.choices import FileExtension
from sync.models import Source, Media
from sync.utils import normalize_codec


class Command(BaseCommand):

    help = ('Scans download media directories for media not yet downloaded and '
            'marks them as downloaded')
    extra_extensions = ['mp3', 'mp4', 'avi']

    def handle(self, *args, **options):
        log.info('Building directory to Source map...')
        dirmap = {}
        for s in Source.objects.all():
            dirmap[str(s.directory_path)] = s
        log.info('Scanning sources...')
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
                # import .info.json file
                info_json = Path(filepath).with_suffix('.info.json')
                if not item.has_metadata and info_json.is_file():
                    try:
                        json_dict = json.loads(info_json.read_text())
                        item.ingest_metadata(json_dict)
                    except:
                        log.exception(f'could not import: {info_json}')
                        pass
                    else:
                        epoch = item.get_metadata_first_value('epoch', arg_dict=json_dict) or None
                        if epoch:
                            item.download_date = timestamp_to_datetime(epoch)
                        item.downloaded_audio_codec = normalize_codec(
                            item.get_metadata_first_value('acodec', arg_dict=json_dict)
                        ) or None
                        item.downloaded_container = item.get_metadata_first_value('ext', arg_dict=json_dict) or None
                        item.downloaded_fps = item.get_metadata_first_value('fps', arg_dict=json_dict) or None
                        dynamic_range = item.get_metadata_first_value('dynamic_range', arg_dict=json_dict) or ''
                        format = item.get_metadata_first_value('format', arg_dict=json_dict) or ''
                        if dynamic_range:
                            item.downloaded_hdr = 'HDR' == dynamic_range.upper()
                        elif format:
                            item.downloaded_hdr = 'HDR' in format.upper()
                        item.downloaded_height = item.get_metadata_first_value('height', arg_dict=json_dict) or None
                        item.downloaded_video_codec = normalize_codec(
                            item.get_metadata_first_value('vcodec', arg_dict=json_dict)
                        ) or None
                        item.downloaded_width = item.get_metadata_first_value('width', arg_dict=json_dict) or None
                        item.duration = item.get_metadata_first_value('duration', arg_dict=json_dict) or None
                        timestamp = item.get_metadata_first_value('timestamp', arg_dict=json_dict) or None
                        if timestamp:
                            item.published = timestamp_to_datetime(timestamp)
                        item.title = item.get_metadata_first_value(('fulltitle', 'title',), '', arg_dict=json_dict) or ''
                        if item.title:
                            item.title = item.title[:200]
                # set a reasonable download date
                date = timestamp_to_datetime(Path(filepath).stat().st_mtime)
                if item.published and item.published > date:
                    date = item.published
                if item.has_metadata:
                    metadata_date = timestamp_to_datetime(item.get_metadata_first_value('epoch', 0))
                    if metadata_date and metadata_date > date:
                        date = metadata_date
                if item.download_date and item.download_date > date:
                    date = item.download_date
                item.download_date = date
                item.save()
        log.info('Done')
