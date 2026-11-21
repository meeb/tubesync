from django.db import models
from django.utils.translation import gettext_lazy as _
from .codec import Codec


class Subtitle(models.Model):
    '''
        Subtitle is a subtitle track available for a media item.
    '''

    extension = models.CharField(
        _('extension'),
        max_length=8,
        blank=False,
        null=False,
        help_text=_('The file extension of the subtitle (e.g. vtt, srt)'),
    )
    language = models.CharField(
        _('language'),
        max_length=16,
        blank=False,
        null=False,
        help_text=_('BCP-47 language tag of the subtitle track (e.g. en-US)'),
    )
    original_language = models.CharField(
        _('original language'),
        max_length=16,
        blank=False,
        null=True,
        default=None,
        help_text=_('BCP-47 language tag of the source language, or NULL if unknown'),
    )
    machine_generated = models.BooleanField(
        _('machine generated'),
        default=False,
        help_text=_('Whether the subtitle was automatically generated'),
    )
    codec = models.ForeignKey(
        Codec,
        on_delete=models.SET_NULL,
        null=True,
        related_name='subtitles',
        help_text=_('The codec used for this subtitle track'),
    )

    class Meta:
        verbose_name = _('Subtitle')
        verbose_name_plural = _('Subtitles')
        unique_together = (
            ('language', 'extension'),
        )

    def __str__(self):
        return f'{self.extension} / {self.language}'

