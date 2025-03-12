from django import template
from django.template.defaultfilters import filesizeformat


register = template.Library()


@register.filter(is_safe=True)
def bytesformat(input):
    output = filesizeformat(input)
    if not (output and output.endswith('B', -1)):
        return output
    return output[: -1 ] + 'iB'

@register.filter(is_safe=False)
def sub(value, arg):
    """Subtract the arg from the value."""
    try:
        return int(value) - int(arg)
    except (ValueError, TypeError):
        try:
            return value - arg
        except Exception:
            return ""

