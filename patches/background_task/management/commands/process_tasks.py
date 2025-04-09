# -*- coding: utf-8 -*-
import logging
import random
import sys
import time

from django import VERSION
from django.core.management.base import BaseCommand
from django.utils import autoreload

from background_task.tasks import tasks, autodiscover
from background_task.utils import SignalManager
from django.db import close_old_connections as close_connection


logger = logging.getLogger(__name__)


def _configure_log_std():
    class StdOutWrapper(object):
        def write(self, s):
            logger.info(s)

    class StdErrWrapper(object):
        def write(self, s):
            logger.error(s)
    sys.stdout = StdOutWrapper()
    sys.stderr = StdErrWrapper()


class Command(BaseCommand):
    help = 'Run tasks that are scheduled to run on the queue'

    # Command options are specified in an abstract way to enable Django < 1.8 compatibility
    OPTIONS = (
        (('--duration', ), {
            'action': 'store',
            'dest': 'duration',
            'type': int,
            'default': 0,
            'help': 'Run task for this many seconds (0 or less to run forever) - default is 0',
        }),
        (('--sleep', ), {
            'action': 'store',
            'dest': 'sleep',
            'type': float,
            'default': 5.0,
            'help': 'Sleep for this many seconds before checking for new tasks (if none were found) - default is 5',
        }),
        (('--queue', ), {
            'action': 'store',
            'dest': 'queue',
            'help': 'Only process tasks on this named queue',
        }),
        (('--log-std', ), {
            'action': 'store_true',
            'dest': 'log_std',
            'help': 'Redirect stdout and stderr to the logging system',
        }),
        (('--dev', ), {
            'action': 'store_true',
            'dest': 'dev',
            'help': 'Auto-reload your code on changes. Use this only for development',
        }),
    )

    if VERSION < (1, 8):
        from optparse import make_option
        option_list = BaseCommand.option_list + tuple([make_option(*args, **kwargs) for args, kwargs in OPTIONS])

    # Used in Django >= 1.8
    def add_arguments(self, parser):
        for (args, kwargs) in self.OPTIONS:
            parser.add_argument(*args, **kwargs)

    def __init__(self, *args, **kwargs):
        super(Command, self).__init__(*args, **kwargs)
        self.sig_manager = None
        self._tasks = tasks

    def run(self, *args, **options):
        duration = options.get('duration', 0)
        sleep = options.get('sleep', 5.0)
        queue = options.get('queue', None)
        log_std = options.get('log_std', False)
        is_dev = options.get('dev', False)
        sig_manager = self.sig_manager

        if is_dev:
            # raise last Exception is exist
            autoreload.raise_last_exception()

        if log_std:
            _configure_log_std()

        autodiscover()

        start_time = time.time()

        while (duration <= 0) or (time.time() - start_time) <= duration:
            if sig_manager.kill_now:
                # shutting down gracefully
                break

            if not self._tasks.run_next_task(queue):
                # there were no tasks in the queue, let's recover.
                close_connection()
                logger.debug('waiting for tasks')
                time.sleep(sleep)
            else:
                # there were some tasks to process, let's check if there is more work to do after a little break.
                time.sleep(random.uniform(sig_manager.time_to_wait[0], sig_manager.time_to_wait[1]))
        self._tasks._pool_runner._pool.close()

    def handle(self, *args, **options):
        is_dev = options.get('dev', False)
        self.sig_manager = SignalManager()
        if is_dev:
            reload_func = autoreload.run_with_reloader
            if VERSION < (2, 2):
                reload_func = autoreload.main
            reload_func(self.run, *args, **options)
        else:
            self.run(*args, **options)
