from datetime import datetime
from django.core.serializers.json import DjangoJSONEncoder
from yt_dlp.utils import LazyList


class CustomJSONEncoder(DjangoJSONEncoder):
    """
    Custom JSON encoder for handling datetime and LazyList objects.
    """
    item_separator: str = ','
    key_separator: str = ':'

    def default(self, obj: object) -> object:
        """
        Returns the default JSON representation of the object.

        If the object is iterable, it is converted to a list.
        Otherwise, the default JSON representation is returned.

        :param obj: The object to be JSON-serialized.
        :return: The JSON representation of the object.
        """
        try:
            # Check if the object is iterable
            iterable = iter(obj)
        except TypeError:
            # If not iterable, return the default JSON representation
            pass
        else:
            # If iterable, convert it to a list
            return list(iterable)
        return super().default(obj)


def json_serial(obj: object) -> str:
    """
    Returns a JSON-serializable representation of the object.

    :param obj: The object to be JSON-serialized.
    :return: A JSON-serializable string representation of the object.
    """
    if isinstance(obj, datetime):
        # Convert datetime objects to ISO format
        return obj.isoformat()
    elif isinstance(obj, LazyList):
        # Convert LazyList objects to lists
        return list(obj)
    else:
        # Raise a TypeError for unsupported types
        raise TypeError(f'Type {type(obj)} is not json_serial()-able')