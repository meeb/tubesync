import logging

logger = lambda name=None: logging.getLogger(
    __name__.rsplit('.', 1)[0] if name is None else name
)

__all__ = ['logger']
