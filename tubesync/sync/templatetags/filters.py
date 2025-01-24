from django import template
from django.template.defaultfilters import filesizeformat

register = template.Library()

@register.filter(is_safe=True)
def bytesformat(input):
    intermediate = filesizeformat(input)
    return intermediate.replace('B', 'iB')

