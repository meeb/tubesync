from ..choices import Val, YouTube_SourceType # noqa


_srctype_dict = lambda n: dict(zip( YouTube_SourceType.values, (n,) * len(YouTube_SourceType.values) ))


def _nfo_element(nfo, label, text, /, *, attrs={}, tail='\n', char=' ', indent=2):
    element = nfo.makeelement(label, attrs)
    element.text = text
    element.tail = tail + (char * indent)
    return element

def directory_and_stem(arg_path, /, all_suffixes=False):
    filepath = Path(arg_path)
    stem = Path(filepath.stem)
    while all_suffixes and stem.suffixes and '' != stem.suffix:
        stem = Path(stem.stem)
    stem = str(stem)
    return (filepath.parent, stem,)

