import logging

from django.core.exceptions import ValidationError
from django.test import TestCase
from django_huey import DJANGO_HUEY, get_queue

from common.models import TaskHistory
from sync.choices import IndexSchedule, Val, YouTube_SourceType
from sync.models import Source
from sync.source_import import (
    MAX_IMPORT_ITEMS,
    build_source_kwargs,
    import_sources,
)


class SourceImportTestCase(TestCase):
    '''Unit tests for build_source_kwargs() and import_sources().'''

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Queue tasks in memory instead of executing them or touching disk.
        for qn in DJANGO_HUEY.get('queues', dict()):
            q = get_queue(qn)
            q.immediate_use_memory = True
            q.immediate = False

    def setUp(self):
        logging.disable(logging.CRITICAL)

    # -- build_source_kwargs: key / type resolution ---------------------

    def test_url_resolution_channel(self):
        kw = build_source_kwargs({'url': 'https://www.youtube.com/testchannel'})
        self.assertEqual(kw['key'], 'testchannel')
        self.assertEqual(kw['source_type'], Val(YouTube_SourceType.CHANNEL))

    def test_url_resolution_channel_id(self):
        kw = build_source_kwargs({
            'url': 'https://www.youtube.com/channel/UCplaylisttestchannelid',
        })
        self.assertEqual(kw['key'], 'UCplaylisttestchannelid')
        self.assertEqual(kw['source_type'], Val(YouTube_SourceType.CHANNEL_ID))

    def test_url_resolution_playlist(self):
        kw = build_source_kwargs({
            'url': 'https://www.youtube.com/playlist?list=PL3hFtw-djaEbjYRb',
        })
        self.assertEqual(kw['key'], 'PL3hFtw-djaEbjYRb')
        self.assertEqual(kw['source_type'], Val(YouTube_SourceType.PLAYLIST))

    def test_bad_url_raises(self):
        with self.assertRaises(ValidationError):
            build_source_kwargs({'url': 'https://example.com/not-youtube'})

    def test_key_and_source_type_path(self):
        kw = build_source_kwargs({'key': 'PL_abc', 'source_type': 'p'})
        self.assertEqual(kw['key'], 'PL_abc')
        self.assertEqual(kw['source_type'], 'p')

    def test_missing_url_and_key_raises(self):
        with self.assertRaises(ValidationError):
            build_source_kwargs({'name': 'orphan'})

    def test_name_and_directory_derived(self):
        kw = build_source_kwargs({'key': 'PLxyz', 'source_type': 'p',
                                  'title': 'Häkelanleitungen'})
        self.assertEqual(kw['name'], 'Häkelanleitungen')
        self.assertEqual(kw['directory'], 'hakelanleitungen')

    # -- build_source_kwargs: whitelist / validation ------------------

    def test_unknown_field_raises(self):
        with self.assertRaises(ValidationError):
            build_source_kwargs({'key': 'PLx', 'source_type': 'p', 'bogus': 1})

    def test_filter_text_rejected(self):
        with self.assertRaises(ValidationError):
            build_source_kwargs({'key': 'PLx', 'source_type': 'p',
                                 'filter_text': 'anything'})

    def test_metadata_fields_rejected(self):
        for bad in ('uuid', 'has_failed', 'created', 'last_crawl'):
            with self.assertRaises(ValidationError):
                build_source_kwargs({'key': 'PLx', 'source_type': 'p', bad: 'x'})

    def test_bad_choice_lists_valid_values(self):
        with self.assertRaises(ValidationError) as ctx:
            build_source_kwargs({'key': 'PLx', 'source_type': 'p',
                                 'source_resolution': '999p'})
        self.assertIn('1080p', str(ctx.exception))

    def test_bad_index_schedule_raises(self):
        with self.assertRaises(ValidationError):
            build_source_kwargs({'key': 'PLx', 'source_type': 'p',
                                 'index_schedule': 12345})

    def test_directory_escape_rejected(self):
        for bad in ('../../etc', '/etc/passwd', 'a/../../b'):
            with self.assertRaises(ValidationError):
                build_source_kwargs({'key': 'PLx', 'source_type': 'p',
                                     'directory': bad})

    def test_string_boolean_rejected(self):
        with self.assertRaises(ValidationError):
            build_source_kwargs({'key': 'PLx', 'source_type': 'p',
                                 'download_media': 'true'})

    def test_sponsorblock_categories_list_and_string(self):
        kw = build_source_kwargs({'key': 'PLx', 'source_type': 'p',
                                  'sponsorblock_categories': ['sponsor', 'intro']})
        self.assertEqual(kw['sponsorblock_categories'], ['sponsor', 'intro'])
        kw = build_source_kwargs({'key': 'PLy', 'source_type': 'p',
                                  'sponsorblock_categories': 'sponsor,outro'})
        self.assertEqual(kw['sponsorblock_categories'], ['sponsor', 'outro'])
        with self.assertRaises(ValidationError):
            build_source_kwargs({'key': 'PLz', 'source_type': 'p',
                                 'sponsorblock_categories': ['nonsense']})

    # -- import_sources -----------------------------------------------

    def test_created_then_idempotent_exists(self):
        items = [{'key': 'PLaaa', 'source_type': 'p', 'name': 'Alpha'}]
        report = import_sources(items)
        self.assertEqual((report.created, report.exists, report.errors), (1, 0, 0))
        self.assertTrue(Source.objects.filter(key='PLaaa').exists())

        report2 = import_sources(items)
        self.assertEqual((report2.created, report2.exists, report2.errors), (0, 1, 0))
        self.assertEqual(Source.objects.filter(key='PLaaa').count(), 1)
        self.assertEqual(report2.results[0].status, 'exists')

    def test_name_collision_is_per_item_error(self):
        Source.objects.create(key='PLexisting', name='Taken', directory='taken')
        report = import_sources([
            {'key': 'PLgood', 'source_type': 'p', 'name': 'Fresh'},
            {'key': 'PLbad', 'source_type': 'p', 'name': 'Taken'},
        ])
        self.assertEqual((report.created, report.exists, report.errors), (1, 0, 1))
        statuses = {r.status for r in report.results}
        self.assertEqual(statuses, {'created', 'error'})
        err = [r for r in report.results if r.status == 'error'][0]
        self.assertIsNotNone(err.input)

    def test_directory_collision_is_per_item_error(self):
        Source.objects.create(key='PLexisting', name='Existing', directory='shared')
        report = import_sources([
            {'key': 'PLnew', 'source_type': 'p', 'name': 'New', 'directory': 'shared'},
        ])
        self.assertEqual((report.created, report.exists, report.errors), (0, 0, 1))

    def test_dry_run_persists_nothing(self):
        before = Source.objects.count()
        report = import_sources(
            [{'key': 'PLdry', 'source_type': 'p', 'name': 'DryRun'}],
            dry_run=True,
        )
        self.assertTrue(report.dry_run)
        self.assertEqual(report.created, 1)
        self.assertEqual(Source.objects.count(), before)

    def test_activate_false_creates_inactive_source(self):
        report = import_sources(
            [{'key': 'PLinactive', 'source_type': 'p', 'name': 'Inactive'}],
            activate=False,
        )
        self.assertEqual(report.created, 1)
        source = Source.objects.get(key='PLinactive')
        self.assertEqual(source.index_schedule, Val(IndexSchedule.NEVER))
        self.assertFalse(source.download_media)
        self.assertFalse(source.is_active)
        index_tasks = TaskHistory.objects.filter(
            name='sync.tasks.index_source',
            task_params__0__0=str(source.uuid),
        )
        self.assertFalse(index_tasks.exists())

    def test_activate_true_schedules_index_task(self):
        report = import_sources(
            [{'key': 'PLactive', 'source_type': 'p', 'name': 'Active'}],
            activate=True,
        )
        self.assertEqual(report.created, 1)
        source = Source.objects.get(key='PLactive')
        self.assertTrue(source.is_active)
        index_tasks = TaskHistory.objects.filter(
            name='sync.tasks.index_source',
            task_params__0__0=str(source.uuid),
        )
        self.assertTrue(index_tasks.exists())

    def test_defer_indexing_creates_and_schedules(self):
        report = import_sources(
            [
                {'key': 'PLdefer1', 'source_type': 'p', 'name': 'Defer One'},
                {'key': 'PLdefer2', 'source_type': 'p', 'name': 'Defer Two'},
            ],
            activate=True,
            defer_indexing=True,
        )
        self.assertEqual((report.created, report.exists, report.errors), (2, 0, 0))
        self.assertEqual(Source.objects.filter(key__startswith='PLdefer').count(), 2)
        for source in Source.objects.filter(key__startswith='PLdefer'):
            self.assertTrue(TaskHistory.objects.filter(
                name='sync.tasks.index_source',
                task_params__0__0=str(source.uuid),
            ).exists())

    def test_too_many_items_raises(self):
        items = [
            {'key': f'PL{n:04d}', 'source_type': 'p', 'name': f'S{n}'}
            for n in range(MAX_IMPORT_ITEMS + 1)
        ]
        with self.assertRaises(ValidationError):
            import_sources(items)
