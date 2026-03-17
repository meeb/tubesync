#!/usr/bin/env python3

"""
This script is the entry point for the Django management command runner.
It sets up the Django environment and executes the specified command.
"""

import os
import sys
from django.core.exceptions import ImportError

def import_django() -> None:
    """
    Import the Django core management module and set the DJANGO_SETTINGS_MODULE environment variable.
    
    Raises:
        ImportError: If Django is not installed or cannot be imported.
    """
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tubesync.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError('Unable to import django, is it installed?') from exc


def run_management_command() -> None:
    """
    Execute the specified management command using the execute_from_command_line function.
    
    Args:
        sys.argv (list): The list of command-line arguments.
    """
    import_django()
    execute_from_command_line(sys.argv)


def main() -> None:
    """
    The main entry point for the script.
    
    This function checks if the script is being run directly (not imported) and calls the run_management_command function.
    """
    if __name__ == '__main__':
        run_management_command()


if __name__ == '__main__':
    main()