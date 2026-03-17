import os.path
from django.conf import settings
from django.test import TestCase, Client
from .testutils import prevent_request_warnings
from .utils import parse_database_connection_string, clean_filename
from .errors import DatabaseConnectionError


class ErrorPageTestCase(TestCase):
    """Test cases for error pages."""

    @prevent_request_warnings
    def test_error_403(self):
        """Test 403 error page."""
        client = Client()
        response = client.get("/error403")
        self.assertEqual(response.status_code, 403)

    @prevent_request_warnings
    def test_error_404(self):
        """Test 404 error page."""
        client = Client()
        response = client.get("/error404")
        self.assertEqual(response.status_code, 404)

    @prevent_request_warnings
    def test_error_500(self):
        """Test 500 error page."""
        client = Client()
        response = client.get("/error500")
        self.assertEqual(response.status_code, 500)


class HealthcheckTestCase(TestCase):
    """Test cases for healthcheck."""

    def test_healthcheck(self):
        """Test healthcheck."""
        client = Client()
        response = client.get("/healthcheck")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), "ok")


class CommonStaticTestCase(TestCase):
    """Test cases for common static files."""

    def test_robots(self):
        """Test robots.txt."""
        response = self.client.get("/robots.txt")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), settings.ROBOTS)

    def test_favicon(self):
        """Test favicon.ico."""
        # /favicon.ico should be a redirect to the real icon somewhere in STATIC_FILES
        response = self.client.get("/favicon.ico")
        self.assertEqual(response.status_code, 302)
        # Given tests run with DEBUG=False calls to files in /static/ will fail, check
        # the file exists on disk in common/static/ manually
        static_root = settings.STATIC_ROOT
        static_root_parts = str(static_root).split(os.sep)
        url = response.url
        if url.startswith("/"):
            url = url[1:]
        url_parts = url.split(os.sep)
        if url_parts[0] == static_root_parts[-1]:
            del static_root_parts[-1]
            del url_parts[0]
        static_root_parts.append("common")
        static_root_parts.append("static")
        favicon_real_path = os.path.join(
            os.sep.join(static_root_parts), os.sep.join(url_parts)
        )
        self.assertTrue(os.path.exists(favicon_real_path))


class UtilsTestCase(TestCase):
    """Test cases for utility functions."""

    def test_parse_database_connection_string(self):
        """Test parse_database_connection_string."""
        # Test valid connection strings
        database_dict = parse_database_connection_string(
            "postgresql://tubesync:password@localhost:5432/tubesync"
        )
        self.assertEqual(
            database_dict,
            {
                "DRIVER": "postgresql",
                "ENGINE": "django.db.backends.postgresql",
                "USER": "tubesync",
                "PASSWORD": "password",
                "HOST": "localhost",
                "PORT": 5432,
                "NAME": "tubesync",
                "CONN_HEALTH_CHECKS": True,
                "CONN_MAX_AGE": 0,
                "OPTIONS": {
                    "pool": {
                        "max_size": 10,
                        "min_size": 3,
                        "num_workers": 2,
                        "timeout": 180,
                    }
                },
            },
        )
        database_dict = parse_database_connection_string(
            "mysql://tubesync:password@localhost:3306/tubesync"
        )
        self.assertEqual(
            database_dict,
            {
                "DRIVER": "mysql",
                "ENGINE": "django.db.backends.mysql",
                "USER": "tubesync",
                "PASSWORD": "password",
                "HOST": "localhost",
                "PORT": 3306,
                "NAME": "tubesync",
                "CONN_HEALTH_CHECKS": True,
                "CONN_MAX_AGE": 300,
                "OPTIONS": {"charset": "utf8mb4"},
            },
        )

        # Test invalid connection strings
        with self.assertRaises(DatabaseConnectionError):
            parse_database_connection_string(
                "test://tubesync:password@localhost:5432/tubesync"
            )
        with self.assertRaises(DatabaseConnectionError):
            parse_database_connection_string(
                "postgresql://password@localhost:5432/tubesync"
            )
        with self.assertRaises(DatabaseConnectionError):
            parse_database_connection_string("postgresql://tubesync:password@5432")
        with self.assertRaises(DatabaseConnectionError):
            parse_database_connection_string(
                "postgresql://tubesync:password@localhost:test/tubesync"
            )
        with self.assertRaises(DatabaseConnectionError):
            parse_database_connection_string(
                "postgresql://tubesync:password@localhost:65537/tubesync"
            )
        with self.assertRaises(DatabaseConnectionError):
            parse_database_connection_string(
                "postgresql://tubesync:password:test@localhost:5432/tubesync"
            )
        with self.assertRaises(DatabaseConnectionError):
            parse_database_connection_string(
                "postgresql://tubesync:password@localhost:5432/tubesync/test"
            )

    def test_clean_filename(self):
        """Test clean_filename."""
        self.assertEqual(clean_filename("a"), "a")
        self.assertEqual(clean_filename("a\t"), "a")
        self.assertEqual(clean_filename("a\n"), "a")
        self.assertEqual(clean_filename("a a"), "a a")
        self.assertEqual(clean_filename("a  a"), "a  a")
        self.assertEqual(clean_filename("a\t\t\ta"), "a   a")
        self.assertEqual(clean_filename("a\t\t\ta\t\t\t"), "a   a")
