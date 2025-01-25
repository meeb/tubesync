from django import template
from django.template.defaultfilters import filesizeformat


register = template.Library()


@register.filter(is_safe=True)
def bytesformat(input):
    output = filesizeformat(input)
    if not (output and output.endswith('B')):
        return output
    return output.replace('B', 'iB', -1)

