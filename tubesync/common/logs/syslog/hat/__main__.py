import contextlib
import logging
import socket
import threading
import time
import unittest

from ._default import handler


class MockSyslogServer:
    """Stands up an isolated local background socket server to harvest transport streams."""

    def __init__(self, host='127.0.0.1', port=0):
        self.host = host
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.host, self.port))
        self.port = self.sock.getsockname()[1]

        self.received_messages = []
        self.shutdown = threading.Event()
        self._thread = None

    def start(self):
        self.shutdown.clear()
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self.shutdown.set()

        # Wake up the blocking accept() call.
        with contextlib.suppress(OSError, TypeError, ValueError):
            socket.create_connection((self.host, self.port), timeout=0.1).close()

        if self._thread:
            self._thread.join(timeout=1.0)
        self.sock.close()

    def _listen_loop(self):
        self.sock.listen(1)
        while not self.shutdown.is_set():
            with contextlib.suppress(OSError):
                conn, _ = self.sock.accept()
                with conn:
                    while (data := conn.recv(4096)) and not self.shutdown.is_set():
                        self.received_messages.append(data.decode('utf-8'))


class TestSyslogHandlerIntegration(unittest.TestCase):
    def setUp(self):
        """Initializes the background mock network collection service before running assertions."""
        self.server = MockSyslogServer()
        self.server.start()

        self.handler = handler(
            host=self.server.host,
            port=self.server.port,
            comm_type='tcp',
            queue_size=10,
            reconnect_delay=1,
        )

        self.test_logger = logging.getLogger('integration_test')
        self.test_logger.setLevel(logging.DEBUG)
        self.test_logger.addHandler(self.handler)

    def tearDown(self):
        """Cleans up the network service topology profiles safely upon validation teardown."""
        with contextlib.suppress(Exception):
            self.handler.close()
        self.server.stop()

    def test_pipeline_delivery_and_flush(self):
        """Verifies that items are completely delivered down the wire before flush unblocks."""
        self.test_logger.debug('Message A')
        self.test_logger.info('Message B')

        start_time = time.monotonic()
        self.handler.flush()
        elapsed = time.monotonic() - start_time

        self.assertLess(elapsed, 2.0, 'The flush operations deadlocked the execution loop context')
        self.assertTrue(any('Message A' in msg for msg in self.server.received_messages))
        self.assertTrue(any('Message B' in msg for msg in self.server.received_messages))

    def test_graceful_close_lifecycle(self):
        """Confirms that close drains remaining log states and tears down the worker thread."""
        self.test_logger.info('Shutdown Message')
        self.handler.close()
        self.assertTrue(any('Shutdown Message' in msg for msg in self.server.received_messages))

unittest.main()
