
from django import forms, VERSION as DJANGO_VERSION
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from .models import Source


if DJANGO_VERSION[0:3] < (5, 0, 0):
    _assume_scheme = dict()
else:
    # Silence RemovedInDjango60Warning
    _assume_scheme = dict(assume_scheme='http')

SourceForm = forms.modelform_factory(
    Source,
    # manual ordering
    fields = (
        'source_type', 'key', 'name', 'directory', 'filter_text', 'filter_text_invert', 'filter_seconds', 'filter_seconds_min',
        'media_format', 'target_schedule', 'index_schedule', 'index_videos', 'index_streams', 'download_media',
        'download_cap', 'delete_old_media', 'days_to_keep', 'source_resolution', 'source_vcodec', 'source_acodec',
        'prefer_60fps', 'prefer_hdr', 'fallback', 'delete_removed_media', 'delete_files_on_disk', 'copy_channel_images',
        'copy_thumbnails', 'write_nfo', 'write_json', 'embed_metadata', 'embed_thumbnail',
        'enable_sponsorblock', 'sponsorblock_categories', 'write_subtitles', 'auto_subtitles', 'sub_langs',
    ),
    widgets = {
        'target_schedule': forms.DateTimeInput(
            attrs={'type': 'datetime-local'},
        ),
    },
)

def source_clean_media_format(self):
    data = self.cleaned_data.get('media_format', '').strip()
    return data or getattr(settings, 'MEDIA_FORMATSTR', settings.MEDIA_FORMATSTR_DEFAULT)

SourceForm.clean_media_format = source_clean_media_format

class ValidateSourceForm(forms.Form):

    source_url = forms.URLField(
        label=_('Source URL'),
        required=True,
        widget=forms.URLInput(attrs={'placeholder': 'https://www.youtube.com/@channelname'}),
        **_assume_scheme,
    )


class ConfirmDeleteSourceForm(forms.Form):

    delete_media = forms.BooleanField(
        label=_('Also delete downloaded media'),
        required=False
    )


class RedownloadMediaForm(forms.Form):

    pass


class SkipMediaForm(forms.Form):

    pass


class EnableMediaForm(forms.Form):

    pass


class ResetTasksForm(forms.Form):

    pass


class ScheduleTaskForm(forms.Form):

    now = forms.DateTimeField(
        label=_('The current date and time'),
        required=False,
        widget=forms.DateTimeInput(
            attrs={
                'type': 'datetime-local',
                'readonly': 'true',
            },
        ),
    )

    when = forms.DateTimeField(
        label=_('When the task should run'),
        required=True,
        widget=forms.DateTimeInput(
            attrs={'type': 'datetime-local'},
        ),
    )


class ConfirmDeleteMediaServerForm(forms.Form):

    pass


_media_server_type_label = 'Jellyfin'
class JellyfinMediaServerForm(forms.Form):

    host = forms.CharField(
        label=_(f'Host name or IP address of the {_media_server_type_label} server'),
        required=True,
    )
    port = forms.IntegerField(
        label=_(f'Port number of the {_media_server_type_label} server'),
        required=True,
        initial=8096,
    )
    use_https = forms.BooleanField(
        label=_('Connect over HTTPS'),
        required=False,
        initial=False,
    )
    verify_https = forms.BooleanField(
        label=_('Verify the HTTPS certificate is valid if connecting over HTTPS'),
        required=False,
        initial=True,
    )
    token = forms.CharField(
        label=_(f'{_media_server_type_label} token'),
        required=True,
    )
    libraries = forms.CharField(
        label=_(f'Comma-separated list of {_media_server_type_label} library IDs to update'),
        required=False,
    )


_media_server_type_label = 'Plex'
class PlexMediaServerForm(forms.Form):

    host = forms.CharField(
        label=_('Host name or IP address of the Plex server'),
        required=True
    )
    port = forms.IntegerField(
        label=_('Port number of the Plex server'),
        required=True,
        initial=32400
    )
    use_https = forms.BooleanField(
        label=_('Connect over HTTPS'),
        required=False,
        initial=True,
    )
    verify_https = forms.BooleanField(
        label=_('Verify the HTTPS certificate is valid if connecting over HTTPS'),
        required=False
    )
    token = forms.CharField(
        label=_('Plex token'),
        required=True
    )
    libraries = forms.CharField(
        label=_('Comma-separated list of Plex library IDs to update, such as "9" or "4,6"')
    )
