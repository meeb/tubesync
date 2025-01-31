from django.forms import MultipleChoiceField,  CheckboxSelectMultiple, Field, TypedMultipleChoiceField
from django.db import models
from typing import Any, Optional, Dict
from django.utils.translation import gettext_lazy as _


# as stolen from:
# - https://wiki.sponsor.ajay.app/w/Types
# - https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/postprocessor/sponsorblock.py
#
# The spacing is a little odd, it is for easy copy/paste selection.
# Please don't change it.
# Every possible category fits in a string < 128 characters
class SponsorBlock_Category(models.TextChoices):
    SPONSOR = 'sponsor', _( 'Sponsor' )
    INTRO = 'intro', _( 'Intermission/Intro Animation' )
    OUTRO = 'outro', _( 'Endcards/Credits' )
    SELFPROMO = 'selfpromo', _( 'Unpaid/Self Promotion' )
    PREVIEW = 'preview', _( 'Preview/Recap' )
    FILLER = 'filler', _( 'Filler Tangent' )
    INTERACTION = 'interaction', _( 'Interaction Reminder' )
    MUSIC_OFFTOPIC = 'music_offtopic', _( 'Non-Music Section' )


# this is a form field!
class CustomCheckboxSelectMultiple(CheckboxSelectMultiple):
    template_name = 'widgets/checkbox_select.html'
    option_template_name = 'widgets/checkbox_option.html'

    def get_context(self, name: str, value: Any, attrs) -> Dict[str, Any]:
        ctx = super().get_context(name, value, attrs)['widget']
        ctx["multipleChoiceProperties"] = []
        for _group, options, _index in ctx["optgroups"]:
            for option in options:
                if not isinstance(value,str) and not isinstance(value,list) and ( option["value"] in value.selected_choices or ( value.allow_all and value.all_choice in value.selected_choices ) ):
                    checked = True
                else:
                    checked = False

                ctx["multipleChoiceProperties"].append({
                    "template_name": option["template_name"],
                    "type": option["type"],
                    "value": option["value"],
                    "label": option["label"],
                    "name": option["name"],
                    "checked": checked})

        return { 'widget': ctx }

# this is a database field!
class CommaSepChoiceField(models.CharField):
    "Implements comma-separated storage of lists"

    def __init__(self, *args, separator=",", possible_choices=(("","")), all_choice="", all_label="All", allow_all=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.separator = str(separator)
        self.possible_choices = possible_choices
        self.selected_choices = []
        self.allow_all = allow_all
        self.all_label = all_label
        self.all_choice = all_choice

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        if ',' != self.separator:
            kwargs['separator'] = self.separator
        kwargs['possible_choices'] = self.possible_choices
        return name, path, args, kwargs

    def get_internal_type(self):
        return super().get_internal_type()

    def get_my_choices(self):
        choiceArray = []
        if self.possible_choices is None:
            return choiceArray
        if self.allow_all:
            choiceArray.append((self.all_choice, _(self.all_label)))

        for t in self.possible_choices:
            choiceArray.append(t)

        return choiceArray

    def formfield(self, **kwargs):
        # This is a fairly standard way to set up some defaults
        # while letting the caller override them.
        defaults = {'form_class': MultipleChoiceField, 
                    'choices': self.get_my_choices,
                    'widget': CustomCheckboxSelectMultiple,
                    'label': '',
                    'required': False}
        defaults.update(kwargs)
        # CharField calls with an extra 'max_length' that we must avoid.
        return models.Field.formfield(self, **defaults)

    def from_db_value(self, value, expr, conn):
        if 0 == len(value) or value is None:
            self.selected_choices = []
        else:
            self.selected_choices = value.split(self.separator)

        return self

    def get_prep_value(self, value):
        if value is None:
            return ""
        if not isinstance(value,list):
            return ""

        if self.all_choice not in value:
            return self.separator.join(value)
        else:
            return self.all_choice

    def pre_save(self, model_instance, add=False):
        obj = super().pre_save(model_instance, add)
        if isinstance(obj, str):
            self.from_db_value(obj, None, None)
        selected = self.selected_choices
        return self.get_prep_value(selected)

    def get_text_for_value(self, val):
        fval = [i for i in self.possible_choices if i[0] == val]
        if len(fval) <= 0:
            return []
        else:
            return fval[0][1]
