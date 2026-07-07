import logging
from os import getenv

def level_from_environment(env_var, default=None):
    levels_dict = logging.getLevelNamesMapping()
    if default is None:
        default = 'INFO'
    level_string = getenv(env_var, default)
    level_number = levels_dict.get(level_string.upper())
    if not (level_number and isinstance(level_number, int)):
        level_number = levels_dict.get(default.upper(), 0)
    return logging.getLevelName(level_number)
