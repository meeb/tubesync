# -*- coding: utf-8 -*-
import signal
import platform

TTW_SLOW = [0.5, 1.5]
TTW_FAST = [0.0, 0.1]


class SignalManager():
    """Manages POSIX signals."""

    kill_now = False
    time_to_wait = TTW_SLOW

    def __init__(self):
        signal.signal(signal.SIGINT, self.exit_gracefully)
        # On Windows, signal() can only be called with:
        # SIGABRT, SIGFPE, SIGILL, SIGINT, SIGSEGV, SIGTERM, or SIGBREAK.
        if platform.system() == 'Windows':
            signal.signal(signal.SIGBREAK, self.exit_gracefully)
        else:
            signal.signal(signal.SIGHUP, self.exit_gracefully)
            signal.signal(signal.SIGUSR1, self.speed_up)
            signal.signal(signal.SIGUSR2, self.slow_down)

    def exit_gracefully(self, signum, frame):
        self.kill_now = True
        # Using interrupt again should raise
        # a KeyboardInterrupt exception.
        signal.signal(signal.SIGINT, signal.SIG_DFL)

    def speed_up(self, signum, frame):
        self.time_to_wait = TTW_FAST

    def slow_down(self, signum, frame):
        self.time_to_wait = TTW_SLOW
