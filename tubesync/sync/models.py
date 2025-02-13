import os
import uuid
import json
import re
from xml.etree import ElementTree
from collections import OrderedDict
from datetime import datetime, timedelta
from pathlib import Path
from django.conf import settings
from django.db import models
from django.core.exceptions import SuspiciousOperation
from django.core.files.storage import FileSystemStorage
from django.core.validators import RegexValidator
from django.utils.text import slugify
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from common.logger import log
from common.errors import NoFormatException
from common.utils import clean_filename, clean_emoji
from .youtube import (get_media_info as get_youtube_media_info,
                      download_media as download_youtube_media,
                      get_channel_image_info as get_youtube_channel_image_info)
from .utils import (seconds_to_timestr, parse_media_format, filter_response,
                    write_text_file, mkdir_p, directory_and_stem, glob_quote)
from .matching import (get_best_combined_format, get_best_audio_format,
                       get_best_video_format)
from .mediaservers import PlexMediaServer
from .fields import CommaSepChoiceField
from .choices import (V, CapChoices, Fallback, FileExtension,
                        FilterSeconds, IndexSchedule, MediaServerType,
                        MediaState, SourceResolution, SourceResolutionInteger,
                        SponsorBlock_Category, YouTube_AudioCodec,
                        YouTube_SourceType, YouTube_VideoCodec)

media_file_storage = FileSystemStorage(location=str(settings.DOWNLOAD_ROOT), base_url='/media-data/')
_srctype_dict = lambda n: dict(zip( YouTube_SourceType.values, (n,) * len(YouTube_SourceType.values) ))

