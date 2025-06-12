import os
import uuid
import json
from collections import OrderedDict
from copy import deepcopy
from datetime import datetime, timedelta, timezone as tz
from pathlib import Path
from xml.etree import ElementTree
from django.conf import settings
from django.db import models
from django.core.exceptions import ObjectDoesNotExist
from django.db.transaction import atomic
from django.utils.text import slugify
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from common.logger import log
from common.errors import NoFormatException
from common.json import JSONEncoder
from common.utils import (
    clean_filename, clean_emoji, directory_and_stem,
    glob_quote, mkdir_p, multi_key_sort, seconds_to_timestr,
)
from ..youtube import (
    get_media_info as get_youtube_media_info,
    download_media as download_youtube_media,
)
from ..utils import (
    filter_response, parse_media_format, write_text_file,
)
from ..matching import (
    get_best_combined_format,
    get_best_audio_format, get_best_video_format,
)
from ..choices import (
    Val, Fallback, MediaState, SourceResolution,
    YouTube_AudioCodec, YouTube_VideoCodec,
)
from ._migrations import (
    media_file_storage, get_media_thumb_path, get_media_file_path,
)
from ._private import _srctype_dict, _nfo_element
from .media__tasks import (
    copy_thumbnail, download_checklist, download_finished,
    wait_for_premiere, write_nfo_file,
)
from .source import Source


