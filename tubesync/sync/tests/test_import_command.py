import io
import json
import logging
import tempfile
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django_huey import DJANGO_HUEY, get_queue

from sync.models import Source


class ImportSourcesCommandTestCase(TestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        for qn in DJANGO_HUEY.get('queues', dict()):
            q = get_queue(qn)
            q.immediate_use_memory = True
            q.immediate = False

    def setUp(self):
        logging.disable(logging.CRITICAL)
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def _write(self, name, content):
        path = self.tmp / name
        path.write_text(content, encoding='utf-8')
        return str(path)

    def test_json_file_creates_sources(self):
        path = self._write('sources.json', json.dumps({
            'activate': False,
            'sources': [
                {'key': 'PLcmd1', 'source_type': 'p', 'name': 'Cmd One'},
                {'key': 'PLcmd2', 'source_type': 'p', 'name': 'Cmd Two'},
            ],
        }))
        out = io.StringIO()
        call_command('import-sources', path, stdout=out)
        self.assertEqual(Source.objects.filter(key__in=('PLcmd1', 'PLcmd2')).count(), 2)
        self.assertIn('created=2', out.getvalue())

    def test_stdin_dash(self):
        payload = json.dumps([{'key': 'PLstdin', 'source_type': 'p', 'name': 'Stdin'}])
        with mock.patch('sys.stdin', io.StringIO(payload)):
            call_command('import-sources', '-', stdout=io.StringIO())
        self.assertTrue(Source.objects.filter(key='PLstdin').exists())

    def test_dry_run_persists_nothing_exit_zero(self):
        path = self._write('dry.json', json.dumps([
            {'key': 'PLdryrun', 'source_type': 'p', 'name': 'DryRun'},
        ]))
        out = io.StringIO()
        call_command('import-sources', path, '--dry-run', stdout=out)
        self.assertFalse(Source.objects.filter(key='PLdryrun').exists())
        self.assertIn('dry-run', out.getvalue())

    def test_errors_without_dry_run_raise_commanderror(self):
        Source.objects.create(key='PLexisting', name='Clash', directory='clash')
        path = self._write('bad.json', json.dumps([
            {'key': 'PLbad', 'source_type': 'p', 'name': 'Clash'},
        ]))
        with self.assertRaises(CommandError):
            call_command('import-sources', path, stdout=io.StringIO())

    def test_lines_format_with_urls_and_comments(self):
        content = (
            '# a comment\n'
            '\n'
            'https://www.youtube.com/playlist?list=PLlines1\n'
            'PLlines2\n'
            '   # indented comment\n'
        )
        path = self._write('sources.txt', content)
        call_command('import-sources', path, '--format', 'lines', stdout=io.StringIO())
        self.assertTrue(Source.objects.filter(key='PLlines1').exists())
        self.assertTrue(Source.objects.filter(key='PLlines2').exists())

    def test_lines_format_rejects_bare_non_playlist(self):
        path = self._write('bad.txt', 'just-some-text\n')
        with self.assertRaises(CommandError):
            call_command('import-sources', path, '--format', 'lines',
                         stdout=io.StringIO())

    def test_default_resolution_injected(self):
        path = self._write('r.json', json.dumps([
            {'key': 'PLres', 'source_type': 'p', 'name': 'Res'},
        ]))
        call_command('import-sources', path, '--default-resolution', '720p',
                     stdout=io.StringIO())
        self.assertEqual(Source.objects.get(key='PLres').source_resolution, '720p')
