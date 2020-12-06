import uuid
import json
from datetime import datetime
from pathlib import Path
from django.conf import settings
from django.db import models
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from .youtube import get_media_info as get_youtube_media_info


class Source(models.Model):
    '''
        A Source is a source of media. Currently, this is either a YouTube channel
        or a YouTube playlist.
    '''

    SOURCE_TYPE_YOUTUBE_CHANNEL = 'c'
    SOURCE_TYPE_YOUTUBE_PLAYLIST = 'p'
    SOURCE_TYPES = (SOURCE_TYPE_YOUTUBE_CHANNEL, SOURCE_TYPE_YOUTUBE_PLAYLIST)
    SOURCE_TYPE_CHOICES = (
        (SOURCE_TYPE_YOUTUBE_CHANNEL, _('YouTube channel')),
        (SOURCE_TYPE_YOUTUBE_PLAYLIST, _('YouTube playlist')),
    )

    SOURCE_RESOLUTION_360p = '360p'
    SOURCE_RESOLUTION_480p = '480p'
    SOURCE_RESOLUTION_720P = '720p'
    SOURCE_RESOLUTION_1080P = '1080p'
    SOURCE_RESOLUTION_2160P = '2160p'
    SOURCE_RESOLUTION_AUDIO = 'audio'
    SOURCE_RESOLUTIONS = (SOURCE_RESOLUTION_360p, SOURCE_RESOLUTION_480p,
                          SOURCE_RESOLUTION_720P, SOURCE_RESOLUTION_1080P,
                          SOURCE_RESOLUTION_2160P, SOURCE_RESOLUTION_AUDIO)
    SOURCE_RESOLUTION_CHOICES = (
        (SOURCE_RESOLUTION_360p, _('360p (SD)')),
        (SOURCE_RESOLUTION_480p, _('480p (SD)')),
        (SOURCE_RESOLUTION_720P, _('720p (HD)')),
        (SOURCE_RESOLUTION_1080P, _('1080p (Full HD)')),
        (SOURCE_RESOLUTION_2160P, _('2160p (4K)')),
        (SOURCE_RESOLUTION_AUDIO, _('Audio only')),
    )

    SOURCE_VCODEC_AVC1 = 'AVC1'
    SOURCE_VCODEC_VP9 = 'VP9'
    SOURCE_VCODECS = (SOURCE_VCODEC_AVC1, SOURCE_VCODEC_VP9)
    SOURCE_VCODECS_PRIORITY = (SOURCE_VCODEC_VP9, SOURCE_VCODEC_AVC1)
    SOURCE_VCODEC_CHOICES = (
        (SOURCE_VCODEC_AVC1, _('AVC1 (H.264)')),
        (SOURCE_VCODEC_VP9, _('VP9')),
    )

    SOURCE_ACODEC_M4A = 'M4A'
    SOURCE_ACODEC_OPUS = 'OPUS'
    SOURCE_ACODECS = (SOURCE_ACODEC_M4A, SOURCE_ACODEC_OPUS)
    SOURCE_ACODEC_PRIORITY = (SOURCE_ACODEC_OPUS, SOURCE_ACODEC_M4A)
    SOURCE_ACODEC_CHOICES = (
        (SOURCE_ACODEC_M4A, _('M4A')),
        (SOURCE_ACODEC_OPUS, _('OPUS')),
    )

    FALLBACK_FAIL = 'f'
    FALLBACK_NEXT_SD = 's'
    FALLBACK_NEXT_HD = 'h'
    FALLBACKS = (FALLBACK_FAIL, FALLBACK_NEXT_SD, FALLBACK_NEXT_HD)
    FALLBACK_CHOICES = (
        (FALLBACK_FAIL, _('Fail, do not download any media')),
        (FALLBACK_NEXT_SD, _('Get next best SD media or codec instead')),
        (FALLBACK_NEXT_HD, _('Get next best HD media or codec instead')),
    )

    ICONS = {
        SOURCE_TYPE_YOUTUBE_CHANNEL: '<i class="fab fa-youtube"></i>',
        SOURCE_TYPE_YOUTUBE_PLAYLIST: '<i class="fab fa-youtube"></i>',
    }

    URLS = {
        SOURCE_TYPE_YOUTUBE_CHANNEL: 'https://www.youtube.com/c/{key}',
        SOURCE_TYPE_YOUTUBE_PLAYLIST: 'https://www.youtube.com/playlist?list={key}',
    }

    INDEXERS = {
        SOURCE_TYPE_YOUTUBE_CHANNEL: get_youtube_media_info,
        SOURCE_TYPE_YOUTUBE_PLAYLIST: get_youtube_media_info,
    }

    KEY_FIELD = {  # Field returned by indexing which contains a unique key
        SOURCE_TYPE_YOUTUBE_CHANNEL: 'id',
        SOURCE_TYPE_YOUTUBE_PLAYLIST: 'id',
    }

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
        default=FALLBACK_FAIL,
        help_text=_('What do do when media in your source resolution and codecs is not available')
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
    def is_audio(self):
        return self.source_resolution == self.SOURCE_RESOLUTION_AUDIO

    @property
    def is_video(self):
        return not self.is_audio

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
            if self.source_acodec == self.SOURCE_ACODEC_M4A:
                return 'm4a'
            elif self.source_acodec == self.SOURCE_ACODEC_OPUS:
                return 'ogg'
            else:
                raise ValueError('Unable to choose audio extension, uknown acodec')
        else:
            return 'mkv'

    @classmethod
    def create_url(obj, source_type, key):
        url = obj.URLS.get(source_type)
        return url.format(key=key)

    @property
    def url(self):
        return Source.create_url(self.source_type, self.key)

    @property
    def format_summary(self):
        if self.source_resolution == Source.SOURCE_RESOLUTION_AUDIO:
            vc = 'none'
        else:
            vc = self.source_vcodec
        ac = self.source_acodec
        f = '60FPS' if self.prefer_60fps else ''
        h = 'HDR' if self.prefer_hdr else ''
        return f'{self.source_resolution} (video:{vc}, audio:{ac}) {f} {h}'.strip()

    @property
    def directory_path(self):
        if self.source_resolution == self.SOURCE_RESOLUTION_AUDIO:
            return settings.SYNC_AUDIO_ROOT / self.directory
        else:
            return settings.SYNC_VIDEO_ROOT / self.directory

    @property
    def key_field(self):
        return self.KEY_FIELD.get(self.source_type, '')

    def index_media(self):
        '''
            Index the media source returning a list of media metadata as dicts.
        '''
        indexer = self.INDEXERS.get(self.source_type, None)
        if not callable(indexer):
            raise Exception(f'Source type f"{self.source_type}" has no indexer')
        response = indexer(self.url)
        return response.get('entries', [])