class Media(models.Model):
    '''
        Media is a single piece of media, such as a single YouTube video linked to a
        Source.
    '''

    # Used to convert seconds to datetime
    posix_epoch = datetime(1970, 1, 1, tzinfo=tz.utc)

    # Format to use to display a URL for the media
    URLS = _srctype_dict('https://www.youtube.com/watch?v={key}')

    # Callback functions to get a list of media from the source
    INDEXERS = _srctype_dict(get_youtube_media_info)

    # Maps standardised names to names used in source metdata
    _same_name = lambda n, k=None: {k or n: _srctype_dict(n) }
    METADATA_FIELDS = {
        **(_same_name('upload_date')),
        **(_same_name('timestamp')),
        **(_same_name('title')),
        **(_same_name('fulltitle')),
        **(_same_name('description')),
        **(_same_name('duration')),
        **(_same_name('formats')),
        **(_same_name('categories')),
        **(_same_name('average_rating', 'rating')),
        **(_same_name('age_limit')),
        **(_same_name('uploader')),
        **(_same_name('like_count', 'upvotes')),
        **(_same_name('dislike_count', 'downvotes')),
        **(_same_name('playlist_title')),
    }

    STATE_ICONS = dict(zip(
        MediaState.values,
        (
            '<i class="far fa-question-circle" title="Unknown download state"></i>',
            '<i class="far fa-clock" title="Scheduled to download"></i>',
            '<i class="fas fa-download" title="Downloading now"></i>',
            '<i class="far fa-check-circle" title="Downloaded"></i>',
            '<i class="fas fa-exclamation-circle" title="Skipped"></i>',
            '<i class="fas fa-stop-circle" title="Media downloading disabled at source"></i>',
            '<i class="fas fa-exclamation-triangle" title="Error downloading"></i>',
        )
    ))

    uuid = models.UUIDField(
        _('uuid'),
        primary_key=True,
        editable=False,
        default=uuid.uuid4,
        help_text=_('UUID of the media')
    )
    created = models.DateTimeField(
        _('created'),
        auto_now_add=True,
        db_index=True,
        help_text=_('Date and time the media was created')
    )
    source = models.ForeignKey(
        Source,
        on_delete=models.CASCADE,
        related_name='media_source',
        help_text=_('Source the media belongs to'),
    )
    published = models.DateTimeField(
        _('published'),
        db_index=True,
        null=True,
        blank=True,
        help_text=_('Date and time the media was published on the source')
    )
    key = models.CharField(
        _('key'),
        max_length=100,
        db_index=True,
        help_text=_('Media key, such as exact YouTube video ID')
    )
    thumb = models.ImageField(
        _('thumb'),
        upload_to=get_media_thumb_path,
        max_length=200,
        blank=True,
        null=True,
        width_field='thumb_width',
        height_field='thumb_height',
        help_text=_('Thumbnail')
    )
    thumb_width = models.PositiveSmallIntegerField(
        _('thumb width'),
        blank=True,
        null=True,
        help_text=_('Width (X) of the thumbnail')
    )
    thumb_height = models.PositiveSmallIntegerField(
        _('thumb height'),
        blank=True,
        null=True,
        help_text=_('Height (Y) of the thumbnail')
    )
    metadata = models.TextField(
        _('metadata'),
        blank=True,
        null=True,
        help_text=_('JSON encoded metadata for the media')
    )
    can_download = models.BooleanField(
        _('can download'),
        db_index=True,
        default=False,
        help_text=_('Media has a matching format and can be downloaded')
    )
    media_file = models.FileField(
        _('media file'),
        upload_to=get_media_file_path,
        max_length=255,
        blank=True,
        null=True,
        storage=media_file_storage,
        help_text=_('Media file')
    )
    skip = models.BooleanField(
        _('skip'),
        db_index=True,
        default=False,
        help_text=_('INTERNAL FLAG - Media will be skipped and not downloaded')
    )
    manual_skip = models.BooleanField(
        _('manual_skip'),
        db_index=True,
        default=False,
        help_text=_('Media marked as "skipped", won\'t be downloaded')
    )
    downloaded = models.BooleanField(
        _('downloaded'),
        db_index=True,
        default=False,
        help_text=_('Media has been downloaded')
    )
    download_date = models.DateTimeField(
        _('download date'),
        db_index=True,
        blank=True,
        null=True,
        help_text=_('Date and time the download completed')
    )
    downloaded_format = models.CharField(
        _('downloaded format'),
        max_length=30,
        blank=True,
        null=True,
        help_text=_('Video format (resolution) of the downloaded media')
    )
    downloaded_height = models.PositiveIntegerField(
        _('downloaded height'),
        blank=True,
        null=True,
        help_text=_('Height in pixels of the downloaded media')
    )
    downloaded_width = models.PositiveIntegerField(
        _('downloaded width'),
        blank=True,
        null=True,
        help_text=_('Width in pixels of the downloaded media')
    )
    downloaded_audio_codec = models.CharField(
        _('downloaded audio codec'),
        max_length=30,
        blank=True,
        null=True,
        help_text=_('Audio codec of the downloaded media')
    )
    downloaded_video_codec = models.CharField(
        _('downloaded video codec'),
        max_length=30,
        blank=True,
        null=True,
        help_text=_('Video codec of the downloaded media')
    )
    downloaded_container = models.CharField(
        _('downloaded container format'),
        max_length=30,
        blank=True,
        null=True,
        help_text=_('Container format of the downloaded media')
    )
    downloaded_fps = models.PositiveSmallIntegerField(
        _('downloaded fps'),
        blank=True,
        null=True,
        help_text=_('FPS of the downloaded media')
    )
    downloaded_hdr = models.BooleanField(
        _('downloaded hdr'),
        default=False,
        help_text=_('Downloaded media has HDR')
    )
    downloaded_filesize = models.PositiveBigIntegerField(
        _('downloaded filesize'),
        db_index=True,
        blank=True,
        null=True,
        help_text=_('Size of the downloaded media in bytes')
    )
    duration = models.PositiveIntegerField(
        _('duration'),
        blank=True,
        null=True,
        help_text=_('Duration of media in seconds')
    )
    title = models.CharField(
        _('title'),
        max_length=200,
        blank=True,
        null=False,
        default='',
        help_text=_('Video title')
    )

    def __str__(self):
        return self.key

    class Meta:
        verbose_name = _('Media')
        verbose_name_plural = _('Media')
        unique_together = (
            ('source', 'key'),
        )

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
        setattr(self, '_cached_metadata_dict', None)
        # Correct the path after a source is renamed
        if self.created and self.downloaded and not self.media_file_exists:
            fp_list = list((self.filepath,))
            if self.media_file:
                # Try the new computed directory + the file base name from the database
                fp_list.append(self.filepath.parent / Path(self.media_file.path).name)
            for filepath in fp_list:
                if filepath.exists():
                    self.media_file.name = str(
                        filepath.relative_to(
                            self.media_file.storage.location
                        )
                    )
                    self.skip = False
                    if update_fields is not None:
                        update_fields = {'media_file', 'skip'}.union(update_fields)

        # Trigger an update of derived fields from metadata
        update_md = (
            self.has_metadata and
            (
                update_fields is None or
                'metadata' in update_fields
            )
        )
        if update_md:
            self.title = self.metadata_title[:200] or self.title
            self.duration = self.metadata_duration or self.duration
            setattr(self, '_cached_metadata_dict', None)
            if update_fields is not None:
                # If only some fields are being updated, make sure we update title and duration if metadata changes
                update_fields = {"title", "duration"}.union(update_fields)

        super().save(
            force_insert=force_insert,
            force_update=force_update,
            using=using,
            update_fields=update_fields,)

    def get_metadata_field(self, field):
        fields = self.METADATA_FIELDS.get(field, {})
        return fields.get(self.source.source_type, field)

    def get_metadata_first_value(self, iterable, default=None, /, *, arg_dict=None):
        '''
            fetch the first key with a value from metadata
        '''

        if arg_dict is None:
            arg_dict = self.loaded_metadata
        assert isinstance(arg_dict, dict), type(arg_dict)
        # str is an iterable of characters
        # we do not want to look for each character!
        if isinstance(iterable, str):
            iterable = (iterable,)
        for key in tuple(iterable):
            # reminder: unmapped fields return the key itself
            field = self.get_metadata_field(key)
            value = arg_dict.get(field)
            # value can be None because:
            #   - None was stored at the key
            #   - the key was not in the dictionary
            # either way, we don't want those values
            if value is None:
                continue
            if isinstance(value, str):
                return value.strip()
            return value
        return default

    def iter_formats(self):
        for fmt in self.formats:
            yield parse_media_format(fmt)

    def get_best_combined_format(self):
        return get_best_combined_format(self)

    def get_best_audio_format(self):
        return get_best_audio_format(self)

    def get_best_video_format(self):
        return get_best_video_format(self)

    def get_format_str(self):
        '''
            Returns a youtube-dl compatible format string for the best matches
            combination of source requirements and available audio and video formats.
            Returns boolean False if there is no valid downloadable combo.
        '''
        if self.source.is_audio:
            audio_match, audio_format = self.get_best_audio_format()
            if audio_format:
                return str(audio_format)
            else:
                return False
        else:
            combined_match, combined_format = self.get_best_combined_format()
            if combined_format:
                return str(combined_format)
            else:
                audio_match, audio_format = self.get_best_audio_format()
                video_match, video_format = self.get_best_video_format()
                if audio_format and video_format:
                    return f'{video_format}+{audio_format}'
                else:
                    # last resort: any combined format
                    fallback_hd_cutoff = getattr(settings, 'VIDEO_HEIGHT_IS_HD', 500)

                    for fmt in reversed(list(self.iter_formats())):
                        select_fmt = (
                            fmt.get('id') and
                            fmt.get('acodec') and
                            fmt.get('vcodec') and
                            self.source.can_fallback and
                            (
                                (self.source.fallback == Val(Fallback.NEXT_BEST)) or
                                (
                                    self.source.fallback == Val(Fallback.NEXT_BEST_HD) and
                                    (fmt.get('height') or 0) >= fallback_hd_cutoff
                                )
                            )
                        )
                        if select_fmt:
                            return str(fmt.get('id'))
                    return False
        return False

    def get_display_format(self, format_str):
        '''
            Returns a tuple used in the format component of the output filename. This
            is the format(s) found by matching. Examples:
                # Audio and video streams
                ('1080p', 'vp9', 'opus')
                # Audio only stream
                ('opus',)
                # Audio and video streams with additional flags
                ('720p', 'avc1', 'mp4a', '60fps', 'hdr')  
        '''
        fmt = []
        resolution = ''
        vcodec = ''
        acodec = ''
        height = '0'
        width = '0'
        fps = ''
        hdr = ''
        # If the download has completed use existing values
        if self.downloaded:
            # Check if there's any stored meta data at all
            if (not self.downloaded_video_codec and \
                not self.downloaded_audio_codec):
                # Marked as downloaded but no metadata, imported?
                return {
                    'resolution': resolution,
                    'height': height,
                    'width': width,
                    'vcodec': vcodec,
                    'acodec': acodec,
                    'fps': fps,
                    'hdr': hdr,
                    'format': tuple(fmt),
                }
            if self.downloaded_format:
                resolution = self.downloaded_format.lower()
            elif self.downloaded_height:
                resolution = f'{self.downloaded_height}p'
            if resolution:
                fmt.append(resolution)
            if self.downloaded_format != Val(SourceResolution.AUDIO):
                vcodec = self.downloaded_video_codec.lower()
            if vcodec:
                fmt.append(vcodec)
            acodec = self.downloaded_audio_codec.lower()
            if acodec:
                fmt.append(acodec)
            if self.downloaded_format != Val(SourceResolution.AUDIO):
                fps = str(self.downloaded_fps)
                if fps:
                    fmt.append(f'{fps}fps')
                if self.downloaded_hdr:
                    hdr = 'hdr'
                    fmt.append(hdr)
                height = str(self.downloaded_height)
                width = str(self.downloaded_width)
            return {
                'resolution': resolution,
                'height': height,
                'width': width,
                'vcodec': vcodec,
                'acodec': acodec,
                'fps': fps,
                'hdr': hdr,
                'format': tuple(fmt),
            }
        # Otherwise, calculate from matched format codes
        vformat = None
        aformat = None
        if format_str and '+' in format_str:
            # Seperate audio and video streams
            vformat_code, aformat_code = format_str.split('+')
            vformat = self.get_format_by_code(vformat_code)
            aformat = self.get_format_by_code(aformat_code)
        else:
            # Combined stream or audio only
            cformat = self.get_format_by_code(format_str)
            aformat = cformat
            if cformat and cformat['vcodec']:
                # Combined
                vformat = cformat
        if vformat:
            if vformat['format']:
                resolution = vformat['format'].lower()
            else:
                resolution = f"{vformat['height']}p"
            if resolution:
                fmt.append(resolution)
            vcodec = vformat['vcodec'].lower()
            if vcodec:
                fmt.append(vcodec)
        if aformat:
            acodec = aformat['acodec'].lower()
            if acodec:
                fmt.append(acodec)
        if vformat:
            if vformat['is_60fps']:
                fps = '60fps'
                fmt.append(fps)
            if vformat['is_hdr']:
                hdr = 'hdr'
                fmt.append(hdr)
            height = str(vformat['height'])
            width = str(vformat['width'])
        return {
            'resolution': resolution,
            'height': height,
            'width': width,
            'vcodec': vcodec,
            'acodec': acodec,
            'fps': fps,
            'hdr': hdr,
            'format': tuple(fmt),
        }

    def get_format_by_code(self, format_code):
        '''
            Matches a format code, such as '22', to a processed format dict.
        '''
        for fmt in self.iter_formats():
            if format_code == fmt['id']:
                return fmt
        return False

    @property
    def format_dict(self):
        '''
            Returns a dict matching the media_format key requirements for this item
            of media.
        '''
        format_str = self.get_format_str()
        display_format = self.get_display_format(format_str)
        dateobj = self.upload_date if self.upload_date else self.created
        return {
            'yyyymmdd': dateobj.strftime('%Y%m%d'),
            'yyyy_mm_dd': dateobj.strftime('%Y-%m-%d'),
            'yyyy': dateobj.strftime('%Y'),
            'mm': dateobj.strftime('%m'),
            'dd': dateobj.strftime('%d'),
            'source': self.source.slugname,
            'source_full': clean_filename(self.source.name),
            'title': self.slugtitle,
            'title_full': clean_filename(self.title),
            'key': self.key,
            'format': '-'.join(display_format['format']),
            'playlist_title': self.playlist_title,
            'video_order': self.get_episode_str(True),
            'ext': self.source.extension,
            'resolution': display_format['resolution'],
            'height': display_format['height'],
            'width': display_format['width'],
            'vcodec': display_format['vcodec'],
            'acodec': display_format['acodec'],
            'fps': display_format['fps'],
            'hdr': display_format['hdr'],
            'uploader': self.uploader,
        }


    @property
    def has_metadata(self):
        result = self.metadata is not None
        if not result:
            return False
        value = self.get_metadata_first_value(('id', 'display_id', 'channel_id', 'uploader_id',))
        return value is not None


    def metadata_clear(self, /, *, save=False):
        self.metadata = None
        setattr(self, '_cached_metadata_dict', None)
        if save:
            self.save()


    def metadata_dumps(self, arg_dict=dict()):
        fallback = dict()
        try:
            fallback.update(self.new_metadata.with_formats)
        except ObjectDoesNotExist:
            pass
        data = arg_dict or fallback
        return json.dumps(data, separators=(',', ':'), cls=JSONEncoder)


    def metadata_loads(self, arg_str='{}'):
        data = json.loads(arg_str) or self.loaded_metadata
        return data


    @atomic(durable=False)
    def ingest_metadata(self, data):
        assert isinstance(data, dict), type(data)
        site = self.get_metadata_first_value(
            'extractor_key',
            'Youtube',
            arg_dict=data,
        )
        md_model = self._meta.fields_map.get('new_metadata').related_model
        md, created = md_model.objects.filter(
            source__isnull=True,
        ).get_or_create(
            media=self,
            site=site,
            key=self.key,
        )
        setattr(self, '_cached_metadata_dict', None)
        return md.ingest_metadata(data)


    def save_to_metadata(self, key, value, /):
        data = self.loaded_metadata
        using_new_metadata = self.get_metadata_first_value(
            ('migrated', '_using_table',),
            False,
            arg_dict=data,
        )
        data[key] = value
        self.ingest_metadata(data)
        if not using_new_metadata:
            epoch = self.get_metadata_first_value('epoch', arg_dict=data)
            migrated = dict(migrated=True, epoch=epoch)
            migrated['_using_table'] = True
            self.metadata = self.metadata_dumps(arg_dict=migrated)
            self.save()
        from common.logger import log
        log.debug(f'Saved to metadata: {self.key} / {self.uuid}: {key=}: {value}')


    @property
    def reduce_data(self):
        now = timezone.now()
        try:
            data = json.loads(self.metadata or "{}")
            if '_reduce_data_ran_at' in data.keys():
                total_seconds = data['_reduce_data_ran_at']
                assert isinstance(total_seconds, int), type(total_seconds)
                ran_at = self.ts_to_dt(total_seconds)
                if (now - ran_at) < timedelta(hours=1):
                    return data

            compact_json = self.metadata_dumps(arg_dict=data)

            filtered_data = filter_response(data, True)
            filtered_data['_reduce_data_ran_at'] = round((now - self.posix_epoch).total_seconds())
            filtered_json = self.metadata_dumps(arg_dict=filtered_data)
        except Exception as e:
            from common.logger import log
            log.exception('reduce_data: %s', e)
        else:
            from common.logger import log
            # log the results of filtering / compacting on metadata size
            new_mdl = len(compact_json)
            old_mdl = len(self.metadata or "")
            if old_mdl > new_mdl:
                delta = old_mdl - new_mdl
                log.info(f'{self.key}: metadata compacted by {delta:,} characters ({old_mdl:,} -> {new_mdl:,})')
            new_mdl = len(filtered_json)
            if old_mdl > new_mdl:
                delta = old_mdl - new_mdl
                log.info(f'{self.key}: metadata reduced by {delta:,} characters ({old_mdl:,} -> {new_mdl:,})')
                if getattr(settings, 'SHRINK_OLD_MEDIA_METADATA', False):
                    self.metadata = filtered_json
                    return filtered_data
            return data


    @property
    def loaded_metadata(self):
        cached = getattr(self, '_cached_metadata_dict', None)
        if cached:
            return deepcopy(cached)
        data = None
        if getattr(settings, 'SHRINK_OLD_MEDIA_METADATA', False):
            data = self.reduce_data
        try:
            if not data:
                data = json.loads(self.metadata or "{}")
            if not isinstance(data, dict):
                return {}
            # if hasattr(self, 'new_metadata'):
            try:
                data.update(self.new_metadata.with_formats)
            except ObjectDoesNotExist:
                pass
            setattr(self, '_cached_metadata_dict', data)
            return data
        except Exception:
            return {}


    @property
    def refresh_formats(self):
        if not self.has_metadata:
            return
        data = self.loaded_metadata
        metadata_seconds = data.get('epoch', None)
        if not metadata_seconds:
            self.metadata_clear(save=True)
            return False

        now = timezone.now()
        attempted_key = '_refresh_formats_attempted'
        attempted_seconds = data.get(attempted_key)
        if attempted_seconds:
            # skip for recent unsuccessful refresh attempts also
            attempted_dt = self.ts_to_dt(attempted_seconds)
            if (now - attempted_dt) < timedelta(seconds=self.source.index_schedule):
                return False
        # skip for recent successful formats refresh
        refreshed_key = 'formats_epoch'
        formats_seconds = data.get(refreshed_key, metadata_seconds)
        metadata_dt = self.ts_to_dt(formats_seconds)
        if (now - metadata_dt) < timedelta(seconds=self.source.index_schedule):
            return False

        last_attempt = round((now - self.posix_epoch).total_seconds())
        self.save_to_metadata(attempted_key, last_attempt)
        self.skip = False
        metadata = self.index_metadata()
        if self.skip:
            return False

        response = metadata
        if getattr(settings, 'SHRINK_NEW_MEDIA_METADATA', False):
            response = filter_response(metadata, True)

        # save the new list of thumbnails
        thumbnails = self.get_metadata_first_value(
            'thumbnails',
            self.get_metadata_first_value('thumbnails', []),
            arg_dict=response,
        )
        field = self.get_metadata_field('thumbnails')
        self.save_to_metadata(field, thumbnails)

        # select and save our best thumbnail url
        try:
            thumbnail = [ thumb.get('url') for thumb in multi_key_sort(
                thumbnails,
                [('preference', True,)],
            ) if thumb.get('url', '').endswith('.jpg') ][0]
        except IndexError:
            pass
        else:
            field = self.get_metadata_field('thumbnail')
            self.save_to_metadata(field, thumbnail)

        field = self.get_metadata_field('formats')
        self.save_to_metadata(field, response.get(field, []))
        self.save_to_metadata(refreshed_key, response.get('epoch', formats_seconds))
        if data.get('availability', 'public') != response.get('availability', 'public'):
            self.save_to_metadata('availability', response.get('availability', 'public'))
        return True


    @property
    def url(self):
        url = self.URLS.get(self.source.source_type, '')
        return url.format(key=self.key)

    @property
    def description(self):
        return self.get_metadata_first_value('description', '')

    @property
    def metadata_title(self):
        return self.get_metadata_first_value(('fulltitle', 'title',), '')

    def ts_to_dt(self, /, timestamp):
        try:
            timestamp_float = float(timestamp)
        except (TypeError, ValueError,) as e:
            log.warn(f'Could not compute published from timestamp for: {self.source} / {self} with "{e}"')
            pass
        else:
            return self.posix_epoch + timedelta(seconds=timestamp_float)
        return None

    @property
    def slugtitle(self):
        replaced = self.title.replace('_', '-').replace('&', 'and').replace('+', 'and')
        return slugify(replaced)[:80]

    @property
    def thumbnail(self):
        default = f'https://i.ytimg.com/vi/{self.key}/maxresdefault.jpg'
        return self.get_metadata_first_value('thumbnail', default)

    @property
    def name(self):
        title = self.title
        return title if title else self.key

    @property
    def upload_date(self):
        upload_date_str = self.get_metadata_first_value('upload_date')
        if not upload_date_str:
            return None
        try:
            return datetime.strptime(upload_date_str, '%Y%m%d')
        except (AttributeError, ValueError) as e:
            log.debug(f'Media.upload_date: {self.source} / {self}: strptime: {e}')
            pass
        return None

    @property
    def metadata_duration(self):
        duration = self.get_metadata_first_value('duration', 0)
        try:
            duration = int(duration)
        except (TypeError, ValueError):
            duration = 0
        return duration

    @property
    def duration_formatted(self):
        duration = self.duration
        if duration and duration > 0:
            return seconds_to_timestr(duration)
        return '??:??:??'

    @property
    def categories(self):
        return self.get_metadata_first_value('categories', list())

    @property
    def rating(self):
        return self.get_metadata_first_value('rating', 0)

    @property
    def votes(self):
        upvotes = self.get_metadata_first_value('upvotes', 0)
        if not isinstance(upvotes, int):
            upvotes = 0
        downvotes = self.get_metadata_first_value('downvotes', 0)
        if not isinstance(downvotes, int):
            downvotes = 0
        return upvotes + downvotes

    @property
    def age_limit(self):
        return self.get_metadata_first_value('age_limit', 0)

    @property
    def uploader(self):
        return self.get_metadata_first_value('uploader', '')

    @property
    def formats(self):
        return self.get_metadata_first_value('formats', list())

    @property
    def playlist_title(self):
        return self.get_metadata_first_value('playlist_title', '')

    @property
    def filename(self):
        # Create a suitable filename from the source media_format
        media_format = str(self.source.media_format)
        media_details = self.format_dict
        result = media_format.format(**media_details)
        return '.' + result if '/' == result[0] else result

    @property
    def directory_path(self):
        return self.filepath.parent

    @property
    def filepath(self):
        return self.source.directory_path / self.filename

    def filename_prefix(self):
        if self.downloaded and self.media_file:
            filename = self.media_file.path
        else:
            filename = self.filename
        # The returned prefix should not contain any directories.
        # So, we do not care about the different directories
        # used for filename in the cases above.
        prefix, ext = os.path.splitext(os.path.basename(filename))
        return prefix

    @property
    def thumbname(self):
        prefix = self.filename_prefix()
        return f'{prefix}.jpg'

    @property
    def thumbpath(self):
        return self.directory_path / self.thumbname

    @property
    def nfoname(self):
        prefix = self.filename_prefix()
        return f'{prefix}.nfo'

    @property
    def nfopath(self):
        return self.directory_path / self.nfoname

    @property
    def jsonname(self):
        prefix = self.filename_prefix()
        return f'{prefix}.info.json'

    @property
    def jsonpath(self):
        return self.directory_path / self.jsonname

    @property
    def thumb_file_exists(self):
        if not self.thumb:
            return False
        return os.path.exists(self.thumb.path)

    @property
    def media_file_exists(self):
        if not self.media_file:
            return False
        return os.path.exists(self.media_file.path)

    @property
    def content_type(self):
        if not self.downloaded:
            return 'video/mp4'
        vcodec = self.downloaded_video_codec
        if vcodec is None:
            acodec = self.downloaded_audio_codec
            if acodec is None:
                raise TypeError() # nothing here.
            acodec = acodec.upper()
            if acodec == Val(YouTube_AudioCodec.MP4A):
                return "audio/mp4"
            elif acodec == Val(YouTube_AudioCodec.OPUS):
                return "audio/opus"
            else:
                # fall-fall-back.
                return 'audio/ogg'
        vcodec = vcodec.upper()
        if vcodec == Val(YouTube_VideoCodec.AVC1):
            return 'video/mp4'
        else:
            return 'video/matroska'

    @property
    def nfoxml(self):
        '''
            Returns an NFO formatted (prettified) XML string.
        '''
        nfo = ElementTree.Element('episodedetails')
        nfo.text = '\n  '
        # title = media metadata title
        nfo.append(_nfo_element(nfo,
            'title', clean_emoji(self.title),
        ))
        # showtitle = source name
        nfo.append(_nfo_element(nfo,
            'showtitle', clean_emoji(str(self.source.name).strip()),
        ))
        # season = upload date year
        nfo.append(_nfo_element(nfo,
            'season',
            '1' if self.source.is_playlist else str(
                self.upload_date.year if self.upload_date else ''
            ),
        ))
        # episode = number of video in the year
        nfo.append(_nfo_element(nfo,
            'episode', self.get_episode_str(),
        ))
        # ratings = media metadata youtube rating
        value = _nfo_element(nfo, 'value', str(self.rating), indent=6)
        votes = _nfo_element(nfo, 'votes', str(self.votes), indent=4)
        rating_attrs = OrderedDict()
        rating_attrs['name'] = 'youtube'
        rating_attrs['max'] = '5'
        rating_attrs['default'] = 'true'
        rating = nfo.makeelement('rating', rating_attrs)
        rating.text = '\n      '
        rating.append(value)
        rating.append(votes)
        rating.tail = '\n  '
        ratings = nfo.makeelement('ratings', {})
        ratings.text = '\n    '
        if self.rating is not None:
            ratings.append(rating)
        ratings.tail = '\n  '
        nfo.append(ratings)
        # plot = media metadata description
        nfo.append(_nfo_element(nfo,
            'plot', clean_emoji(str(self.description).strip()),
        ))
        # thumb = local path to media thumbnail
        nfo.append(_nfo_element(nfo,
            'thumb', self.thumbname if self.source.copy_thumbnails else '',
        ))
        # mpaa = media metadata age requirement
        if self.age_limit and self.age_limit > 0:
            nfo.append(_nfo_element(nfo,
                'mpaa', str(self.age_limit),
            ))
        # runtime = media metadata duration in seconds
        nfo.append(_nfo_element(nfo,
            'runtime', str(self.duration),
        ))
        # id = media key
        nfo.append(_nfo_element(nfo,
            'id', str(self.key).strip(),
        ))
        # uniqueid = media key
        uniqueid_attrs = OrderedDict()
        uniqueid_attrs['type'] = 'youtube'
        uniqueid_attrs['default'] = 'True'
        nfo.append(_nfo_element(nfo,
            'uniqueid', str(self.key).strip(), attrs=uniqueid_attrs,
        ))
        # studio = media metadata uploader
        nfo.append(_nfo_element(nfo,
            'studio', clean_emoji(str(self.uploader).strip()),
        ))
        # aired = media metadata uploaded date
        upload_date = self.upload_date
        nfo.append(_nfo_element(nfo,
            'aired', upload_date.strftime('%Y-%m-%d') if upload_date else '',
        ))
        # dateadded = date and time media was created in tubesync
        nfo.append(_nfo_element(nfo,
            'dateadded', self.created.strftime('%Y-%m-%d %H:%M:%S'),
        ))
        # genre = any media metadata categories if they exist
        for category_str in self.categories:
            nfo.append(_nfo_element(nfo,
                'genre', str(category_str).strip(),
            ))
        nfo[-1].tail = '\n'
        # Return XML tree as a prettified string
        return ElementTree.tostring(nfo, encoding='utf8', method='xml').decode('utf8')

    def get_download_state(self, task=None):
        if self.downloaded:
            return Val(MediaState.DOWNLOADED)
        if task:
            if task.locked_by_pid_running():
                return Val(MediaState.DOWNLOADING)
            elif task.has_error():
                return Val(MediaState.ERROR)
            else:
                return Val(MediaState.SCHEDULED)
        if self.skip:
            return Val(MediaState.SKIPPED)
        if not self.source.download_media:
            return Val(MediaState.DISABLED_AT_SOURCE)
        return Val(MediaState.UNKNOWN)

    def get_download_state_icon(self, task=None):
        state = self.get_download_state(task)
        return self.STATE_ICONS.get(state, self.STATE_ICONS[Val(MediaState.UNKNOWN)])

    def download_media(self):
        format_str = self.get_format_str()
        if not format_str:
            raise NoFormatException(f'Cannot download, media "{self.pk}" ({self}) has '
                                    f'no valid format available')
        # Download the media with youtube-dl
        download_youtube_media(self.url, format_str, self.source.extension,
                               str(self.filepath), self.source.write_json,
                               self.source.sponsorblock_categories.selected_choices, self.source.embed_thumbnail,
                               self.source.embed_metadata, self.source.enable_sponsorblock,
                              self.source.write_subtitles, self.source.auto_subtitles,self.source.sub_langs )
        # Return the download paramaters
        return format_str, self.source.extension

    def index_metadata(self):
        '''
            Index the media metadata returning a dict of info.
        '''
        indexer = self.INDEXERS.get(self.source.source_type, None)
        if not callable(indexer):
            raise Exception(f'Media with source type f"{self.source.source_type}" '
                            f'has no indexer')
        response = indexer(self.url)
        no_formats_available = (
            not response or
            "formats" not in response.keys() or
            0 == len(response["formats"])
        )
        if no_formats_available:
            self.can_download = False
            self.skip = True
        return response

    def calculate_episode_number(self):
        if self.source.is_playlist:
            sorted_media = Media.objects.filter(
                source=self.source,
                metadata__isnull=False,
            ).order_by(
                'published',
                'created',
                'key',
            )
        else:
            self_year = self.created.year # unlikely to be accurate
            if self.published:
                self_year = self.published.year
            elif self.has_metadata and self.upload_date:
                self_year = self.upload_date.year
            elif self.download_date:
                # also, unlikely to be accurate
                self_year = self.download_date.year
            sorted_media = Media.objects.filter(
                source=self.source,
                metadata__isnull=False,
                published__year=self_year,
            ).order_by(
                'published',
                'created',
                'key',
            )
        for counter, media in enumerate(sorted_media, start=1):
            if media == self:
                return counter

    def get_episode_str(self, use_padding=False):
        episode_number = self.calculate_episode_number()
        if not episode_number:
            return ''

        if use_padding:
            return f'{episode_number:02}'

        return str(episode_number)

    def rename_files(self):
        if self.downloaded and self.media_file:
            old_video_path = Path(self.media_file.path)
            new_video_path = Path(get_media_file_path(self, None))
            if old_video_path == new_video_path:
                return
            if old_video_path.exists() and not new_video_path.exists():
                old_video_path = old_video_path.resolve(strict=True)

                # move video to destination
                mkdir_p(new_video_path.parent)
                log.debug(f'{self!s}: {old_video_path!s} => {new_video_path!s}')
                old_video_path.rename(new_video_path)
                log.info(f'Renamed video file for: {self!s}')

                # collect the list of files to move
                # this should not include the video we just moved
                (old_prefix_path, old_stem) = directory_and_stem(old_video_path)
                other_paths = list(old_prefix_path.glob(glob_quote(old_stem) + '*'))
                log.info(f'Collected {len(other_paths)} other paths for: {self!s}')

                # adopt orphaned files, if possible
                fuzzy_paths = list()
                media_format = str(self.source.media_format)
                top_dir_path = Path(self.source.directory_path)
                if '{key}' in media_format:
                    fuzzy_paths = list(top_dir_path.rglob('*' + glob_quote(str(self.key)) + '*'))
                    log.info(f'Collected {len(fuzzy_paths)} fuzzy paths for: {self!s}')

                if new_video_path.exists():
                    new_video_path = new_video_path.resolve(strict=True)

                    # update the media_file in the db
                    self.media_file.name = str(new_video_path.relative_to(self.media_file.storage.location))
                    self.skip = False
                    self.save(update_fields=('media_file', 'skip'))
                    log.info(f'Updated "media_file" in the database for: {self!s}')

                    (new_prefix_path, new_stem) = directory_and_stem(new_video_path)

                    # move and change names to match stem
                    for other_path in other_paths:
                        # it should exist, but check anyway
                        if not other_path.exists():
                            continue

                        old_file_str = other_path.name
                        new_file_str = new_stem + old_file_str[len(old_stem):]
                        new_file_path = Path(new_prefix_path / new_file_str)
                        if new_file_path == other_path:
                            continue
                        log.debug(f'Considering replace for: {self!s}\n\t{other_path!s}\n\t{new_file_path!s}')
                        # do not move the file we just updated in the database
                        # doing that loses track of the `Media.media_file` entirely
                        if not new_video_path.samefile(other_path):
                            log.debug(f'{self!s}: {other_path!s} => {new_file_path!s}')
                            other_path.replace(new_file_path)

                    for fuzzy_path in fuzzy_paths:
                        (fuzzy_prefix_path, fuzzy_stem) = directory_and_stem(fuzzy_path, True)
                        old_file_str = fuzzy_path.name
                        new_file_str = new_stem + old_file_str[len(fuzzy_stem):]
                        new_file_path = Path(new_prefix_path / new_file_str)
                        if new_file_path == fuzzy_path:
                            continue
                        log.debug(f'Considering rename for: {self!s}\n\t{fuzzy_path!s}\n\t{new_file_path!s}')
                        # it quite possibly was renamed already
                        if fuzzy_path.exists() and not new_file_path.exists():
                            log.debug(f'{self!s}: {fuzzy_path!s} => {new_file_path!s}')
                            fuzzy_path.rename(new_file_path)

                    # The thumbpath inside the .nfo file may have changed
                    if self.source.write_nfo and self.source.copy_thumbnails:
                        write_text_file(new_prefix_path / self.nfopath.name, self.nfoxml)
                        log.info(f'Wrote new ".nfo" file for: {self!s}')

                    # try to remove empty dirs
                    parent_dir = old_video_path.parent
                    stop_dir = self.source.directory_path
                    try:
                        while parent_dir.is_relative_to(stop_dir):
                            parent_dir.rmdir()
                            log.info(f'Removed empty directory: {parent_dir!s}')
                            parent_dir = parent_dir.parent
                    except OSError:
                        pass


# add imported functions
Media.copy_thumbnail = copy_thumbnail
Media.download_checklist = download_checklist
Media.download_finished = download_finished
Media.wait_for_premiere = wait_for_premiere
Media.write_nfo_file = write_nfo_file

