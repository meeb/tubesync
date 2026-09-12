from pathlib import Path
from django.conf import settings
from django.test import TestCase, Client
from .testutils import prevent_request_warnings
from .utils import parse_database_connection_string, clean_filename
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
        # save the separator
        root = Path(settings.STATIC_ROOT)
        if hasattr(root, 'parser'):
            root_sep = root.parser.sep
        elif (m := getattr(root, '_flavour', None)):
            root_sep = m.sep

        # /favicon.ico should be a redirect to the real icon somewhere in STATIC_FILES
        response = self.client.get('/favicon.ico')
        self.assertEqual(response.status_code, 302)
        # Given tests run with DEBUG=False calls to files in /static/ will fail, check
        # the file exists on disk in common/static/ manually
        url_sep = '/'
        url = response.url.removeprefix(url_sep)
        url_parts = url.split(url_sep)
        if url_parts[0] == root.name:
            del url_parts[0]
            root = root.parent
        root /= 'common'
        root /= 'static'
        favicon_real_path = root.joinpath(root_sep.join(url_parts))
        self.assertTrue(favicon_real_path.exists())


class UtilsTestCase(TestCase):

    def test_parse_database_connection_string(self):
        database_dict = parse_database_connection_string(
            'postgresql://tubesync:password@localhost:5432/tubesync')
        self.assertEqual(database_dict,
            {
                'DRIVER': 'postgresql',
                'ENGINE': 'django.db.backends.postgresql',
                'USER': 'tubesync',
                'PASSWORD': 'password',
                'HOST': 'localhost',
                'PORT': 5432,
                'NAME': 'tubesync',
                'CONN_HEALTH_CHECKS': True,
                'CONN_MAX_AGE': 0,
                'OPTIONS': dict(pool={
                    'max_size': 10,
                    'min_size': 3,
                    'num_workers': 2,
                    'timeout': 180,
                }),
            }
        )
        database_dict = parse_database_connection_string(
            'mysql://tubesync:password@localhost:3306/tubesync')
        self.assertEqual(database_dict,
            {
                'DRIVER': 'mysql',
                'ENGINE': 'django.db.backends.mysql',
                'USER': 'tubesync',
                'PASSWORD': 'password',
                'HOST': 'localhost',
                'PORT': 3306,
                'NAME': 'tubesync',
                'CONN_HEALTH_CHECKS': True,
                'CONN_MAX_AGE': 300,
                'OPTIONS': {'charset': 'utf8mb4'}
            }
        )
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

    def test_clean_filename(self):
        self.assertEqual(clean_filename('a'), 'a')
        self.assertEqual(clean_filename('a\t'), 'a')
        self.assertEqual(clean_filename('a\n'), 'a')
        self.assertEqual(clean_filename('a a'), 'a a')
        self.assertEqual(clean_filename('a  a'), 'a  a')
        self.assertEqual(clean_filename('a\t\t\ta'), 'a   a')
        self.assertEqual(clean_filename('a\t\t\ta\t\t\t'), 'a   a')
