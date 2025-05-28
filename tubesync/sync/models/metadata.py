import uuid
from common.json import JSONEncoder
from common.timestamp import timestamp_to_datetime
from common.utils import django_queryset_generator as qs_gen
from django import db
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from .media import Media, Source


class Metadata(db.models.Model):
    '''
        Metadata for an indexed `Media` item.
    '''
    class Meta:
        db_table = 'sync_media_metadata'
        verbose_name = _('Metadata about Media')
        verbose_name_plural = _('Metadata about Media')
        unique_together = (
            ('media', 'site', 'key'),
            ('source', 'site', 'key', ),
        )
        get_latest_by = ["-retrieved", "-created"]

    uuid = db.models.UUIDField(
        _('uuid'),
        primary_key=True,
        editable=False,
        default=uuid.uuid4,
        help_text=_('UUID of the metadata'),
    )
    source = db.models.ForeignKey(
        Source,
        on_delete=db.models.CASCADE,
        related_name="videos",
        related_query_name="video",
        help_text=_('Source from which the video was retrieved'),
        blank=True,
        null=True,
    )
    media = db.models.OneToOneField(
        Media,
        # on_delete=models.DO_NOTHING,
        on_delete=db.models.SET_NULL,
        related_name='new_metadata',
        help_text=_('Media the metadata belongs to'),
        blank=True,
        null=True,
        parent_link=False,
    )
    site = db.models.CharField(
        _('site'),
        max_length=256,
        blank=True,
        db_index=True,
        null=False,
        default='Youtube',
        help_text=_('Site from which the metadata was retrieved'),
    )
    key = db.models.CharField(
        _('key'),
        max_length=256,
        blank=True,
        db_index=True,
        null=False,
        default='',
        help_text=_('Media identifier at the site from which the metadata was retrieved'),
    )
    created = db.models.DateTimeField(
        _('created'),
        auto_now_add=True,
        db_index=True,
        help_text=_('Date and time the metadata was created'),
    )
    retrieved = db.models.DateTimeField(
        _('retrieved'),
        db_index=True,
        default=timezone.now,
        help_text=_('Date and time the metadata was retrieved'),
    )
    uploaded = db.models.DateTimeField(
        _('uploaded'),
        db_index=True,
        null=True,
        help_text=_('Date and time the media was uploaded'),
    )
    published = db.models.DateTimeField(
        _('published'),
        db_index=True,
        null=True,
        help_text=_('Date and time the media was published'),
    )
    value = db.models.JSONField(
        _('value'),
        encoder=JSONEncoder,
        null=False,
        default=dict,
        help_text=_('JSON metadata object'),
    )


    def __str__(self):
        template = '"{}" from {} at: {}'
        return template.format(
            self.key,
            self.site,
            self.retrieved.isoformat(timespec='seconds'),
        )

    @db.transaction.atomic(durable=False)
    def ingest_formats(self, formats=list(), /):
        number = 0
        for number, format in enumerate(formats, start=1):
            mdf, created = self.format.get_or_create(site=self.site, key=self.key, number=number)
            mdf.value = format
            mdf.save()
        if number > 0:
            # delete any numbers we did not overwrite or create
            self.format.filter(site=self.site, key=self.key, number__gt=number).delete()

    @property
    def with_formats(self):
        formats = self.format.all().order_by('number')
        formats_list = [ f.value for f in qs_gen(formats) ]
        metadata = self.value.copy()
        metadata.update(dict(formats=formats_list))
        return metadata

    @db.transaction.atomic(durable=False)
    def ingest_metadata(self, data):
        assert isinstance(data, dict), type(data)

        try:
            self.retrieved = timestamp_to_datetime(
                self.media.get_metadata_first_value(
                    'epoch',
                    arg_dict=data,
                )
            ) or self.created
        except AssertionError:
            self.retrieved = self.created

        try:
            self.published = timestamp_to_datetime(
                self.media.get_metadata_first_value(
                    ('release_timestamp', 'timestamp',),
                    arg_dict=data,
                )
            ) or self.media.published
        except AssertionError:
            self.published = self.media.published

        self.value = data.copy() # try not to have side-effects for the caller
        formats_key = self.media.get_metadata_field('formats')
        formats = self.value.pop(formats_key, list())
        self.uploaded = min(
            self.published,
            self.retrieved,
            self.media.created,
        )
        self.save()
        self.ingest_formats(formats)

        return self.with_formats

