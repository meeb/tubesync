import logging

from django.core.management import call_command
from django.test import TestCase
from django_huey import DJANGO_HUEY, get_queue

from sync.models import Media, Source
from sync.signals import _sources_being_deleted


class SourceDeleteTestCase(TestCase):
    '''
        Deleting a Source must not leave orphaned Media rows behind. On
        PostgreSQL an orphan fails the deferred FK check at COMMIT; on SQLite it
        silently corrupts the table. media_post_delete used to recreate a
        "skipped media" placeholder pointing at the Source being deleted.
    '''

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        for qn in DJANGO_HUEY.get('queues', dict()):
            q = get_queue(qn)
            q.immediate_use_memory = True
            q.immediate = False

    def setUp(self):
        logging.disable(logging.CRITICAL)
        _sources_being_deleted.clear()

    def _make_source(self, key='delK', name='Del', directory='del', **kw):
        src = Source.objects.create(key=key, name=name, directory=directory, **kw)
        for i in range(3):
            Media.objects.create(source=src, key=f'{key}-v{i}', downloaded=True,
                                 title=f'{name} {i}')
        return src

    def test_source_delete_leaves_no_orphan_media(self):
        src = self._make_source()
        sid = str(src.uuid)
        src.delete()
        self.assertEqual(Media.objects.filter(source_id=sid).count(), 0)
        self.assertEqual(Source.objects.filter(uuid=sid).count(), 0)
        self.assertNotIn(sid, _sources_being_deleted)

    def test_delete_source_management_command(self):
        src = self._make_source(key='cmdK', name='CmdDel', directory='cmd-del')
        sid = str(src.uuid)
        call_command('delete-source', '--source', sid)
        self.assertEqual(Source.objects.filter(uuid=sid).count(), 0)
        self.assertEqual(Media.objects.filter(source_id=sid).count(), 0)

    def test_delete_source_with_delete_files_flag(self):
        src = self._make_source(key='ffK', name='FF', directory='ff',
                                delete_files_on_disk=True)
        sid = str(src.uuid)
        src.delete()   # must not raise even though delete_files_on_disk is set
        self.assertEqual(Media.objects.filter(source_id=sid).count(), 0)

    def test_media_post_delete_on_already_orphaned_row_does_not_crash(self):
        src = self._make_source(key='orphK', name='Orph', directory='orph')
        media = src.media_source.first()
        # Simulate an orphan: drop the source row without cascading.
        Source.objects.filter(pk=src.uuid).delete()
        _sources_being_deleted.clear()
        # Deleting the orphaned media must not raise Source.DoesNotExist.
        media.delete()
        self.assertFalse(Media.objects.filter(pk=media.pk).exists())

    def test_delete_all_media_for_source_task_when_source_already_gone(self):
        from sync.tasks import delete_all_media_for_source
        src = self._make_source(key='taskK', name='TaskDel', directory='task-del')
        sid = str(src.uuid)
        directory = str(src.directory_path)
        Source.objects.filter(pk=src.uuid).delete()   # source vanished first
        _sources_being_deleted.clear()
        delete_all_media_for_source.call_local(sid, 'TaskDel', directory)
        self.assertEqual(Media.objects.filter(source_id=sid).count(), 0)
