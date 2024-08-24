#!/usr/bin/env python3


import os
import sys


def main():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tubesync.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError('Unable to import django, is it installed?') from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