class Source(models.Model):
    '''
        A Source is a source of media. Currently, this is either a YouTube channel
        or a YouTube playlist.
    '''

    SOURCE_RESOLUTION_1080P = V(SourceResolution.VIDEO_1080P)
    SOURCE_RESOLUTION_AUDIO = V(SourceResolution.AUDIO)
    SOURCE_RESOLUTIONS = SourceResolution.values

    SOURCE_VCODEC_VP9 = V(YouTube_VideoCodec.VP9)
    SOURCE_VCODEC_CHOICES = list(reversed(YouTube_VideoCodec.choices[1:]))

    SOURCE_ACODEC_OPUS = V(YouTube_AudioCodec.OPUS)
    SOURCE_ACODEC_CHOICES = list(reversed(YouTube_AudioCodec.choices))

    FALLBACK_FAIL = V(Fallback.FAIL)
    FALLBACK_NEXT_BEST = V(Fallback.NEXT_BEST)
    FALLBACK_NEXT_BEST_HD = V(Fallback.NEXT_BEST_HD)

    sponsorblock_categories = CommaSepChoiceField(
        _(''),
        max_length=128,
        possible_choices=SponsorBlock_Category.choices,
        all_choice='all',
        allow_all=True,
        all_label='(All Categories)',
        default='all',
        help_text=_('Select the SponsorBlock categories that you wish to be removed from downloaded videos.')
    )
    embed_metadata = models.BooleanField(
        _('embed metadata'),
        default=False,
        help_text=_('Embed metadata from source into file')
    )
    embed_thumbnail = models.BooleanField(
        _('embed thumbnail'),
        default=False,
        help_text=_('Embed thumbnail into the file')
    )
    enable_sponsorblock = models.BooleanField(
        _('enable sponsorblock'),
        default=True,
        help_text=_('Use SponsorBlock?')
    )

    # Fontawesome icons used for the source on the front end
    ICONS = _srctype_dict('<i class="fab fa-youtube"></i>')

    # Format to use to display a URL for the source
    URLS = dict(zip(
        YouTube_SourceType.values,
        (
            'https://www.youtube.com/c/{key}',
            'https://www.youtube.com/channel/{key}',
            'https://www.youtube.com/playlist?list={key}',
        ),
    ))

    # Format used to create indexable URLs
    INDEX_URLS = dict(zip(
        YouTube_SourceType.values,
        (
            'https://www.youtube.com/c/{key}/{type}',
            'https://www.youtube.com/channel/{key}/{type}',
            'https://www.youtube.com/playlist?list={key}',
        ),
    ))

    # Callback functions to get a list of media from the source
    INDEXERS = _srctype_dict(get_youtube_media_info)

    # Field names to find the media ID used as the key when storing media
    KEY_FIELD = _srctype_dict('id')

    uuid = models.UUIDField(
        _('uuid'),
        primary_key=True,
        editable=False,
        default=uuid.uuid4,
        help_text=_('UUID of the source')
    )
    created = models.DateTimeField(
        _('created'),
        auto_now_add=True,
        db_index=True,
        help_text=_('Date and time the source was created')
    )
    last_crawl = models.DateTimeField(
        _('last crawl'),
        db_index=True,
        null=True,
        blank=True,
        help_text=_('Date and time the source was last crawled')
    )
    source_type = models.CharField(
        _('source type'),
        max_length=1,
        db_index=True,
        choices=YouTube_SourceType.choices,
        default=YouTube_SourceType.CHANNEL,
        help_text=_('Source type')
    )
    key = models.CharField(
        _('key'),
        max_length=100,
        db_index=True,
        unique=True,
        help_text=_('Source key, such as exact YouTube channel name or playlist ID')
    )
    name = models.CharField(
        _('name'),
        max_length=100,
        db_index=True,
        unique=True,
        help_text=_('Friendly name for the source, used locally in TubeSync only')
    )
    directory = models.CharField(
        _('directory'),
        max_length=100,
        db_index=True,
        unique=True,
        help_text=_('Directory name to save the media into')
    )
    media_format = models.CharField(
        _('media format'),
        max_length=200,
        default=settings.MEDIA_FORMATSTR_DEFAULT,
        help_text=_('File format to use for saving files, detailed options at bottom of page.')
    )
    index_schedule = models.IntegerField(
        _('index schedule'),
        choices=IndexSchedule.choices,
        db_index=True,
        default=IndexSchedule.EVERY_24_HOURS,
        help_text=_('Schedule of how often to index the source for new media')
    )
    download_media = models.BooleanField(
        _('download media'),
        default=True,
        help_text=_('Download media from this source, if not selected the source will only be indexed')
    )
    index_videos = models.BooleanField(
        _('index videos'),
        default=True,
        help_text=_('Index video media from this source')
    )
    index_streams = models.BooleanField(
        _('index streams'),
        default=False,
        help_text=_('Index live stream media from this source')
    )
    download_cap = models.IntegerField(
        _('download cap'),
        choices=CapChoices.choices,
        default=CapChoices.CAP_NOCAP,
        help_text=_('Do not download media older than this capped date')
    )
    delete_old_media = models.BooleanField(
        _('delete old media'),
        default=False,
        help_text=_('Delete old media after "days to keep" days?')
    )
    days_to_keep = models.PositiveSmallIntegerField(
        _('days to keep'),
        default=14,
        help_text=_('If "delete old media" is ticked, the number of days after which '
                    'to automatically delete media')
    )
    filter_text = models.CharField(
        _('filter string'),
        max_length=200,
        default='',
        blank=True,
        help_text=_('Regex compatible filter string for video titles')
    )
    filter_text_invert = models.BooleanField(
        _("invert filter text matching"),
        default=False,
        help_text="Invert filter string regex match, skip any matching titles when selected",
    )
    filter_seconds = models.PositiveIntegerField(
                _('filter seconds'),
                blank=True,
                null=True,
                help_text=_('Filter Media based on Min/Max duration. Leave blank or 0 to disable filtering')
    )
    filter_seconds_min = models.BooleanField(
        _('filter seconds min/max'),
        choices=FilterSeconds.choices,
        default=V(FilterSeconds.MIN),
        help_text=_('When Filter Seconds is > 0, do we skip on minimum (video shorter than limit) or maximum (video '
                    'greater than maximum) video duration')
    )
    delete_removed_media = models.BooleanField(
        _('delete removed media'),
        default=False,
        help_text=_('Delete media that is no longer on this playlist')
    )
    delete_files_on_disk = models.BooleanField(
        _('delete files on disk'),
        default=False,
        help_text=_('Delete files on disk when they are removed from TubeSync')
    )
    source_resolution = models.CharField(
        _('source resolution'),
        max_length=8,
        db_index=True,
        choices=SourceResolution.choices,
        default=SourceResolution.VIDEO_1080P,
        help_text=_('Source resolution, desired video resolution to download')
    )
    source_vcodec = models.CharField(
        _('source video codec'),
        max_length=8,
        db_index=True,
        choices=SOURCE_VCODEC_CHOICES,
        default=YouTube_VideoCodec.VP9,
        help_text=_('Source video codec, desired video encoding format to download (ignored if "resolution" is audio only)')
    )
    source_acodec = models.CharField(
        _('source audio codec'),
        max_length=8,
        db_index=True,
        choices=SOURCE_ACODEC_CHOICES,
        default=YouTube_AudioCodec.OPUS,
        help_text=_('Source audio codec, desired audio encoding format to download')
    )
    prefer_60fps = models.BooleanField(
        _('prefer 60fps'),
        default=True,
        help_text=_('Where possible, prefer 60fps media for this source')
    )
    prefer_hdr = models.BooleanField(
        _('prefer hdr'),
        default=False,
        help_text=_('Where possible, prefer HDR media for this source')
    )
    fallback = models.CharField(
        _('fallback'),
        max_length=1,
        db_index=True,
        choices=Fallback.choices,
        default=Fallback.NEXT_BEST_HD,
        help_text=_('What do do when media in your source resolution and codecs is not available')
    )
    copy_channel_images = models.BooleanField(
        _('copy channel images'),
        default=False,
        help_text=_('Copy channel banner and avatar. These may be detected and used by some media servers')
    )
    copy_thumbnails = models.BooleanField(
        _('copy thumbnails'),
        default=False,
        help_text=_('Copy thumbnails with the media, these may be detected and used by some media servers')
    )
    write_nfo = models.BooleanField(
        _('write nfo'),
        default=False,
        help_text=_('Write an NFO file in XML with the media info, these may be detected and used by some media servers')
    )
    write_json = models.BooleanField(
        _('write json'),
        default=False,
        help_text=_('Write a JSON file with the media info, these may be detected and used by some media servers')
    )
    has_failed = models.BooleanField(
        _('has failed'),
        default=False,
        help_text=_('Source has failed to index media')
    )

    write_subtitles = models.BooleanField(
        _('write subtitles'),
        default=False,
        help_text=_('Download video subtitles')
    )

    auto_subtitles = models.BooleanField(
        _('accept auto-generated subs'),
        default=False,
        help_text=_('Accept auto-generated subtitles')
    )
    sub_langs = models.CharField(
        _('subs langs'),
        max_length=30,
        default='en',
        help_text=_('List of subtitles langs to download, comma-separated. Example: en,fr or all,-fr,-live_chat'),
        validators=[
            RegexValidator(
                regex=r"^(\-?[\_\.a-zA-Z-]+(,|$))+",
                message=_('Subtitle langs must be a comma-separated list of langs. example: en,fr or all,-fr,-live_chat')
            )
        ]
    )

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _('Source')
        verbose_name_plural = _('Sources')

    @property
    def icon(self):
        return self.ICONS.get(self.source_type)

    @property
    def slugname(self):
        replaced = self.name.replace('_', '-').replace('&', 'and').replace('+', 'and')
        return slugify(replaced)[:80]

    @property
    def is_audio(self):
        return self.source_resolution == SourceResolution.AUDIO.value

    @property
    def is_playlist(self):
        return self.source_type == YouTube_SourceType.PLAYLIST.value

    @property
    def is_video(self):
        return not self.is_audio

    @property
    def download_cap_date(self):
        delta = self.download_cap
        if delta > 0:
            return timezone.now() - timedelta(seconds=delta)
        else:
            return False

    @property
    def days_to_keep_date(self):
        delta = self.days_to_keep
        if delta > 0:
            return timezone.now() - timedelta(days=delta)
        else:
            return False

    @property
    def extension(self):
        '''
            The extension is also used by youtube-dl to set the output container. As
            it is possible to quite easily pick combinations of codecs and containers
            which are invalid (e.g. OPUS audio in an MP4 container) just set this for
            people. All video is set to mkv containers, audio-only is set to m4a or ogg
            depending on audio codec.
        '''
        if self.is_audio:
            if self.source_acodec == V(YouTube_AudioCodec.MP4A):
                return V(FileExtension.M4A)
            elif self.source_acodec == V(YouTube_AudioCodec.OPUS):
                return V(FileExtension.OGG)
            else:
                raise ValueError('Unable to choose audio extension, uknown acodec')
        else:
            return V(FileExtension.MKV)

    @classmethod
    def create_url(obj, source_type, key):
        url = obj.URLS.get(source_type)
        return url.format(key=key)

    @classmethod
    def create_index_url(obj, source_type, key, type):
        url = obj.INDEX_URLS.get(source_type)
        return url.format(key=key, type=type)

    @property
    def url(self):
        return Source.create_url(self.source_type, self.key)

    def get_index_url(self, type):
        return Source.create_index_url(self.source_type, self.key, type)

    @property
    def format_summary(self):
        if self.is_audio:
            vc = 'none'
        else:
            vc = self.source_vcodec
        ac = self.source_acodec
        f = ' 60FPS' if self.is_video and self.prefer_60fps else ''
        h = ' HDR' if self.is_video and self.prefer_hdr else ''
        return f'{self.source_resolution} (video:{vc}, audio:{ac}){f}{h}'.strip()

    @property
    def directory_path(self):
        download_dir = Path(media_file_storage.location)
        return download_dir / self.type_directory_path

    @property
    def type_directory_path(self):
        if settings.SOURCE_DOWNLOAD_DIRECTORY_PREFIX:
            if self.is_audio:
                return Path(settings.DOWNLOAD_AUDIO_DIR) / self.directory
            else:
                return Path(settings.DOWNLOAD_VIDEO_DIR) / self.directory
        else:
            return Path(self.directory)

    def make_directory(self):
        return os.makedirs(self.directory_path, exist_ok=True)

    @property
    def get_image_url(self):
        if self.is_playlist:
            raise SuspiciousOperation('This source is a playlist so it doesn\'t have thumbnail.')

        return get_youtube_channel_image_info(self.url)


    def directory_exists(self):
        return (os.path.isdir(self.directory_path) and
                os.access(self.directory_path, os.W_OK))

    @property
    def key_field(self):
        return self.KEY_FIELD.get(self.source_type, '')

    @property
    def source_resolution_height(self):
        return SourceResolutionInteger.get(self.source_resolution, 0)

    @property
    def can_fallback(self):
        return self.fallback != self.FALLBACK_FAIL

    @property
    def example_media_format_dict(self):
        '''
            Populates a dict with real-ish and some placeholder data for media name
            format strings. Used for example filenames and media_format validation.
        '''
        fmt = []
        if self.source_resolution:
            fmt.append(self.source_resolution)
        if self.source_vcodec:
            fmt.append(self.source_vcodec.lower())
        if self.source_acodec:
            fmt.append(self.source_acodec.lower())
        if self.prefer_60fps:
            fmt.append('60fps')
        if self.prefer_hdr:
            fmt.append('hdr')
        now = timezone.now()
        return {
            'yyyymmdd': now.strftime('%Y%m%d'),
            'yyyy_mm_dd': now.strftime('%Y-%m-%d'),
            'yyyy': now.strftime('%Y'),
            'mm': now.strftime('%m'),
            'dd': now.strftime('%d'),
            'source': self.slugname,
            'source_full': self.name,
            'uploader': 'Some Channel Name',
            'title': 'some-media-title-name',
            'title_full': 'Some Media Title Name',
            'key': 'SoMeUnIqUiD',
            'format': '-'.join(fmt),
            'playlist_title': 'Some Playlist Title',
            'video_order': '01',
            'ext': self.extension,
            'resolution': self.source_resolution if self.source_resolution else '',
            'height': '720' if self.source_resolution else '',
            'width': '1280' if self.source_resolution else '',
            'vcodec': self.source_vcodec.lower() if self.source_vcodec else '',
            'acodec': self.source_acodec.lower(),
            'fps': '24' if self.source_resolution else '',
            'hdr': 'hdr' if self.source_resolution else ''
        }

    def get_example_media_format(self):
        try:
            return self.media_format.format(**self.example_media_format_dict)
        except Exception as e:
            return ''

    def is_regex_match(self, media_item_title):
        if not self.filter_text:
            return True
        return bool(re.search(self.filter_text, media_item_title))

    def get_index(self, type):
        indexer = self.INDEXERS.get(self.source_type, None)
        if not callable(indexer):
            raise Exception(f'Source type f"{self.source_type}" has no indexer')
        response = indexer(self.get_index_url(type=type))
        if not isinstance(response, dict):
            return []
        entries = response.get('entries', []) 
        return entries

    def index_media(self):
        '''
            Index the media source returning a list of media metadata as dicts.
        '''
        entries = list()
        if self.index_videos:
            entries += self.get_index('videos')
        # Playlists do something different that I have yet to figure out
        if not self.is_playlist:
            if self.index_streams:
                entries += self.get_index('streams')

        if settings.MAX_ENTRIES_PROCESSING:
            entries = entries[:settings.MAX_ENTRIES_PROCESSING]
        return entries

