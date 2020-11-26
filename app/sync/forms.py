
from django import forms


class ValidateSourceForm(forms.Form):

    source_type = forms.CharField(
        max_length=1,
        required=True,
        widget=forms.HiddenInput()
    )
    source_url = forms.URLField(
        label='Source URL',
        required=True
    )
