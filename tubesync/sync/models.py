import os
import uuid
import json
from xml.etree import ElementTree
from collections import OrderedDict
from datetime import datetime, timedelta
from pathlib import Path
from django.conf import settings
from django.db import models
from django.core.files.storage import FileSystemStorage
from django.core.validators import RegexValidator
from django.utils.text import slugify
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from common.errors import NoFormatException
from common.utils import clean_filename
from .youtube import (get_media_info as get_youtube_media_info,
                      download_media as download_youtube_media)
from .utils import seconds_to_timestr, parse_media_format
from .matching import (get_best_combined_format, get_best_audio_format, 
                       get_best_video_format)
from .mediaservers import PlexMediaServer
from .fields import CommaSepChoiceField

media_file_storage = FileSystemStorage(location=str(settings.DOWNLOAD_ROOT), base_url='/media-data/')

class Source(models.Model):
    '''
        A Source is a source of media. Currently, this is either a YouTube channel
        or a YouTube playlist.
    '''

    SOURCE_TYPE_YOUTUBE_CHANNEL = 'c'
    SOURCE_TYPE_YOUTUBE_CHANNEL_ID = 'i'
    SOURCE_TYPE_YOUTUBE_PLAYLIST = 'p'
    SOURCE_TYPES = (SOURCE_TYPE_YOUTUBE_CHANNEL, SOURCE_TYPE_YOUTUBE_CHANNEL_ID,
                    SOURCE_TYPE_YOUTUBE_PLAYLIST)
    SOURCE_TYPE_CHOICES = (
        (SOURCE_TYPE_YOUTUBE_CHANNEL, _('YouTube channel')),
        (SOURCE_TYPE_YOUTUBE_CHANNEL_ID, _('YouTube channel by ID')),
        (SOURCE_TYPE_YOUTUBE_PLAYLIST, _('YouTube playlist')),
    )

    SOURCE_RESOLUTION_360P = '360p'
    SOURCE_RESOLUTION_480P = '480p'
    SOURCE_RESOLUTION_720P = '720p'
    SOURCE_RESOLUTION_1080P = '1080p'
    SOURCE_RESOLUTION_1440P = '1440p'
    SOURCE_RESOLUTION_2160P = '2160p'
    SOURCE_RESOLUTION_4320P = '4320p'
    SOURCE_RESOLUTION_AUDIO = 'audio'
    SOURCE_RESOLUTIONS = (SOURCE_RESOLUTION_360P, SOURCE_RESOLUTION_480P,
                          SOURCE_RESOLUTION_720P, SOURCE_RESOLUTION_1080P,
                          SOURCE_RESOLUTION_1440P, SOURCE_RESOLUTION_2160P,
                          SOURCE_RESOLUTION_4320P, SOURCE_RESOLUTION_AUDIO)
    SOURCE_RESOLUTION_CHOICES = (
        (SOURCE_RESOLUTION_360P, _('360p (SD)')),
        (SOURCE_RESOLUTION_480P, _('480p (SD)')),
        (SOURCE_RESOLUTION_720P, _('720p (HD)')),
        (SOURCE_RESOLUTION_1080P, _('1080p (Full HD)')),
        (SOURCE_RESOLUTION_1440P, _('1440p (2K)')),
        (SOURCE_RESOLUTION_2160P, _('2160p (4K)')),
        (SOURCE_RESOLUTION_4320P, _('4320p (8K)')),
        (SOURCE_RESOLUTION_AUDIO, _('Audio only')),
    )
    RESOLUTION_MAP = {
        SOURCE_RESOLUTION_360P: 360,
        SOURCE_RESOLUTION_480P: 480,
        SOURCE_RESOLUTION_720P: 720,
        SOURCE_RESOLUTION_1080P: 1080,
        SOURCE_RESOLUTION_1440P: 1440,
        SOURCE_RESOLUTION_2160P: 2160,
        SOURCE_RESOLUTION_4320P: 4320,
    }

    SOURCE_VCODEC_AVC1 = 'AVC1'
    SOURCE_VCODEC_VP9 = 'VP9'
    SOURCE_VCODECS = (SOURCE_VCODEC_AVC1, SOURCE_VCODEC_VP9)
    SOURCE_VCODECS_PRIORITY = (SOURCE_VCODEC_VP9, SOURCE_VCODEC_AVC1)
    SOURCE_VCODEC_CHOICES = (
        (SOURCE_VCODEC_AVC1, _('AVC1 (H.264)')),
        (SOURCE_VCODEC_VP9, _('VP9')),
    )

    SOURCE_ACODEC_MP4A = 'MP4A'
    SOURCE_ACODEC_OPUS = 'OPUS'
    SOURCE_ACODECS = (SOURCE_ACODEC_MP4A, SOURCE_ACODEC_OPUS)
    SOURCE_ACODEC_PRIORITY = (SOURCE_ACODEC_OPUS, SOURCE_ACODEC_MP4A)
    SOURCE_ACODEC_CHOICES = (
        (SOURCE_ACODEC_MP4A, _('MP4A')),
        (SOURCE_ACODEC_OPUS, _('OPUS')),
    )

    FALLBACK_FAIL = 'f'
    FALLBACK_NEXT_BEST = 'n'
    FALLBACK_NEXT_BEST_HD = 'h'
    FALLBACKS = (FALLBACK_FAIL, FALLBACK_NEXT_BEST, FALLBACK_NEXT_BEST_HD)
    FALLBACK_CHOICES = (
        (FALLBACK_FAIL, _('Fail, do not download any media')),
        (FALLBACK_NEXT_BEST, _('Get next best resolution or codec instead')),
        (FALLBACK_NEXT_BEST_HD, _('Get next best resolution but at least HD'))
    )

    EXTENSION_M4A = 'm4a'
    EXTENSION_OGG = 'ogg'
    EXTENSION_MKV = 'mkv'
    EXTENSIONS = (EXTENSION_M4A, EXTENSION_OGG, EXTENSION_MKV)


    # as stolen from: https://wiki.sponsor.ajay.app/w/Types / https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/postprocessor/sponsorblock.py
    SPONSORBLOCK_CATEGORIES_CHOICES = (
        ('sponsor', 'Sponsor'),
        ('intro', 'Intermission/Intro Animation'),
        ('outro', 'Endcards/Credits'),
        ('selfpromo', 'Unpaid/Self Promotion'),
        ('preview', 'Preview/Recap'),
        ('filler', 'Filler Tangent'),
        ('interaction', 'Interaction Reminder'),
        ('music_offtopic', 'Non-Music Section'),
    )
    
    sponsorblock_categories = CommaSepChoiceField(
            _(''),
            possible_choices=SPONSORBLOCK_CATEGORIES_CHOICES,
            all_choice="all",
            allow_all=True,
            all_label="(all options)",
            default="all",
            help_text=_("Select the sponsorblocks you want to enforce")
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
    ICONS = {
        SOURCE_TYPE_YOUTUBE_CHANNEL: '<i class="fab fa-youtube"></i>',
        SOURCE_TYPE_YOUTUBE_CHANNEL_ID: '<i class="fab fa-youtube"></i>',
        SOURCE_TYPE_YOUTUBE_PLAYLIST: '<i class="fab fa-youtube"></i>',
    }
    # Format to use to display a URL for the source
    URLS = {
        SOURCE_TYPE_YOUTUBE_CHANNEL: 'https://www.youtube.com/c/{key}',
        SOURCE_TYPE_YOUTUBE_CHANNEL_ID: 'https://www.youtube.com/channel/{key}',
        SOURCE_TYPE_YOUTUBE_PLAYLIST: 'https://www.youtube.com/playlist?list={key}',
    }
    # Format used to create indexable URLs
    INDEX_URLS = {
        SOURCE_TYPE_YOUTUBE_CHANNEL: 'https://www.youtube.com/c/{key}/videos',
        SOURCE_TYPE_YOUTUBE_CHANNEL_ID: 'https://www.youtube.com/channel/{key}/videos',
        SOURCE_TYPE_YOUTUBE_PLAYLIST: 'https://www.youtube.com/playlist?list={key}',
    }
    # Callback functions to get a list of media from the source
    INDEXERS = {
        SOURCE_TYPE_YOUTUBE_CHANNEL: get_youtube_media_info,
        SOURCE_TYPE_YOUTUBE_CHANNEL_ID: get_youtube_media_info,
        SOURCE_TYPE_YOUTUBE_PLAYLIST: get_youtube_media_info,
    }
    # Field names to find the media ID used as the key when storing media
    KEY_FIELD = {
        SOURCE_TYPE_YOUTUBE_CHANNEL: 'id',
        SOURCE_TYPE_YOUTUBE_CHANNEL_ID: 'id',
        SOURCE_TYPE_YOUTUBE_PLAYLIST: 'id',
    }

    class CapChoices(models.IntegerChoices):
        CAP_NOCAP = 0, _('No cap')
        CAP_7DAYS = 604800, _('1 week (7 days)')
        CAP_30DAYS = 2592000, _('1 month (30 days)')
        CAP_90DAYS = 7776000, _('3 months (90 days)')
        CAP_6MONTHS = 15552000, _('6 months (180 days)')
        CAP_1YEAR = 31536000, _('1 year (365 days)')
        CAP_2YEARs = 63072000, _('2 years (730 days)')
        CAP_3YEARs = 94608000, _('3 years (1095 days)')
        CAP_5YEARs = 157680000, _('5 years (1825 days)')
        CAP_10YEARS = 315360000, _('10 years (3650 days)')

    class IndexSchedule(models.IntegerChoices):
        EVERY_HOUR = 3600, _('Every hour')
        EVERY_2_HOURS = 7200, _('Every 2 hours')
        EVERY_3_HOURS = 10800, _('Every 3 hours')
        EVERY_4_HOURS = 14400, _('Every 4 hours')
        EVERY_5_HOURS = 18000, _('Every 5 hours')
        EVERY_6_HOURS = 21600, _('Every 6 hours')
        EVERY_12_HOURS = 43200, _('Every 12 hours')
        EVERY_24_HOURS = 86400, _('Every 24 hours')
        EVERY_3_DAYS = 259200, _('Every 3 days')
        EVERY_7_DAYS = 604800, _('Every 7 days')
        NEVER = 0, _('Never')

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
        choices=SOURCE_TYPE_CHOICES,
        default=SOURCE_TYPE_YOUTUBE_CHANNEL,
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
    delete_removed_media = models.BooleanField(
        _('delete removed media'),
        default=False,
        help_text=_('Delete media that is no longer on this playlist')
    )
    source_resolution = models.CharField(
        _('source resolution'),
        max_length=8,
        db_index=True,
        choices=SOURCE_RESOLUTION_CHOICES,
        default=SOURCE_RESOLUTION_1080P,
        help_text=_('Source resolution, desired video resolution to download')
    )
    source_vcodec = models.CharField(
        _('source video codec'),
        max_length=8,
        db_index=True,
        choices=SOURCE_VCODEC_CHOICES,
        default=SOURCE_VCODEC_VP9,
        help_text=_('Source video codec, desired video encoding format to download (ignored if "resolution" is audio only)')
    )
    source_acodec = models.CharField(
        _('source audio codec'),
        max_length=8,
        db_index=True,
        choices=SOURCE_ACODEC_CHOICES,
        default=SOURCE_ACODEC_OPUS,
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
        choices=FALLBACK_CHOICES,
        default=FALLBACK_NEXT_BEST_HD,
        help_text=_('What do do when media in your source resolution and codecs is not available')
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
                regex=r"^(\-?[\_\.a-zA-Z]+,)*(\-?[\_\.a-zA-Z]+){1}$",
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
        return self.source_resolution == self.SOURCE_RESOLUTION_AUDIO

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
    def extension(self):
        '''
            The extension is also used by youtube-dl to set the output container. As
            it is possible to quite easily pick combinations of codecs and containers
            which are invalid (e.g. OPUS audio in an MP4 container) just set this for
            people. All video is set to mkv containers, audio-only is set to m4a or ogg
            depending on audio codec.
        '''
        if self.is_audio:
            if self.source_acodec == self.SOURCE_ACODEC_MP4A:
                return self.EXTENSION_M4A
            elif self.source_acodec == self.SOURCE_ACODEC_OPUS:
                return self.EXTENSION_OGG
            else:
                raise ValueError('Unable to choose audio extension, uknown acodec')
        else:
            return self.EXTENSION_MKV

    @classmethod
    def create_url(obj, source_type, key):
        url = obj.URLS.get(source_type)
        return url.format(key=key)

    @classmethod
    def create_index_url(obj, source_type, key):
        url = obj.INDEX_URLS.get(source_type)
        return url.format(key=key)

    @property
    def url(self):
        return Source.create_url(self.source_type, self.key)

    @property
    def index_url(self):
        return Source.create_index_url(self.source_type, self.key)

    @property
    def format_summary(self):
        if self.source_resolution == Source.SOURCE_RESOLUTION_AUDIO:
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
        if self.source_resolution == self.SOURCE_RESOLUTION_AUDIO:
            return Path(settings.DOWNLOAD_AUDIO_DIR) / self.directory
        else:
            return Path(settings.DOWNLOAD_VIDEO_DIR) / self.directory

    def make_directory(self):
        return os.makedirs(self.directory_path, exist_ok=True)

    def directory_exists(self):
        return (os.path.isdir(self.directory_path) and
                os.access(self.directory_path, os.W_OK))

    @property
    def key_field(self):
        return self.KEY_FIELD.get(self.source_type, '')

    @property
    def source_resolution_height(self):
        return self.RESOLUTION_MAP.get(self.source_resolution, 0)

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

    def index_media(self):
        '''
            Index the media source returning a list of media metadata as dicts.
        '''
        indexer = self.INDEXERS.get(self.source_type, None)
        if not callable(indexer):
            raise Exception(f'Source type f"{self.source_type}" has no indexer')
        response = indexer(self.index_url)
        if not isinstance(response, dict):
            return []
        entries = response.get('entries', [])

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
    URLS = {
        Source.SOURCE_TYPE_YOUTUBE_CHANNEL: 'https://www.youtube.com/watch?v={key}',
        Source.SOURCE_TYPE_YOUTUBE_CHANNEL_ID: 'https://www.youtube.com/watch?v={key}',
        Source.SOURCE_TYPE_YOUTUBE_PLAYLIST: 'https://www.youtube.com/watch?v={key}',
    }
    # Callback functions to get a list of media from the source
    INDEXERS = {
        Source.SOURCE_TYPE_YOUTUBE_CHANNEL: get_youtube_media_info,
        Source.SOURCE_TYPE_YOUTUBE_CHANNEL_ID: get_youtube_media_info,
        Source.SOURCE_TYPE_YOUTUBE_PLAYLIST: get_youtube_media_info,
    }
    # Maps standardised names to names used in source metdata
    METADATA_FIELDS = {
        'upload_date': {
            Source.SOURCE_TYPE_YOUTUBE_CHANNEL: 'upload_date',
            Source.SOURCE_TYPE_YOUTUBE_CHANNEL_ID: 'upload_date',
            Source.SOURCE_TYPE_YOUTUBE_PLAYLIST: 'upload_date',
        },
        'title': {
            Source.SOURCE_TYPE_YOUTUBE_CHANNEL: 'title',
            Source.SOURCE_TYPE_YOUTUBE_CHANNEL_ID: 'title',
            Source.SOURCE_TYPE_YOUTUBE_PLAYLIST: 'title',
        },
        'thumbnail': {
            Source.SOURCE_TYPE_YOUTUBE_CHANNEL: 'thumbnail',
            Source.SOURCE_TYPE_YOUTUBE_CHANNEL_ID: 'thumbnail',
            Source.SOURCE_TYPE_YOUTUBE_PLAYLIST: 'thumbnail',
        },
        'description': {
            Source.SOURCE_TYPE_YOUTUBE_CHANNEL: 'description',
            Source.SOURCE_TYPE_YOUTUBE_CHANNEL_ID: 'description',
            Source.SOURCE_TYPE_YOUTUBE_PLAYLIST: 'description',
        },
        'duration': {
            Source.SOURCE_TYPE_YOUTUBE_CHANNEL: 'duration',
            Source.SOURCE_TYPE_YOUTUBE_CHANNEL_ID: 'duration',
            Source.SOURCE_TYPE_YOUTUBE_PLAYLIST: 'duration',
        },
        'formats': {
            Source.SOURCE_TYPE_YOUTUBE_CHANNEL: 'formats',
            Source.SOURCE_TYPE_YOUTUBE_CHANNEL_ID: 'formats',
            Source.SOURCE_TYPE_YOUTUBE_PLAYLIST: 'formats',
        },
        'categories': {
            Source.SOURCE_TYPE_YOUTUBE_CHANNEL: 'categories',
            Source.SOURCE_TYPE_YOUTUBE_CHANNEL_ID: 'categories',
            Source.SOURCE_TYPE_YOUTUBE_PLAYLIST: 'categories',
        },
        'rating': {
            Source.SOURCE_TYPE_YOUTUBE_CHANNEL: 'average_rating',
            Source.SOURCE_TYPE_YOUTUBE_CHANNEL_ID: 'average_rating',
            Source.SOURCE_TYPE_YOUTUBE_PLAYLIST: 'average_rating',
        },
        'age_limit': {
            Source.SOURCE_TYPE_YOUTUBE_CHANNEL: 'age_limit',
            Source.SOURCE_TYPE_YOUTUBE_CHANNEL_ID: 'age_limit',
            Source.SOURCE_TYPE_YOUTUBE_PLAYLIST: 'age_limit',
        },
        'uploader': {
            Source.SOURCE_TYPE_YOUTUBE_CHANNEL: 'uploader',
            Source.SOURCE_TYPE_YOUTUBE_CHANNEL_ID: 'uploader',
            Source.SOURCE_TYPE_YOUTUBE_PLAYLIST: 'uploader',
        },
        'upvotes': {
            Source.SOURCE_TYPE_YOUTUBE_CHANNEL: 'like_count',
            Source.SOURCE_TYPE_YOUTUBE_CHANNEL_ID: 'like_count',
            Source.SOURCE_TYPE_YOUTUBE_PLAYLIST: 'like_count',
        },
        'downvotes': {
            Source.SOURCE_TYPE_YOUTUBE_CHANNEL: 'dislike_count',
            Source.SOURCE_TYPE_YOUTUBE_CHANNEL_ID: 'dislike_count',
            Source.SOURCE_TYPE_YOUTUBE_PLAYLIST: 'dislike_count',
        },
        'playlist_title': {
            Source.SOURCE_TYPE_YOUTUBE_CHANNEL: 'playlist_title',
            Source.SOURCE_TYPE_YOUTUBE_CHANNEL_ID: 'playlist_title',
            Source.SOURCE_TYPE_YOUTUBE_PLAYLIST: 'playlist_title',
        },
    }
    STATE_UNKNOWN = 'unknown'
    STATE_SCHEDULED = 'scheduled'
    STATE_DOWNLOADING = 'downloading'
    STATE_DOWNLOADED = 'downloaded'
    STATE_SKIPPED = 'skipped'
    STATE_DISABLED_AT_SOURCE = 'source-disabled'
    STATE_ERROR = 'error'
    STATES = (STATE_UNKNOWN, STATE_SCHEDULED, STATE_DOWNLOADING, STATE_DOWNLOADED,
              STATE_SKIPPED, STATE_DISABLED_AT_SOURCE, STATE_ERROR)
    STATE_ICONS = {
        STATE_UNKNOWN: '<i class="far fa-question-circle" title="Unknown download state"></i>',
        STATE_SCHEDULED: '<i class="far fa-clock" title="Scheduled to download"></i>',
        STATE_DOWNLOADING: '<i class="fas fa-download" title="Downloading now"></i>',
        STATE_DOWNLOADED: '<i class="far fa-check-circle" title="Downloaded"></i>',
        STATE_SKIPPED: '<i class="fas fa-exclamation-circle" title="Skipped"></i>',
        STATE_DISABLED_AT_SOURCE: '<i class="fas fa-stop-circle" title="Media downloading disabled at source"></i>',
        STATE_ERROR: '<i class="fas fa-exclamation-triangle" title="Error downloading"></i>',
    }

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
        help_text=_('Media marked as "skipped", won\' be downloaded')
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

    def __str__(self):
        return self.key

    class Meta:
        verbose_name = _('Media')
        verbose_name_plural = _('Media')
        unique_together = (
            ('source', 'key'),
        )

    def get_metadata_field(self, field):
        fields = self.METADATA_FIELDS.get(field, {})
        return fields.get(self.source.source_type, '')

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
            if self.downloaded_format != 'audio':
                vcodec = self.downloaded_video_codec.lower()
                fmt.append(vcodec)
            acodec = self.downloaded_audio_codec.lower()
            fmt.append(acodec)
            if self.downloaded_format != 'audio':
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
            'source_full': self.source.name,
            'title': self.slugtitle,
            'title_full': clean_filename(self.title),
            'key': self.key,
            'format': '-'.join(display_format['format']),
            'playlist_title': self.playlist_title,
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
    def loaded_metadata(self):
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
    def title(self):
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
    def duration(self):
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
        if duration > 0:
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
    def thumbname(self):
        if self.downloaded and self.media_file:
            filename = os.path.basename(self.media_file.path)
        else:
            filename = self.filename
        prefix, ext = os.path.splitext(filename)
        return f'{prefix}.jpg'

    @property
    def thumbpath(self):
        return self.source.directory_path / self.thumbname

    @property
    def nfoname(self):
        if self.downloaded and self.media_file:
            filename = os.path.basename(self.media_file.path)
        else:
            filename = self.filename
        prefix, ext = os.path.splitext(filename)
        return f'{prefix}.nfo'
    
    @property
    def nfopath(self):
        return self.source.directory_path / self.nfoname

    @property
    def jsonname(self):
        if self.downloaded and self.media_file:
            filename = os.path.basename(self.media_file.path)
        else:
            filename = self.filename
        prefix, ext = os.path.splitext(filename)
        return f'{prefix}.info.json'
    
    @property
    def jsonpath(self):
        return self.source.directory_path / self.jsonname

    @property
    def directory_path(self):
        # Otherwise, create a suitable filename from the source media_format
        media_format = str(self.source.media_format)
        media_details = self.format_dict
        dirname = self.source.directory_path / media_format.format(**media_details)
        return os.path.dirname(str(dirname))

    @property
    def filepath(self):
        return self.source.directory_path / self.filename

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
            
            acodec = acodec.lower()
            if acodec == "mp4a":
                return "audio/mp4"
            elif acodec == "opus":
                return "audio/opus"
            else:
                # fall-fall-back.
                return 'audio/ogg'

        vcodec = vcodec.lower()
        if vcodec == 'vp9':
            return 'video/webm'
        else:
            return 'video/mp4'

    @property
    def nfoxml(self):
        '''
            Returns an NFO formatted (prettified) XML string.
        '''
        nfo = ElementTree.Element('episodedetails')
        nfo.text = '\n  '
        # title = media metadata title
        title = nfo.makeelement('title', {})
        title.text = str(self.name).strip()
        title.tail = '\n  '
        nfo.append(title)
        # showtitle = source name
        showtitle = nfo.makeelement('showtitle', {})
        showtitle.text = str(self.source.name).strip()
        showtitle.tail = '\n  '
        nfo.append(showtitle)
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
        rating_attrs['default'] = 'True'
        rating = nfo.makeelement('rating', rating_attrs)
        rating.text = '\n      '
        rating.append(value)
        rating.append(votes)
        rating.tail = '\n  '
        ratings = nfo.makeelement('ratings', {})
        ratings.text = '\n    '
        ratings.append(rating)
        ratings.tail = '\n  '
        nfo.append(ratings)
        # plot = media metadata description
        plot = nfo.makeelement('plot', {})
        plot.text = str(self.description).strip()
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
        studio.text = str(self.uploader).strip()
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
            return self.STATE_DOWNLOADED
        if task:
            if task.locked_by_pid_running():
                return self.STATE_DOWNLOADING
            elif task.has_error():
                return self.STATE_ERROR
            else:
                return self.STATE_SCHEDULED
        if self.skip:
            return self.STATE_SKIPPED
        if not self.source.download_media:
            return self.STATE_DISABLED_AT_SOURCE
        return self.STATE_UNKNOWN

    def get_download_state_icon(self, task=None):
        state = self.get_download_state(task)
        return self.STATE_ICONS.get(state, self.STATE_ICONS[self.STATE_UNKNOWN])

    def download_media(self):
        format_str = self.get_format_str()
        if not format_str:
            raise NoFormatException(f'Cannot download, media "{self.pk}" ({self}) has '
                                    f'no valid format available')
        # Download the media with youtube-dl
        download_youtube_media(self.url, format_str, self.source.extension,
                               str(self.filepath), self.source.write_json, 
                               self.source.sponsorblock_categories, self.source.embed_thumbnail,
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
        return indexer(self.url)


class MediaServer(models.Model):
    '''
        A remote media server, such as a Plex server.
    '''

    SERVER_TYPE_PLEX = 'p'
    SERVER_TYPES = (SERVER_TYPE_PLEX,)
    SERVER_TYPE_CHOICES = (
        (SERVER_TYPE_PLEX, _('Plex')),
    )
    ICONS = {
        SERVER_TYPE_PLEX: '<i class="fas fa-server"></i>',
    }
    HANDLERS = {
        SERVER_TYPE_PLEX: PlexMediaServer,
    }

    server_type = models.CharField(
        _('server type'),
        max_length=1,
        db_index=True,
        choices=SERVER_TYPE_CHOICES,
        default=SERVER_TYPE_PLEX,
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
