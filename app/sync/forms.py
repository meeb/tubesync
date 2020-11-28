
from django import forms
from django.utils.translation import gettext_lazy as _


class ValidateSourceForm(forms.Form):

    source_type = forms.CharField(
        max_length=1,
        required=True,
        widget=forms.HiddenInput()
    )
    source_url = forms.URLField(
        label=_('Source URL'),
        required=True
    )


class ConfirmDeleteSourceForm(forms.Form):

    delete_media = forms.BooleanField(
        label=_('Also delete downloaded media'),
        required=False
    )
