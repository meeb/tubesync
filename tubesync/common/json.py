from django.core.serializers.json import DjangoJSONEncoder


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