def get_media_thumb_path(instance, filename):
    fileid = str(instance.uuid)
    filename = f'{fileid.lower()}.jpg'
    prefix = fileid[:2]
    return Path('thumbs') / prefix / filename


_metadata_cache = {}


class Media(models.Model):
    '''
        Media is a single piece of media, such as a single YouTube video linked to a
        Source.
    '''

    URLS = {
        Source.SOURCE_TYPE_YOUTUBE_CHANNEL: 'https://www.youtube.com/watch?v={key}',
        Source.SOURCE_TYPE_YOUTUBE_PLAYLIST: 'https://www.youtube.com/watch?v={key}',
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
        max_length=100,
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
    downloaded = models.BooleanField(
        _('downloaded'),
        db_index=True,
        default=False,
        help_text=_('Media has been downloaded')
    )
    downloaded_audio_codec = models.CharField(
        _('downloaded audio codec'),
        max_length=30,
        db_index=True,
        blank=True,
        null=True,
        help_text=_('Audio codec of the downloaded media')
    )
    downloaded_video_codec = models.CharField(
        _('downloaded video codec'),
        max_length=30,
        db_index=True,
        blank=True,
        null=True,
        help_text=_('Video codec of the downloaded media')
    )
    downloaded_container = models.CharField(
        _('downloaded container format'),
        max_length=30,
        db_index=True,
        blank=True,
        null=True,
        help_text=_('Container format of the downloaded media')
    )
    downloaded_fps = models.PositiveSmallIntegerField(
        _('downloaded fps'),
        db_index=True,
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

    @property
    def loaded_metadata(self):
        if self.pk in _metadata_cache:
            return _metadata_cache[self.pk]
        _metadata_cache[self.pk] = json.loads(self.metadata)
        return _metadata_cache[self.pk]

    @property
    def url(self):
        url = self.URLS.get(self.source.source_type, '')
        return url.format(key=self.key)

    @property
    def title(self):
        return self.loaded_metadata.get('title', '').strip()

    @property
    def upload_date(self):
        upload_date_str = self.loaded_metadata.get('upload_date', '').strip()
        try:
            return datetime.strptime(upload_date_str, '%Y%m%d')
        except ValueError as e:
            return None

    @property
    def filename(self):
        upload_date = self.upload_date.strftime('%Y-%m-%d')
        source_name = slugify(self.source.name)
        title = slugify(self.title.replace('&', 'and').replace('+', 'and'))
        ext = self.source.extension
        fn = f'{upload_date}_{source_name}_{title}'[:100]
        return f'{fn}.{ext}'

    @property
    def filepath(self):
        return self.source.directory_path / self.filename
