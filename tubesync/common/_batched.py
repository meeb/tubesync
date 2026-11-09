import itertools
import operator


_NATIVE = getattr(itertools, 'batched', None)
_NATIVE_STRICT = None
if _NATIVE is not None:
    try:
        _NATIVE((), 1, strict=False)
        _NATIVE_STRICT = True
    except TypeError:
        _NATIVE_STRICT = False


def _batched(it, n, strict):
    def f():
        islice = itertools.islice
        return tuple(islice(it, n))
    for batch in iter(f, ()):
        if strict and n > len(batch):
            raise ValueError('batched(): incomplete batch')
        yield batch


def batched(iterable, n, /, *, strict=False):
    # slightly better than: n = int(n)
    n = operator.index(n)
    if n < 1:
        raise ValueError('n must be at least one')

    kwargs = dict()
    use_native = _NATIVE is not None
    if _NATIVE_STRICT:
        kwargs['strict'] = strict
    elif use_native:
        use_native = not strict
    if use_native:
        return _NATIVE(iterable, n, **kwargs)
    # calling iter immediately preserves error timing
    it = iter(iterable)
    return _batched(it, n, strict)
