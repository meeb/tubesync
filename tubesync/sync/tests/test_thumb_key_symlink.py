import os
import shutil
import tempfile
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image

from sync.choices import (
    Fallback,
    SourceResolution,
    Val,
    YouTube_AudioCodec,
    YouTube_SourceType,
    YouTube_VideoCodec,
)
from sync.models import Media, Source

from .fixtures import all_test_metadata


def _jpeg(color):
    buffer = BytesIO()
    Image.new('RGB', (8, 8), color).save(buffer, format='JPEG')
    return buffer.getvalue()


class ThumbKeySymlinkTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.settings_override = override_settings(MEDIA_ROOT=self.media_root)
        self.settings_override.enable()
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
            fallback=Val(Fallback.FAIL),
        )
        self.media = Media.objects.create(
            key='mediakey',
            source=self.source,
            metadata=all_test_metadata['boring'],
        )

    def tearDown(self):
        self.settings_override.disable()
        shutil.rmtree(self.media_root)

    def _jpg_path(self):
        fileid = str(self.media.uuid).lower()
        return Path(settings.MEDIA_ROOT) / 'thumbs' / fileid[:2] / f'{fileid}.jpg'

    def _link_path(self):
        key = self.media.key
        return Path(settings.MEDIA_ROOT) / 'thumbs' / 'key' / key[:2] / key

    def _save_thumb(self, color):
        self.media.thumb.save(
            'thumb.jpg',
            SimpleUploadedFile('thumb.jpg', _jpeg(color), 'image/jpeg'),
            save=True,
        )

    def _assert_link_resolves_to_jpg(self):
        link = self._link_path()
        jpg = self._jpg_path()
        self.assertTrue(jpg.is_file())
        self.assertTrue(link.is_symlink())
        relative = os.readlink(link)
        self.assertFalse(os.path.isabs(relative))
        self.assertEqual((link.parent / relative).resolve(), jpg.resolve())

    def test_saving_thumb_creates_key_symlink(self):
        self._save_thumb('red')
        self._assert_link_resolves_to_jpg()

    def test_deleting_media_removes_symlink(self):
        self._save_thumb('red')
        link = self._link_path()
        self.assertTrue(link.is_symlink())
        self.media.delete()
        self.assertFalse(link.is_symlink())

    def test_deleting_thumb_removes_symlink(self):
        self._save_thumb('red')
        link = self._link_path()
        self.assertTrue(link.is_symlink())
        self.media.thumb.delete(save=False)
        self.assertFalse(link.is_symlink())

    def test_replacing_thumb_repairs_key_symlink(self):
        self._save_thumb('red')
        link = self._link_path()
        link.parent.mkdir(parents=True, exist_ok=True)
        if link.is_symlink():
            link.unlink()
        link.symlink_to('not-the-thumbnail')
        self._save_thumb('blue')
        self._assert_link_resolves_to_jpg()

    def test_resync_is_idempotent(self):
        self._save_thumb('red')
        from sync.thumb_key import sync_media_thumb_key_symlink

        before = os.readlink(self._link_path())
        sync_media_thumb_key_symlink(self.media)
        sync_media_thumb_key_symlink(self.media)
        self.assertEqual(os.readlink(self._link_path()), before)
        self._assert_link_resolves_to_jpg()
