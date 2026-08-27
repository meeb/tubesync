import logging


default_formatter = logging.Formatter(
    '%(asctime)s [%(name)s/%(levelname)s] %(message)s'
)

default_handler = logging.StreamHandler()
default_handler.setFormatter(default_formatter)
default_handler.setLevel(logging.INFO)

__all__ = ['default_formatter', 'default_handler']
