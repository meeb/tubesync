import os
import re
import uuid
from collections import deque as queue
from pathlib import Path
from django import db
from django.conf import settings
from django.core.exceptions import SuspiciousOperation
from django.core.validators import RegexValidator
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from ..choices import (Val,
    SponsorBlock_Category, YouTube_SourceType, IndexSchedule,
    CapChoices, Fallback, FileExtension, FilterSeconds,
    SourceResolution, SourceResolutionInteger,
    YouTube_VideoCodec, YouTube_AudioCodec,
)
from ..fields import CommaSepChoiceField
from ..youtube import (
    get_media_info as get_youtube_media_info,
    get_channel_image_info as get_youtube_channel_image_info,
)
from ._migrations import media_file_storage
from ._private import _srctype_dict


class Source(db.models.Model):
    '''
        A Source is a source of media. Currently, this is either a YouTube channel
        or a YouTube playlist.
    '''

    
    embed_metadata = db.models.BooleanField(
        _('embed metadata'),
        default=False,
        help_text=_('Embed metadata from source into file'),
    )
    embed_thumbnail = db.models.BooleanField(
        _('embed thumbnail'),
        default=False,
        help_text=_('Embed thumbnail into the file'),
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

    uuid = db.models.UUIDField(
        _('uuid'),
        primary_key=True,
        editable=False,
        default=uuid.uuid4,
        help_text=_('UUID of the source'),
    )
    created = db.models.DateTimeField(
        _('created'),
        auto_now_add=True,
        db_index=True,
        help_text=_('Date and time the source was created'),
    )
    last_crawl = db.models.DateTimeField(
        _('last crawl'),
        db_index=True,
        null=True,
        blank=True,
        help_text=_('Date and time the source was last crawled'),
    )
    source_type = db.models.CharField(
        _('source type'),
        max_length=1,
        db_index=True,
        choices=YouTube_SourceType.choices,
        default=YouTube_SourceType.CHANNEL,
        help_text=_('Source type'),
    )
    key = db.models.CharField(
        _('key'),
        max_length=100,
        db_index=True,
        unique=True,
        help_text=_('Source key, such as exact YouTube channel name or playlist ID'),
    )
    name = db.models.CharField(
        _('name'),
        max_length=100,
        db_index=True,
        unique=True,
        help_text=_('Friendly name for the source, used locally in TubeSync only'),
    )
    directory = db.models.CharField(
        _('directory'),
        max_length=100,
        db_index=True,
        unique=True,
        help_text=_('Directory name to save the media into'),
    )
    media_format = db.models.CharField(
        _('media format'),
        max_length=200,
        default=settings.MEDIA_FORMATSTR_DEFAULT,
        help_text=_('File format to use for saving files, detailed options at bottom of page.'),
    )
    target_schedule = db.models.DateTimeField(
        _('target schedule'),
        auto_now_add=True,
        db_index=True,
        help_text=_('Date and time when the task to index the source should begin'),
    )
    index_schedule = db.models.IntegerField(
        _('index schedule'),
        choices=IndexSchedule.choices,
        db_index=True,
        default=IndexSchedule.EVERY_24_HOURS,
        help_text=_('Schedule of how often to index the source for new media'),
    )
    download_media = db.models.BooleanField(
        _('download media'),
        default=True,
        help_text=_('Download media from this source, if not selected the source will only be indexed'),
    )
    index_videos = db.models.BooleanField(
        _('index videos'),
        default=True,
        help_text=_('Index video media from this source'),
    )
    index_streams = db.models.BooleanField(
        _('index streams'),
        default=False,
        help_text=_('Index live stream media from this source'),
    )
    download_cap = db.models.IntegerField(
        _('download cap'),
        choices=CapChoices.choices,
        default=CapChoices.CAP_NOCAP,
        help_text=_('Do not download media older than this capped date'),
    )
    delete_old_media = db.models.BooleanField(
        _('delete old media'),
        default=False,
        help_text=_('Delete old media after "days to keep" days?'),
    )
    days_to_keep = db.models.PositiveSmallIntegerField(
        _('days to keep'),
        default=14,
        help_text=_(
            'If "delete old media" is ticked, the number of days after which '
            'to automatically delete media'
        ),
    )
    filter_text = db.models.CharField(
        _('filter string'),
        max_length=200,
        default='',
        blank=True,
        help_text=_('Regex compatible filter string for video titles'),
    )
    filter_text_invert = db.models.BooleanField(
        _('invert filter text matching'),
        default=False,
        help_text=_('Invert filter string regex match, skip any matching titles when selected'),
    )
    filter_seconds = db.models.PositiveIntegerField(
        _('filter seconds'),
        blank=True,
        null=True,
        help_text=_('Filter Media based on Min/Max duration. Leave blank or 0 to disable filtering'),
    )
    filter_seconds_min = db.models.BooleanField(
        _('filter seconds min/max'),
        choices=FilterSeconds.choices,
        default=Val(FilterSeconds.MIN),
        help_text=_(
            'When Filter Seconds is > 0, do we skip on minimum (video shorter than limit) or maximum (video '
            'greater than maximum) video duration'
        ),
    )
    delete_removed_media = db.models.BooleanField(
        _('delete removed media'),
        default=False,
        help_text=_('Delete media that is no longer on this playlist'),
    )
    delete_files_on_disk = db.models.BooleanField(
        _('delete files on disk'),
        default=False,
        help_text=_('Delete files on disk when they are removed from TubeSync'),
    )
    source_resolution = db.models.CharField(
        _('source resolution'),
        max_length=8,
        db_index=True,
        choices=SourceResolution.choices,
        default=SourceResolution.VIDEO_1080P,
        help_text=_('Source resolution, desired video resolution to download'),
    )
    source_vcodec = db.models.CharField(
        _('source video codec'),
        max_length=8,
        db_index=True,
        choices=YouTube_VideoCodec.choices,
        default=YouTube_VideoCodec.VP9,
        help_text=_('Source video codec, desired video encoding format to download (ignored if "resolution" is audio only)'),
    )
    source_acodec = db.models.CharField(
        _('source audio codec'),
        max_length=8,
        db_index=True,
        choices=YouTube_AudioCodec.choices,
        default=YouTube_AudioCodec.OPUS,
        help_text=_('Source audio codec, desired audio encoding format to download'),
    )
    prefer_60fps = db.models.BooleanField(
        _('prefer 60fps'),
        default=True,
        help_text=_('Where possible, prefer 60fps media for this source'),
    )
    prefer_hdr = db.models.BooleanField(
        _('prefer hdr'),
        default=False,
        help_text=_('Where possible, prefer HDR media for this source'),
    )
    fallback = db.models.CharField(
        _('fallback'),
        max_length=1,
        db_index=True,
        choices=Fallback.choices,
        default=Fallback.NEXT_BEST_HD,
        help_text=_('What do do when media in your source resolution and codecs is not available'),
    )
    copy_channel_images = db.models.BooleanField(
        _('copy channel images'),
        default=False,
        help_text=_('Copy channel banner and avatar. These may be detected and used by some media servers'),
    )
    copy_thumbnails = db.models.BooleanField(
        _('copy thumbnails'),
        default=False,
        help_text=_('Copy thumbnails with the media, these may be detected and used by some media servers'),
    )
    write_nfo = db.models.BooleanField(
        _('write nfo'),
        default=False,
        help_text=_('Write an NFO file in XML with the media info, these may be detected and used by some media servers'),
    )
    write_json = db.models.BooleanField(
        _('write json'),
        default=False,
        help_text=_('Write a JSON file with the media info, these may be detected and used by some media servers'),
    )
    has_failed = db.models.BooleanField(
        _('has failed'),
        default=False,
        help_text=_('Source has failed to index media'),
    )

    write_subtitles = db.models.BooleanField(
        _('write subtitles'),
        default=False,
        help_text=_('Download video subtitles'),
    )

    auto_subtitles = db.models.BooleanField(
        _('accept auto-generated subs'),
        default=False,
        help_text=_('Accept auto-generated subtitles'),
    )
    sub_langs = db.models.CharField(
        _('subs langs'),
        max_length=30,
        default='en',
        help_text=_('List of subtitles langs to download, comma-separated. Example: en,fr or all,-fr,-live_chat'),
        validators=[
            RegexValidator(
                regex=r"^(\-?[\_\.a-zA-Z-]+(,|$))+",
                message=_('Subtitle langs must be a comma-separated list of langs. example: en,fr or all,-fr,-live_chat'),
            ),
        ],
    )
    enable_sponsorblock = db.models.BooleanField(
        _('enable sponsorblock'),
        default=True,
        help_text=_('Use SponsorBlock?'),
    )
    sponsorblock_categories = CommaSepChoiceField(
        _('removed categories'),
        max_length=128,
        possible_choices=SponsorBlock_Category.choices,
        all_choice='all',
        allow_all=True,
        all_label='(All Categories)',
        default='all',
        help_text=_('Select the SponsorBlock categories that you wish to be removed from downloaded videos.'),
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

    def deactivate(self):
        self.download_media = False
        self.index_streams = False
        self.index_videos = False
        self.index_schedule = IndexSchedule.NEVER
        self.save(update_fields={
            'download_media',
            'index_streams',
            'index_videos',
            'index_schedule',
        })

    @property
    def is_active(self):
        active = (
            self.download_media or
            self.index_streams or
            self.index_videos
        )
        return self.index_schedule and active

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
            return timezone.now() - timezone.timedelta(seconds=delta)
        else:
            return False

    @property
    def days_to_keep_date(self):
        delta = self.days_to_keep
        if delta > 0:
            return timezone.now() - timezone.timedelta(days=delta)
        else:
            return False

    @property
    def task_run_at_dt(self):
        now = timezone.now()
        if self.target_schedule > now:
            return self.target_schedule
        when = now.replace(minute=0, second=0, microsecond=0)
        while when.hour != self.target_schedule.hour:
            when += timezone.timedelta(hours=1)
        while when.weekday != self.target_schedule.weekday:
            when += timezone.timedelta(days=1)
        self.target_schedule = when
        return when

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
            if self.source_acodec == Val(YouTube_AudioCodec.MP4A):
                return Val(FileExtension.M4A)
            elif self.source_acodec == Val(YouTube_AudioCodec.OPUS):
                return Val(FileExtension.OGG)
            else:
                raise ValueError('Unable to choose audio extension, uknown acodec')
        else:
            return Val(FileExtension.MKV)

    @classmethod
    def create_url(cls, source_type, key):
        url = cls.URLS.get(source_type)
        return url.format(key=key)

    @classmethod
    def create_index_url(cls, source_type, key, type):
        url = cls.INDEX_URLS.get(source_type)
        return url.format(key=key, type=type)

    @property
    def url(self):
        return self.__class__.create_url(self.source_type, self.key)

    def get_index_url(self, type):
        return self.__class__.create_index_url(self.source_type, self.key, type)

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
        return self.fallback != Val(Fallback.FAIL)

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
        except Exception:
            return ''

    def is_regex_match(self, media_item_title):
        if not self.filter_text:
            return True
        return bool(re.search(self.filter_text, media_item_title))

    def get_index(self, type):
        indexer = self.INDEXERS.get(self.source_type, None)
        if not callable(indexer):
            raise Exception(f'Source type f"{self.source_type}" has no indexer')
        days = None
        if self.download_cap_date:
            days = timezone.timedelta(seconds=self.download_cap).days
        response = indexer(self.get_index_url(type=type), days=days)
        if not isinstance(response, dict):
            return list()
        entries = response.get('entries', list()) 
        return entries

    def index_media(self):
        '''
            Index the media source returning a queue of media metadata as dicts.
        '''
        entries = queue(list(), getattr(settings, 'MAX_ENTRIES_PROCESSING', 0) or None)
        if self.index_videos:
            entries.extend(reversed(self.get_index('videos')))

        # Playlists do something different that I have yet to figure out
        if not self.is_playlist:
            if self.index_streams:
                streams = self.get_index('streams')
                if entries.maxlen is None or 0 == len(entries):
                    entries.extend(reversed(streams))
                else:
                    # share the queue between streams and videos
                    allowed_streams = max(
                        entries.maxlen // 2,
                        entries.maxlen - len(entries),
                    )
                    entries.extend(reversed(streams[: allowed_streams]))

        return entries

