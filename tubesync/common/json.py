from datetime import datetime
from django.core.serializers.json import DjangoJSONEncoder
from yt_dlp.utils import LazyList


class JSONEncoder(DjangoJSONEncoder):
    item_separator = ','
    key_separator = ':'

    def default(self, obj):
        try:
            iterable = iter(obj)
        except TypeError:
            pass
        else:
            return list(iterable)
        return super().default(obj)


def json_serial(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, LazyList):
        return list(obj)
    raise TypeError(f'Type {type(obj)} is not json_serial()-able')

