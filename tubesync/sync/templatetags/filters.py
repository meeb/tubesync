from django import template
from django.template.defaultfilters import filesizeformat


register = template.Library()


@register.filter(is_safe=True)
def bytesformat(input):
    output = filesizeformat(input)
    if not (output and output.endswith('B', -1)):
        return output
    return output[: -1 ] + output[ -1 :].replace('B', 'iB', 1)

