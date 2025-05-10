from ..choices import Val, YouTube_SourceType


_srctype_dict = lambda n: dict(zip( YouTube_SourceType.values, (n,) * len(YouTube_SourceType.values) ))


def _nfo_element(nfo, label, text, /, *, attrs={}, tail='\n', char=' ', indent=2):
    element = nfo.makeelement(label, attrs)
    element.text = text
    element.tail = tail + (char * indent)
    return element

