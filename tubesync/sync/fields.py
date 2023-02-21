from django.forms import MultipleChoiceField,  CheckboxSelectMultiple, Field, TypedMultipleChoiceField
from django.db import models
from typing import Any, Optional, Dict
from django.utils.translation import gettext_lazy as _

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
class CommaSepChoiceField(models.Field):
    "Implements comma-separated storage of lists"

    def __init__(self, separator=",", possible_choices=(("","")), all_choice="", all_label="All", allow_all=False, *args, **kwargs):
        self.separator = separator
        self.possible_choices = possible_choices
        self.selected_choices = []
        self.allow_all = allow_all
        self.all_label = all_label
        self.all_choice = all_choice
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        if self.separator != ",":
            kwargs['separator'] = self.separator
        kwargs['possible_choices'] = self.possible_choices
        return name, path, args, kwargs

    def db_type(self, connection):
        return 'text'

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
        #del defaults.required
        return super().formfield(**defaults)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        # Only include kwarg if it's not the default
        if self.separator != ",":
            kwargs['separator'] = self.separator
        return name, path, args, kwargs

    def from_db_value(self, value, expr, conn):
        if value is None:
            self.selected_choices = []
        else:
            self.selected_choices = value.split(",")

        return self

    def get_prep_value(self, value):
        if value is None:
            return ""
        if not isinstance(value,list):
            return ""

        if self.all_choice not in value:
            return ",".join(value)
        else:
            return self.all_choice

    def get_text_for_value(self, val):
        fval = [i for i in self.possible_choices if i[0] == val]
        if len(fval) <= 0:
            return []
        else:
            return fval[0][1]