def get_media_thumb_path(instance, filename):
    fileid = str(instance.uuid)
    filename = f'{fileid.lower()}.jpg'
    prefix = fileid[:2]
    return Path('thumbs') / prefix / filename


def get_media_file_path(instance, filename):
    return instance.filepath


class Media(models.Model):
    '''
        Media is a single piece of media, such as a single YouTube video linked to a
        Source.
    '''

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
        help_text=_('Source the media belongs to')
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
        # Trigger an update of derived fields from metadata
        if self.metadata:
            self.title = self.metadata_title[:200]
            self.duration = self.metadata_duration
        if update_fields is not None and "metadata" in update_fields:
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
            if self.downloaded_format != V(SourceResolution.AUDIO):
                vcodec = self.downloaded_video_codec.lower()
                fmt.append(vcodec)
            acodec = self.downloaded_audio_codec.lower()
            fmt.append(acodec)
            if self.downloaded_format != V(SourceResolution.AUDIO):
                fps = str(self.downloaded_fps)
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
            resolution = vformat['format'].lower()
            fmt.append(resolution)
            vcodec = vformat['vcodec'].lower()
            fmt.append(vcodec)
        if aformat:
            acodec = aformat['acodec'].lower()
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
        return self.metadata is not None


    @property
    def reduce_data(self):
        try:
            from common.logger import log
            from common.utils import json_serial

            old_mdl = len(self.metadata or "")
            data = json.loads(self.metadata or "{}")
            compact_json = json.dumps(data, separators=(',', ':'), default=json_serial)

            filtered_data = filter_response(data, True)
            filtered_json = json.dumps(filtered_data, separators=(',', ':'), default=json_serial)
        except Exception as e:
            log.exception('reduce_data: %s', e)
        else:
            # log the results of filtering / compacting on metadata size
            new_mdl = len(compact_json)
            if old_mdl > new_mdl:
                delta = old_mdl - new_mdl
                log.info(f'{self.key}: metadata compacted by {delta:,} characters ({old_mdl:,} -> {new_mdl:,})')
            new_mdl = len(filtered_json)
            if old_mdl > new_mdl:
                delta = old_mdl - new_mdl
                log.info(f'{self.key}: metadata reduced by {delta:,} characters ({old_mdl:,} -> {new_mdl:,})')
                if getattr(settings, 'SHRINK_OLD_MEDIA_METADATA', False):
                    self.metadata = filtered_json


    @property
    def loaded_metadata(self):
        if getattr(settings, 'SHRINK_OLD_MEDIA_METADATA', False):
            self.reduce_data
        try:
            data = json.loads(self.metadata)
            if not isinstance(data, dict):
                return {}
            return data
        except Exception as e:
            return {}

    @property
    def url(self):
        url = self.URLS.get(self.source.source_type, '')
        return url.format(key=self.key)

    @property
    def description(self):
        field = self.get_metadata_field('description')
        return self.loaded_metadata.get(field, '').strip()

    @property
    def metadata_title(self):
        field = self.get_metadata_field('title')
        return self.loaded_metadata.get(field, '').strip()

    @property
    def slugtitle(self):
        replaced = self.title.replace('_', '-').replace('&', 'and').replace('+', 'and')
        return slugify(replaced)[:80]

    @property
    def thumbnail(self):
        field = self.get_metadata_field('thumbnail')
        return self.loaded_metadata.get(field, '').strip()

    @property
    def name(self):
        title = self.title
        return title if title else self.key

    @property
    def upload_date(self):
        field = self.get_metadata_field('upload_date')
        try:
            upload_date_str = self.loaded_metadata.get(field, '').strip()
        except (AttributeError, ValueError) as e:
            return None
        try:
            return datetime.strptime(upload_date_str, '%Y%m%d')
        except (AttributeError, ValueError) as e:
            return None

    @property
    def metadata_duration(self):
        field = self.get_metadata_field('duration')
        duration = self.loaded_metadata.get(field, 0)
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
        field = self.get_metadata_field('categories')
        return self.loaded_metadata.get(field, [])

    @property
    def rating(self):
        field = self.get_metadata_field('rating')
        return self.loaded_metadata.get(field, 0)

    @property
    def votes(self):
        field = self.get_metadata_field('upvotes')
        upvotes = self.loaded_metadata.get(field, 0)
        if not isinstance(upvotes, int):
            upvotes = 0
        field = self.get_metadata_field('downvotes')
        downvotes = self.loaded_metadata.get(field, 0)
        if not isinstance(downvotes, int):
            downvotes = 0
        return upvotes + downvotes

    @property
    def age_limit(self):
        field = self.get_metadata_field('age_limit')
        return self.loaded_metadata.get(field, 0)

    @property
    def uploader(self):
        field = self.get_metadata_field('uploader')
        return self.loaded_metadata.get(field, '')

    @property
    def formats(self):
        field = self.get_metadata_field('formats')
        return self.loaded_metadata.get(field, [])

    @property
    def playlist_title(self):
        field = self.get_metadata_field('playlist_title')
        return self.loaded_metadata.get(field, '')

    @property
    def filename(self):
        # Create a suitable filename from the source media_format
        media_format = str(self.source.media_format)
        media_details = self.format_dict
        return media_format.format(**media_details)

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
            if acodec == V(YouTube_AudioCodec.MP4A):
                return "audio/mp4"
            elif acodec == V(YouTube_AudioCodec.OPUS):
                return "audio/opus"
            else:
                # fall-fall-back.
                return 'audio/ogg'
        vcodec = vcodec.upper()
        if vcodec == V(YouTube_VideoCodec.AVC1):
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
        title = nfo.makeelement('title', {})
        title.text = clean_emoji(self.title)
        title.tail = '\n  '
        nfo.append(title)
        # showtitle = source name
        showtitle = nfo.makeelement('showtitle', {})
        showtitle.text = clean_emoji(str(self.source.name).strip())
        showtitle.tail = '\n  '
        nfo.append(showtitle)
        # season = upload date year
        season = nfo.makeelement('season', {})
        if self.source.is_playlist:
            # If it's a playlist, set season to 1
            season.text = '1'
        else:
            # If it's not a playlist, set season to upload date year
            season.text = str(self.upload_date.year) if self.upload_date else ''
        season.tail = '\n  '
        nfo.append(season)
        # episode = number of video in the year
        episode = nfo.makeelement('episode', {})
        episode.text = self.get_episode_str()
        episode.tail = '\n  '
        nfo.append(episode)
        # ratings = media metadata youtube rating
        value = nfo.makeelement('value', {})
        value.text = str(self.rating)
        value.tail = '\n      '
        votes = nfo.makeelement('votes', {})
        votes.text = str(self.votes)
        votes.tail = '\n    '
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
        plot = nfo.makeelement('plot', {})
        plot.text = clean_emoji(str(self.description).strip())
        plot.tail = '\n  '
        nfo.append(plot)
        # thumb = local path to media thumbnail
        thumb = nfo.makeelement('thumb', {})
        thumb.text = self.thumbname if self.source.copy_thumbnails else ''
        thumb.tail = '\n  '
        nfo.append(thumb)
        # mpaa = media metadata age requirement
        mpaa = nfo.makeelement('mpaa', {})
        mpaa.text = str(self.age_limit)
        mpaa.tail = '\n  '
        if self.age_limit and self.age_limit > 0:
            nfo.append(mpaa)
        # runtime = media metadata duration in seconds
        runtime = nfo.makeelement('runtime', {})
        runtime.text = str(self.duration)
        runtime.tail = '\n  '
        nfo.append(runtime)
        # id = media key
        idn = nfo.makeelement('id', {})
        idn.text = str(self.key).strip()
        idn.tail = '\n  '
        nfo.append(idn)
        # uniqueid = media key
        uniqueid_attrs = OrderedDict()
        uniqueid_attrs['type'] = 'youtube'
        uniqueid_attrs['default'] = 'True'
        uniqueid = nfo.makeelement('uniqueid', uniqueid_attrs)
        uniqueid.text = str(self.key).strip()
        uniqueid.tail = '\n  '
        nfo.append(uniqueid)
        # studio = media metadata uploader
        studio = nfo.makeelement('studio', {})
        studio.text = clean_emoji(str(self.uploader).strip())
        studio.tail = '\n  '
        nfo.append(studio)
        # aired = media metadata uploaded date
        aired = nfo.makeelement('aired', {})
        upload_date = self.upload_date
        aired.text = upload_date.strftime('%Y-%m-%d') if upload_date else ''
        aired.tail = '\n  '
        nfo.append(aired)
        # dateadded = date and time media was created in tubesync
        dateadded = nfo.makeelement('dateadded', {})
        dateadded.text = self.created.strftime('%Y-%m-%d %H:%M:%S')
        dateadded.tail = '\n  '
        nfo.append(dateadded)
        # genre = any media metadata categories if they exist
        for category_str in self.categories:
            genre = nfo.makeelement('genre', {})
            genre.text = str(category_str).strip()
            genre.tail = '\n  '
            nfo.append(genre)
        nfo[-1].tail = '\n'
        # Return XML tree as a prettified string
        return ElementTree.tostring(nfo, encoding='utf8', method='xml').decode('utf8')

    def get_download_state(self, task=None):
        if self.downloaded:
            return V(MediaState.DOWNLOADED)
        if task:
            if task.locked_by_pid_running():
                return V(MediaState.DOWNLOADING)
            elif task.has_error():
                return V(MediaState.ERROR)
            else:
                return V(MediaState.SCHEDULED)
        if self.skip:
            return V(MediaState.SKIPPED)
        if not self.source.download_media:
            return V(MediaState.DISABLED_AT_SOURCE)
        return V(MediaState.UNKNOWN)

    def get_download_state_icon(self, task=None):
        state = self.get_download_state(task)
        return self.STATE_ICONS.get(state, self.STATE_ICONS[V(MediaState.UNKNOWN)])

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
            sorted_media = Media.objects.filter(source=self.source)
        else:
            self_year = self.upload_date.year if self.upload_date else self.created.year
            filtered_media = Media.objects.filter(source=self.source, published__year=self_year)
            filtered_media = [m for m in filtered_media if m.upload_date is not None]
            sorted_media = sorted(filtered_media, key=lambda x: (x.upload_date, x.key))
        position_counter = 1
        for media in sorted_media:
            if media == self:
                return position_counter
            position_counter += 1

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
                media_format = str(self.source.media_format)
                top_dir_path = Path(self.source.directory_path)
                if '{key}' in media_format:
                    fuzzy_paths = list(top_dir_path.rglob('*' + glob_quote(str(self.key)) + '*'))
                    log.info(f'Collected {len(fuzzy_paths)} fuzzy paths for: {self!s}')

                if new_video_path.exists():
                    new_video_path = new_video_path.resolve(strict=True)

                    # update the media_file in the db
                    self.media_file.name = str(new_video_path.relative_to(self.media_file.storage.location))
                    self.save()
                    log.info(f'Updated "media_file" in the database for: {self!s}')

                    (new_prefix_path, new_stem) = directory_and_stem(new_video_path)

                    # move and change names to match stem
                    for other_path in other_paths:
                        old_file_str = other_path.name
                        new_file_str = new_stem + old_file_str[len(old_stem):]
                        new_file_path = Path(new_prefix_path / new_file_str)
                        log.debug(f'Considering replace for: {self!s}\n\t{other_path!s}\n\t{new_file_path!s}')
                        # it should exist, but check anyway 
                        if other_path.exists():
                            log.debug(f'{self!s}: {other_path!s} => {new_file_path!s}')
                            other_path.replace(new_file_path)

                    for fuzzy_path in fuzzy_paths:
                        (fuzzy_prefix_path, fuzzy_stem) = directory_and_stem(fuzzy_path)
                        old_file_str = fuzzy_path.name
                        new_file_str = new_stem + old_file_str[len(fuzzy_stem):]
                        new_file_path = Path(new_prefix_path / new_file_str)
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
                    try:
                        while parent_dir.is_dir():
                            parent_dir.rmdir()
                            log.info(f'Removed empty directory: {parent_dir!s}')
                            parent_dir = parent_dir.parent
                    except OSError as e:
                        pass


