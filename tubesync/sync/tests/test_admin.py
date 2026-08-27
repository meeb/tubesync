import logging
from unittest.mock import patch

from django.conf import settings
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory, TestCase, override_settings

from sync.admin import MediaAdmin
from sync.models import Source, Media
from sync.choices import (
    Val, Fallback, SourceResolution,
    YouTube_AudioCodec, YouTube_VideoCodec,
    YouTube_SourceType,
)

from .fixtures import all_test_metadata
metadata = all_test_metadata['boring']


class MediaAdminBulkActionsTestCase(TestCase):
    '''
        Bulk admin actions for toggling `skip` and `can_download`
        on many media items at once (issue #493).
    '''

    def setUp(self):
        logging.disable(logging.CRITICAL)
        self.source = Source.objects.create(
            source_type=Val(YouTube_SourceType.CHANNEL),
            key='testkey',
            name='testname',
            directory='testdirectory',
            media_format=settings.MEDIA_FORMATSTR_DEFAULT,
            index_schedule=3600,
            delete_old_media=False,
            days_to_keep=14,
            source_resolution=Val(SourceResolution.VIDEO_1080P),
            source_vcodec=Val(YouTube_VideoCodec.VP9),
            source_acodec=Val(YouTube_AudioCodec.OPUS),
            prefer_60fps=False,
            prefer_hdr=False,
            fallback=Val(Fallback.FAIL)
        )
        self.media_items = [
            Media.objects.create(
                key=f'mediakey{i}',
                source=self.source,
                metadata=metadata,
            )
            for i in range(3)
        ]
        self.model_admin = MediaAdmin(Media, AdminSite())
        request_factory = RequestFactory()
        self.request = request_factory.post('/admin/sync/media/')
        # message_user needs a messages backend; stub it out instead
        self.model_admin.message_user = lambda *args, **kwargs: None

    def test_bulk_enable_and_disable_skip(self):
        queryset = Media.objects.filter(source=self.source)

        self.model_admin.enable_skip(self.request, queryset)
        for media in queryset:
            self.assertTrue(media.skip)
            self.assertTrue(media.manual_skip)

        self.model_admin.disable_skip(self.request, queryset)
        for media in queryset:
            self.assertFalse(media.skip)
            self.assertFalse(media.manual_skip)

    def test_bulk_enable_and_disable_can_download(self):
        queryset = Media.objects.filter(source=self.source)

        self.model_admin.disable_can_download(self.request, queryset)
        for media in queryset:
            self.assertFalse(media.can_download)

        self.model_admin.enable_can_download(self.request, queryset)
        for media in queryset:
            self.assertTrue(media.can_download)

    def test_actions_registered(self):
        for action in (
            'enable_skip', 'disable_skip',
            'enable_can_download', 'disable_can_download',
        ):
            self.assertIn(action, self.model_admin.actions)

    def test_save_media_tasks_not_queued_by_default(self):
        queryset = Media.objects.filter(source=self.source)

        with patch('sync.admin.save_media') as mock_save_media:
            self.model_admin.enable_skip(self.request, queryset)

        mock_save_media.map.assert_not_called()

    @override_settings(SAVE_MEDIA_AFTER_BULK_ACTION=True)
    def test_save_media_tasks_queued_when_enabled(self):
        queryset = Media.objects.filter(source=self.source)

        with patch('sync.admin.save_media') as mock_save_media:
            self.model_admin.enable_skip(self.request, queryset)

        mock_save_media.map.assert_called_once()
        queued = set(mock_save_media.map.call_args.args[0])
        expected = {
            str(media_uuid)
            for media_uuid in queryset.values_list('uuid', flat=True)
        }
        self.assertEqual(queued, expected)
