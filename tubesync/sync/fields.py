from collections import namedtuple
from typing import Any, Dict
from django import forms
from django.db import connection, models
from django.utils.translation import gettext_lazy as _


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
    # perhaps set the 'selected' attribute too?
    # checked_attribute = {'checked': True, 'selected': True}

    def get_context(self, name: str, value: Any, attrs) -> Dict[str, Any]:
        data = value
        select_all = False
        if isinstance(data, CommaSepChoice):
            select_all = (data.allow_all and data.all_choice in data.selected_choices)
            value = list(data.selected_choices)
        context = super().get_context(name, value, attrs)
        widget = context['widget']
        options = widget['optgroups']
        # This is a new key in widget
        widget['multipleChoiceProperties'] = list()
        for _group, single_option_list, _index in options:
            for option in single_option_list:
                option['selected'] |= select_all
                widget['multipleChoiceProperties'].append(option)

        return { 'widget': widget }


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
        self.separator = str(separator)
        self.possible_choices = possible_choices or choices
        self.selected_choices = list()
        self.allow_all = allow_all
        self.all_label = all_label
        self.all_choice = all_choice
        self.choices = self.get_all_choices()
        super().__init__(*args, **kwargs)
        self.validators.clear()


    # Override these functions to prevent unwanted behaviors
    def to_python(self, value):
        saved_value = None
        arg_was_none = True if value is None else False
        if isinstance(value, CommaSepChoice):
            return value.selected_choices
        if isinstance(value, list) and len(value) > 0 and value[0].startswith('CommaSepChoice('):
            saved_value = value
            value = ''.join(value)
        if isinstance(value, str) and value.startswith('CommaSepChoice('):
            r = value.replace('CommaSepChoice(', 'dict(', 1)
            try:
                o = eval(r)
            except Exception:
                pass
            else:
                return o.get('selected_choices')
        if arg_was_none:
            value = None
        elif saved_value is not None:
            value = saved_value
        self.log.debug(f'CommaSepChoiceField: to_python: was called with: {value!r}')
        return value

    def get_internal_type(self):
        return super().get_internal_type()


    # standard functions for this class
    def deconstruct(self):
        # set it back to the default for models.Field
        # this way it is never in the returned values
        self.choices = None
        name, path, args, kwargs = super().deconstruct()
        self.choices = self.get_all_choices()
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

    def formfield(self, **kwargs):
        # This is a fairly standard way to set up some defaults
        # while letting the caller override them.
        defaults = {
            'form_class': self.form_class,
            # 'choices_form_class': self.form_class,
            'widget': self.widget,
            # use a callable for choices
            'choices': self.get_all_choices,
            'label': '',
            'required': False,
        }
        # Keep the part from CharField we want,
        # then call Field to skip the 'max_length' entry.
        db_empty_string_as_null = connection.features.interprets_empty_strings_as_nulls
        if self.null and not db_empty_string_as_null:
            defaults['empty_value'] = None
        defaults.update(kwargs)
        return models.Field.formfield(self, **defaults)
        # This is a more compact way to do the same thing
        # return super().formfield(**{
        #     'form_class': self.form_class,
        #     **kwargs,
        # })

    def from_db_value(self, value, expression, connection):
        '''
        Create a data structure to be used in Python code.
        '''
        # possibly not useful?
        if isinstance(value, CommaSepChoice):
            value = value.selected_choices
        # normally strings
        if isinstance(value, str) and len(value) > 0:
            value = value.split(self.separator)
        # empty string and None, or whatever
        if not isinstance(value, list):
            value = list()
        self.selected_choices = value
        args_dict = {key: self.__dict__[key] for key in CommaSepChoice._fields}
        return CommaSepChoice(**args_dict)

    def get_prep_value(self, value):
        '''
        Create a value to be stored in the database.
        '''
        data = value
        if not isinstance(data, CommaSepChoice):
            # The data was lost; we can regenerate it.
            args_dict = {key: self.__dict__[key] for key in CommaSepChoice._fields}
            args_dict['selected_choices'] = list(value)
            # setting a string manually should not result in characters
            if isinstance(value, str) and len(value) > 0:
                args_dict['selected_choices'] = value.split(self.separator)
            data = CommaSepChoice(**args_dict)
        value = data.selected_choices
        s_value = super().get_prep_value(value)
        if set(s_value) != set(value):
            self.log.warn(f'CommaSepChoiceField:get_prep_value: values did not match. '
                          f'CommaSepChoiceField({value}) versus CharField({s_value})')
        return self.__class__._tuple__str__(data)

    
    # extra functions not used by any parent classes
    @staticmethod
    def _tuple__str__(data):
        if not isinstance(data, CommaSepChoice):
            return data
        value = data.selected_choices
        if not isinstance(value, list):
            return ''
        if data.all_choice in value:
            return data.all_choice
        ordered_unique = list(dict.fromkeys(value))
        return data.separator.join(ordered_unique)

    def get_all_choices(self):
        choice_list = list()
        if self.possible_choices is None:
            return choice_list
        if self.allow_all:
            choice_list.append((self.all_choice, _(self.all_label)))

        for choice in self.possible_choices:
            choice_list.append(choice)

        return choice_list


CommaSepChoice.__str__ = CommaSepChoiceField._tuple__str__