class MediaServer(models.Model):
    '''
        A remote media server, such as a Plex server.
    '''

    ICONS = {
        V(MediaServerType.PLEX): '<i class="fas fa-server"></i>',
    }
    HANDLERS = {
        V(MediaServerType.PLEX): PlexMediaServer,
    }

    server_type = models.CharField(
        _('server type'),
        max_length=1,
        db_index=True,
        choices=MediaServerType.choices,
        default=MediaServerType.PLEX,
        help_text=_('Server type')
    )
    host = models.CharField(
        _('host'),
        db_index=True,
        max_length=200,
        help_text=_('Hostname or IP address of the media server')
    )
    port = models.PositiveIntegerField(
        _('port'),
        db_index=True,
        help_text=_('Port number of the media server')
    )
    use_https = models.BooleanField(
        _('use https'),
        default=True,
        help_text=_('Connect to the media server over HTTPS')
    )
    verify_https = models.BooleanField(
        _('verify https'),
        default=False,
        help_text=_('If connecting over HTTPS, verify the SSL certificate is valid')
    )
    options = models.TextField(
        _('options'),
        blank=True,
        null=True,
        help_text=_('JSON encoded options for the media server')
    )

    def __str__(self):
        return f'{self.get_server_type_display()} server at {self.url}'

    class Meta:
        verbose_name = _('Media Server')
        verbose_name_plural = _('Media Servers')
        unique_together = (
            ('host', 'port'),
        )

    @property
    def url(self):
        scheme = 'https' if self.use_https else 'http'
        return f'{scheme}://{self.host.strip()}:{self.port}'

    @property
    def icon(self):
        return self.ICONS.get(self.server_type)

    @property
    def handler(self):
        handler_class = self.HANDLERS.get(self.server_type)
        return handler_class(self)

    @property
    def loaded_options(self):
        try:
            return json.loads(self.options)
        except Exception as e:
            return {}

    def validate(self):
        return self.handler.validate()

    def update(self):
        return self.handler.update()

    def get_help_html(self):
        return self.handler.HELP
