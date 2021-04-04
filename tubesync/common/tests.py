import os.path
from django.conf import settings
from django.test import TestCase, Client
from .testutils import prevent_request_warnings
from .utils import parse_database_connection_string
from .errors import DatabaseConnectionError


class ErrorPageTestCase(TestCase):

    @prevent_request_warnings
    def test_error_403(self):
        c = Client()
        response = c.get('/error403')
        self.assertEqual(response.status_code, 403)

    @prevent_request_warnings
    def test_error_404(self):
        c = Client()
        response = c.get('/error404')
        self.assertEqual(response.status_code, 404)

    @prevent_request_warnings
    def test_error_500(self):
        c = Client()
        response = c.get('/error500')
        self.assertEqual(response.status_code, 500)


class HealthcheckTestCase(TestCase):

    def test_healthcheck(self):
        c = Client()
        response = c.get('/healthcheck')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), 'ok')


class CommonStaticTestCase(TestCase):

    def test_robots(self):
        response = self.client.get('/robots.txt')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), settings.ROBOTS)

    def test_favicon(self):
        # /favicon.ico should be a redirect to the real icon somewhere in STATIC_FILES
        response = self.client.get('/favicon.ico')
        self.assertEqual(response.status_code, 302)
        # Given tests run with DEBUG=False calls to files in /static/ will fail, check
        # the file exists on disk in common/static/ manually
        root = settings.STATIC_ROOT
        root_parts = str(root).split(os.sep)
        url = response.url
        if url.startswith('/'):
            url = url[1:]
        url_parts = url.split(os.sep)
        if url_parts[0] == root_parts[-1]:
            del root_parts[-1]
            del url_parts[0]
        root_parts.append('common')
        root_parts.append('static')
        favicon_real_path = os.path.join(os.sep.join(root_parts),
                                         os.sep.join(url_parts))
        self.assertTrue(os.path.exists(favicon_real_path))


class DatabaseConnectionTestCase(TestCase):

    def test_parse_database_connection_string(self):
        database_dict = parse_database_connection_string(
            'postgresql://tubesync:password@localhost:5432/tubesync')
        database_dict = parse_database_connection_string(
            'mysql://tubesync:password@localhost:3306/tubesync')
        # Invalid driver
        with self.assertRaises(DatabaseConnectionError):
            parse_database_connection_string(
                'test://tubesync:password@localhost:5432/tubesync')
        # No username
        with self.assertRaises(DatabaseConnectionError):
            parse_database_connection_string(
                'postgresql://password@localhost:5432/tubesync')
        # No database name
        with self.assertRaises(DatabaseConnectionError):
            parse_database_connection_string(
                'postgresql://tubesync:password@5432')
        # Invalid port
        with self.assertRaises(DatabaseConnectionError):
            parse_database_connection_string(
                'postgresql://tubesync:password@localhost:test/tubesync')
        # Invalid port
        with self.assertRaises(DatabaseConnectionError):
            parse_database_connection_string(
                'postgresql://tubesync:password@localhost:65537/tubesync')
        # Invalid username or password
        with self.assertRaises(DatabaseConnectionError):
            parse_database_connection_string(
                'postgresql://tubesync:password:test@localhost:5432/tubesync')
        # Invalid database name
        with self.assertRaises(DatabaseConnectionError):
            parse_database_connection_string(
                'postgresql://tubesync:password@localhost:5432/tubesync/test')
