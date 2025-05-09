from django import db
from django.utils.translation import gettext_lazy as _
from ..choices import Val, MediaServerType


class MediaServer(db.models.Model):
    '''
        A remote media server, such as a Plex server.
    '''

    ICONS = {
        Val(MediaServerType.JELLYFIN): '<i class="fas fa-server"></i>',
        Val(MediaServerType.PLEX): '<i class="fas fa-server"></i>',
    }
    HANDLERS = MediaServerType.handlers_dict()

    server_type = db.models.CharField(
        _('server type'),
        max_length=1,
        db_index=True,
        choices=MediaServerType.choices,
        default=MediaServerType.PLEX,
        help_text=_('Server type'),
    )
    host = db.models.CharField(
        _('host'),
        db_index=True,
        max_length=200,
        help_text=_('Hostname or IP address of the media server'),
    )
    port = db.models.PositiveIntegerField(
        _('port'),
        db_index=True,
        help_text=_('Port number of the media server'),
    )
    use_https = db.models.BooleanField(
        _('use https'),
        default=False,
        help_text=_('Connect to the media server over HTTPS'),
    )
    verify_https = db.models.BooleanField(
        _('verify https'),
        default=True,
        help_text=_('If connecting over HTTPS, verify the SSL certificate is valid'),
    )
    options = db.models.JSONField(
        _('options'),
        blank=False,
        null=True,
        help_text=_('Options for the media server'),
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

    def validate(self):
        return self.handler.validate()

    def update(self):
        return self.handler.update()

    def get_help_html(self):
        return self.handler.HELP
