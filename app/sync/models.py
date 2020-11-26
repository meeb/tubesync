import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _


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

    SOURCE_PROFILE_360p = '360p'
    SOURCE_PROFILE_480p = '480p'
    SOURCE_PROFILE_720P = '720p'
    SOURCE_PROFILE_1080P = '1080p'
    SOURCE_PROFILE_2160P = '2160p'
    SOURCE_PROFILE_AUDIO = 'audio'
    SOURCE_PROFILES = (SOURCE_PROFILE_360p, SOURCE_PROFILE_480p, SOURCE_PROFILE_720P,
                       SOURCE_PROFILE_1080P, SOURCE_PROFILE_2160P,
                       SOURCE_PROFILE_AUDIO)
    SOURCE_PROFILE_CHOICES = (
        (SOURCE_PROFILE_360p, _('360p (SD)')),
        (SOURCE_PROFILE_480p, _('480p (SD)')),
        (SOURCE_PROFILE_720P, _('720p (HD)')),
        (SOURCE_PROFILE_1080P, _('1080p (Full HD)')),
        (SOURCE_PROFILE_2160P, _('2160p (4K)')),
        (SOURCE_PROFILE_AUDIO, _('Audio only')),
    )

    OUTPUT_FORMAT_MP4 = 'mp4'
    OUTPUT_FORMAT_MKV = 'mkv'
    OUTPUT_FORMAT_M4A = 'm4a'
    OUTPUT_FORMAT_OGG = 'ogg'
    OUTPUT_FORMATS = (OUTPUT_FORMAT_MP4, OUTPUT_FORMAT_MKV, OUTPUT_FORMAT_M4A,
                      OUTPUT_FORMAT_OGG)
    OUTPUT_FORMAT_CHOICES = (
        (OUTPUT_FORMAT_MP4, _('.mp4 container')),
        (OUTPUT_FORMAT_MKV, _('.mkv container')),
        (OUTPUT_FORMAT_MKV, _('.webm container')),
        (OUTPUT_FORMAT_M4A, _('.m4a container (audio only)')),
        (OUTPUT_FORMAT_OGG, _('.ogg container (audio only)')),
    )

    FALLBACK_FAIL = 'f'
    FALLBACK_NEXT_SD = 's'
    FALLBACK_NEXT_HD = 'h'
    FALLBACKS = (FALLBACK_FAIL, FALLBACK_NEXT_SD, FALLBACK_NEXT_HD)
    FALLBACK_CHOICES = (
        (FALLBACK_FAIL, _('Fail, do not download any media')),
        (FALLBACK_NEXT_SD, _('Get next best SD media instead')),
        (FALLBACK_NEXT_HD, _('Get next best HD media instead')),
    )

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
        _('type'),
        max_length=1,
        db_index=True,
        choices=SOURCE_TYPE_CHOICES,
        default=SOURCE_TYPE_YOUTUBE_CHANNEL,
        help_text=_('Source type')
    )
    url = models.URLField(
        _('url'),
        db_index=True,
        help_text=_('URL of the source')
    )
    key = models.CharField(
        _('key'),
        max_length=100,
        db_index=True,
        help_text=_('Source key, such as exact YouTube channel name or playlist ID')
    )
    name = models.CharField(
        _('name'),
        max_length=100,
        db_index=True,
        help_text=_('Friendly name for the source, used locally in TubeSync only')
    )
    directory = models.CharField(
        _('directory'),
        max_length=100,
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
    source_profile = models.CharField(
        _('source profile'),
        max_length=8,
        db_index=True,
        choices=SOURCE_PROFILE_CHOICES,
        default=SOURCE_PROFILE_1080P,
        help_text=_('Source profile, the quality to attempt to download media')
    )
    prefer_60fps = models.BooleanField(
        _('prefer 60fps'),
        default=False,
        help_text=_('Where possible, prefer 60fps media for this source')
    )
    prefer_hdr = models.BooleanField(
        _('prefer hdr'),
        default=False,
        help_text=_('Where possible, prefer HDR media for this source')
    )
    output_format = models.CharField(
        _('output format'),
        max_length=8,
        db_index=True,
        choices=OUTPUT_FORMAT_CHOICES,
        default=OUTPUT_FORMAT_MKV,
        help_text=_('Output format, the file format container in which to save media')
    )
    fallback = models.CharField(
        _('fallback'),
        max_length=1,
        db_index=True,
        choices=FALLBACK_CHOICES,
        default=FALLBACK_FAIL,
        help_text=_('What do do when media in your source profile is not available')
    )

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _('Source')
        verbose_name_plural = _('Sources')


def get_media_thumb_path(instance, filename):
    fileid = str(instance.uuid)
    filename = f'{fileid.lower()}.{instance.image_type.lower()}'
    prefix = fileid[:2]
    return os.path.join('thumbs', prefix, filename)


class Media(models.Model):
    '''
        Media is a single piece of media, such as a single YouTube video linked to a
        Source.
    '''

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
    url = models.URLField(
        _('url'),
        db_index=True,
        help_text=_('URL of the media')
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
        help_text=_('Width (X) of the thumbnail')
    )
    thumb_height = models.PositiveSmallIntegerField(
        _('thumb height'),
        blank=True,
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
