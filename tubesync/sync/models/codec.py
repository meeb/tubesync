import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _
from ..choices import AssetType, AssetCodec


class Codec(models.Model):
    '''
        Codec is a supported codec for a given asset type.
    '''

    uuid = models.UUIDField(
        _('uuid'),
        primary_key=True,
        editable=False,
        default=uuid.uuid4,
        help_text=_('UUID of the codec'),
    )
    asset_type = models.CharField(
        _('asset type'),
        max_length=16,
        db_index=True,
        choices=AssetType.choices,
        help_text=_('The type of asset this codec is used for'),
    )
    codec = models.CharField(
        _('codec'),
        max_length=16,
        db_index=True,
        choices=AssetCodec.choices,
        help_text=_('The codec name'),
    )

    def __str__(self):
        return f'{self.asset_type} / {self.codec}'

    class Meta:
        verbose_name = _('Codec')
        verbose_name_plural = _('Codecs')
        unique_together = (
            ('asset_type', 'codec'),
        )