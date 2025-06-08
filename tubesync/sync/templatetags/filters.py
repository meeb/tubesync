from django import template
from django.template.defaultfilters import filesizeformat
from math import ceil


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


@register.filter
def timedelta(value, arg=None, /, *, fmt_2=None):
    if hasattr(value, 'total_seconds') and callable(value.total_seconds):
        seconds_total = value.total_seconds()
    elif hasattr(value, 'seconds'):
        seconds_total = value.seconds + (value.days * 24 * 60 * 60)
    else:
        seconds_total = value

    if arg is None:
        if seconds_total < 1.0:
            return f'{seconds_total:.6f} seconds'
        dynamic_arg = True
        arg = '{hours2}:{minutes2}:{seconds2}'

    if fmt_2 is None:
        fmt_2 = '{:02d}'

    seconds_total = ceil(seconds_total)
    seconds = seconds_total % 60

    minutes_total = seconds_total // 60
    minutes = minutes_total % 60

    hours_total = minutes_total // 60
    hours = hours_total % 24

    days_total = hours_total // 24
    days = days_total % 365

    years_total = days_total // 365
    years = years_total

    if dynamic_arg:
        prefix_years = prefix_days = ''
        if years_total > 0:
            prefix_years = '{years_total} years, '
        if prefix_years and days_total > 0:
            prefix_days = '{days} days, '
        elif days_total > 0:
            prefix_days = '{total_days} days, '
        arg = prefix_years + prefix_days + arg

    return arg.format(**{
        'seconds': seconds,
        'seconds2': fmt_2.format(seconds),
        'minutes': minutes,
        'minutes2': fmt_2.format(minutes),
        'hours': hours,
        'hours2': fmt_2.format(hours),
        'days': days,
        'years': years,
        'seconds_total': seconds_total,
        'minutes_total': minutes_total,
        'hours_total': hours_total,
        'days_total': days_total,
        'years_total': years_total,
    })

