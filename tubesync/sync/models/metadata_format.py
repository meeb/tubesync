import uuid
from common.json import JSONEncoder
from django import db
from django.utils.translation import gettext_lazy as _
#from .metadata import Metadata
from . import Metadata

class MetadataFormat(db.models.Model):
    '''
        A format from the Metadata for an indexed `Media` item.
    '''
    class Meta:
        db_table = f'{Metadata._meta.db_table}_format'
        verbose_name = _('Format from Media Metadata')
        verbose_name_plural = _('Formats from Media Metadata')
        unique_together = (
            ('metadata', 'site', 'key', 'number'),
        )
        ordering = ['site', 'key', 'number']

    uuid = db.models.UUIDField(
        _('uuid'),
        primary_key=True,
        editable=False,
        default=uuid.uuid4,
        help_text=_('UUID of the format'),
    )
    metadata = db.models.ForeignKey(
        Metadata,
        # on_delete=models.DO_NOTHING,
        on_delete=db.models.CASCADE,
        related_name='format',
        help_text=_('Metadata the format belongs to'),
        null=False,
    )
    site = db.models.CharField(
        _('site'),
        max_length=256,
        blank=True,
        db_index=True,
        null=False,
        default='Youtube',
        help_text=_('Site from which the format is available'),
    )
    key = db.models.CharField(
        _('key'),
        max_length=256,
        blank=True,
        db_index=True,
        null=False,
        default='',
        help_text=_('Media identifier at the site from which this format is available'),
    )
    number = db.models.PositiveIntegerField(
        _('number'),
        blank=False,
        null=False,
        help_text=_('Ordering number for this format'),
    )
    value = db.models.JSONField(
        _('value'),
        encoder=JSONEncoder,
        null=False,
        default=dict,
        help_text=_('JSON metadata format object'),
    )


    def __str__(self):
        template = '#{:n} "{}" from {}: {}'
        return template.format(
            self.number,
            self.key,
            self.site,
            self.value.get('format') or self.value.get('format_id'),
        )
