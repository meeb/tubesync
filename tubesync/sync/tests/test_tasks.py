import logging
from datetime import timedelta
from django.test import TestCase
from django.utils import timezone
from sync.models import Source, Media
from sync.tasks import (
    cleanup_old_media,
)

class TasksTestCase(TestCase):

    def setUp(self):
        # Disable general logging for test case
        logging.disable(logging.CRITICAL)

    def test_delete_old_media(self):
        src1 = Source.objects.create(key='aaa', name='aaa', directory='/tmp/a', delete_old_media=False, days_to_keep=14)
        src2 = Source.objects.create(key='bbb', name='bbb', directory='/tmp/b', delete_old_media=True, days_to_keep=14)

        now = timezone.now()

        m11 = Media.objects.create(source=src1, downloaded=True, key='a11', download_date=now - timedelta(days=5)) # noqa: F841
        m12 = Media.objects.create(source=src1, downloaded=True, key='a12', download_date=now - timedelta(days=25)) # noqa: F841
        m13 = Media.objects.create(source=src1, downloaded=False, key='a13') # noqa: F841

        m21 = Media.objects.create(source=src2, downloaded=True, key='a21', download_date=now - timedelta(days=5)) # noqa: F841
        m22 = Media.objects.create(source=src2, downloaded=True, key='a22', download_date=now - timedelta(days=25))
        m23 = Media.objects.create(source=src2, downloaded=False, key='a23') # noqa: F841
        self.assertEqual(src1.media_source.all().count(), 3)

        self.assertEqual(src2.media_source.all().count(), 3)

        cleanup_old_media.call_local(durable=False)

        self.assertEqual(src1.media_source.all().count(), 3)
        self.assertEqual(src2.media_source.all().count(), 3)
        self.assertEqual(Media.objects.filter(pk=m22.pk).exists(), False)
        self.assertEqual(Media.objects.filter(source=src2, key=m22.key, skip=True).exists(), True)
