from collections import namedtuple
from functools import lru_cache
from typing import Any, Dict
from django import forms
from django.db import models
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


CommaSepChoice = namedtuple(
    'CommaSepChoice', [
        'allow_all',
        'all_choice',
        'all_label',
        'possible_choices',
        'selected_choices',
        'separator',
    ],
    defaults = (
        False,
        None,
        'All',
        list(),
        list(),
        ',',
    ),
)

# this is a form field!
class CustomCheckboxSelectMultiple(forms.CheckboxSelectMultiple):
    template_name = 'widgets/checkbox_select.html'
    option_template_name = 'widgets/checkbox_option.html'

    def get_context(self, name: str, value: Any, attrs) -> Dict[str, Any]:
        data = value
        select_all = False
        if isinstance(data, CommaSepChoice):
            select_all = (data.allow_all and data.all_choice in data.selected_choices)
            value = data.selected_choices
        ctx = super().get_context(name, value, attrs)['widget']
        options = ctx["optgroups"]
        ctx["multipleChoiceProperties"] = list()
        for _group, single_option_list, _index in options:
            for option in single_option_list:
                option["selected"] |= select_all
                ctx["multipleChoiceProperties"].append(option)

        return { 'widget': ctx }


# this is a database field!
class CommaSepChoiceField(models.CharField):
    '''
    Implements comma-separated storage of lists
    '''

    form_class = forms.MultipleChoiceField
    widget = CustomCheckboxSelectMultiple
    from common.logger import log

    def __init__(self, *args, separator=",", possible_choices=(("","")), all_choice="", all_label="All", allow_all=False, **kwargs):
        kwargs.setdefault('max_length', 128)
        super().__init__(*args, **kwargs)
        self.separator = str(separator)
        self.possible_choices = possible_choices
        self.selected_choices = list()
        self.allow_all = allow_all
        self.all_label = all_label
        self.all_choice = all_choice
        self.choices = self.get_all_choices()
        self.validators.clear()


    # Override these functions to prevent unwanted behaviors
    def to_python(self, value):
        self.log.debug(f'to_py:1: {type(value)} {repr(value)}')
        return value

    def get_internal_type(self):
        return super().get_internal_type()

    # maybe useful?
    def value_to_string(self, obj):
        return self.value_from_object(obj)


    # standard functions for this class
    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        if ',' != self.separator:
            kwargs['separator'] = self.separator
        kwargs['possible_choices'] = self.possible_choices
        if self.allow_all:
            kwargs['allow_all'] = self.allow_all
            if self.all_choice:
                kwargs['all_choice'] = self.all_choice
            if 'All' != self.all_label:
                kwargs['all_label'] = self.all_label
        return name, path, args, kwargs

    # maybe useful?
    def check(self, **kwargs):
        errors = super().check(**kwargs)
        return errors

    # maybe useful?
    def validate(self, value, model_instance):
        super().validate(value, model_instance)

    def formfield(self, **kwargs):
        # This is a fairly standard way to set up some defaults
        # while letting the caller override them.
        defaults = {
            'form_class': self.form_class,
            # 'choices_form_class': self.form_class,
            'widget': self.widget,
            'choices': self.get_all_choices(),
            'label': '',
            'required': False,
        }
        defaults.update(kwargs)
        return super().formfield(**defaults)
        # This is a more compact way to do the same thing
        # return super().formfield(**{
        #     'form_class': self.form_class,
        #     **kwargs,
        # })

    @lru_cache(maxsize=10)
    def from_db_value(self, value, expression, connection):
        '''
        Create a data structure to be used in Python code.

        This is called quite often with the same input,
        because the database value doesn't change often.
        So, it's being cached to prevent excessive logging.
        '''
        self.log.debug(f'fdbv:1: {type(value)} {repr(value)}')
        if isinstance(value, str) and len(value) > 0:
            value = value.split(self.separator)
        if not isinstance(value, list):
            value = list()
        self.selected_choices = value
        args_dict = {key: self.__dict__[key] for key in CommaSepChoice._fields}
        return CommaSepChoice(**args_dict)

    def get_prep_value(self, value):
        '''
        Create a value to be stored in the database.
        '''
        self.log.debug(f'gpv:1: {type(value)} {repr(value)}')
        s_value = super().get_prep_value(value)
        self.log.debug(f'gpv:2: {type(s_value)} {repr(s_value)}')
        data = value
        if isinstance(value, CommaSepChoice):
            value = value.selected_choices
        if not isinstance(value, list):
            return ''
        if data.all_choice in value:
            return data.all_choice
        return data.separator.join(value)

    # extra functions not used by any parent classes
    def get_all_choices(self):
        choice_list = list()
        if self.possible_choices is None:
            return choice_list
        if self.allow_all:
            choice_list.append((self.all_choice, _(self.all_label)))

        for choice in self.possible_choices:
            choice_list.append(choice)

        return choice_list

