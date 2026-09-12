import json
import sys

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from sync.source_import import import_sources


# Bare playlist-id prefixes that we accept without a full URL.
_PLAYLIST_ID_PREFIXES = ('PL', 'LL', 'OLAK', 'RDCLAK', 'FL', 'UU')


class Command(BaseCommand):

    help = 'Bulk-import Source objects from a JSON file, a line list, or stdin.'

    def add_arguments(self, parser):
        parser.add_argument(
            'source',
            type=str,
            help="Path to a JSON/line file, or '-' to read stdin.",
        )
        parser.add_argument(
            '--format',
            choices=('json', 'lines'),
            default=None,
            help="Input format. Default: infer from the extension / first character.",
        )
        activate = parser.add_mutually_exclusive_group()
        activate.add_argument(
            '--activate', dest='activate', action='store_true', default=None,
            help='Force imported sources active (schedule indexing + downloads).',
        )
        activate.add_argument(
            '--no-activate', '--inactive', dest='activate', action='store_false',
            help='Force imported sources inactive (index_schedule=0, no downloads).',
        )
        parser.add_argument(
            '--defer-indexing', action='store_true',
            help='bulk_create + staggered index tasks. For very large imports only.',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Validate and report, but roll everything back.',
        )
        parser.add_argument(
            '--default-resolution', default=None,
            help="Applied to items that do not set 'source_resolution'.",
        )
        parser.add_argument(
            '--default-index-schedule', type=int, default=None,
            help="Applied to items that do not set 'index_schedule'.",
        )

    def handle(self, *args, **options):
        raw = self._read_input(options['source'])
        fmt = options['format'] or self._infer_format(options['source'], raw)

        if fmt == 'json':
            items, file_opts = self._parse_json(raw)
        else:
            items, file_opts = self._parse_lines(raw), {}

        if not items:
            raise CommandError('no source items found in the input')

        # Flags override values found in a JSON file.
        activate = options['activate']
        if activate is None:
            activate = file_opts.get('activate')
        defer_indexing = options['defer_indexing'] or bool(file_opts.get('defer_indexing'))
        dry_run = options['dry_run'] or bool(file_opts.get('dry_run'))

        self._inject_defaults(items, options)

        try:
            report = import_sources(
                items,
                activate=activate,
                defer_indexing=defer_indexing,
                dry_run=dry_run,
            )
        except ValidationError as e:
            raise CommandError('; '.join(e.messages)) from e

        for result in report.results:
            if result.status == 'created':
                self.stdout.write(self.style.SUCCESS(
                    f'+ created  {self._label(result)}'
                ))
            elif result.status == 'exists':
                self.stdout.write(f'= exists   {self._label(result)}')
            else:
                self.stdout.write(self.style.ERROR(
                    f'! error    {result.detail}'
                ))

        summary = (
            f'created={report.created} exists={report.exists} '
            f'errors={report.errors}'
            + ('  (dry-run, rolled back)' if report.dry_run else '')
        )
        self.stdout.write(summary)

        if report.errors and not dry_run:
            raise CommandError(f'{report.errors} item(s) failed to import')

    # -- helpers ---------------------------------------------------------

    @staticmethod
    def _label(result):
        key = f'  [{result.key}]' if result.key else ''
        return f'{result.uuid or ""}{key}'.strip()

    @staticmethod
    def _read_input(source):
        if source == '-':
            return sys.stdin.read()
        try:
            with open(source, 'r', encoding='utf-8') as fobj:
                return fobj.read()
        except OSError as e:
            raise CommandError(f'could not read {source!r}: {e}') from e

    @staticmethod
    def _infer_format(source, raw):
        if source.lower().endswith('.json'):
            return 'json'
        stripped = raw.lstrip()
        if stripped[:1] in ('{', '['):
            return 'json'
        return 'lines'

    @staticmethod
    def _parse_json(raw):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise CommandError(f'invalid JSON: {e}') from e
        if isinstance(data, list):
            return data, {}
        if isinstance(data, dict):
            items = data.get('sources')
            if not isinstance(items, list):
                raise CommandError("JSON object must contain a 'sources' list")
            opts = {
                k: data[k]
                for k in ('activate', 'defer_indexing', 'dry_run')
                if k in data
            }
            return items, opts
        raise CommandError('JSON must be an array or an object with a "sources" list')

    @classmethod
    def _parse_lines(cls, raw):
        items = []
        for lineno, line in enumerate(raw.splitlines(), start=1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '://' in line:
                items.append({'url': line})
            elif line.startswith(_PLAYLIST_ID_PREFIXES):
                items.append({'key': line, 'source_type': 'p'})
            else:
                raise CommandError(
                    f'line {lineno}: {line!r} is not a URL and does not look like '
                    f'a playlist id; pass a full URL'
                )
        return items

    @staticmethod
    def _inject_defaults(items, options):
        res = options['default_resolution']
        sched = options['default_index_schedule']
        for item in items:
            if not isinstance(item, dict):
                continue
            if res is not None and 'source_resolution' not in item:
                item['source_resolution'] = res
            if sched is not None and 'index_schedule' not in item:
                item['index_schedule'] = sched
