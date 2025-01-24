from django import template
from django.template.defaultfilters import filesizeformat, stringfilter


register = template.Library()


@register.filter(is_safe=True)
@stringfilter
def fixB(input):
    return input.replace('B', 'iB')


@register.filter(is_safe=True)
def bytesformat(input):
    output = filesizeformat(input)
    if not (output and output.endswith('B')):
        return output
    return fixB(output)

