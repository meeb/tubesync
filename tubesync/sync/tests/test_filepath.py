import logging
from pathlib import Path
from django.conf import settings
from django.test import TestCase
from django.utils import timezone
from sync.models import Source, Media
from sync.choices import (
    Val, Fallback, SourceResolution,
    YouTube_AudioCodec, YouTube_VideoCodec,
    YouTube_SourceType,
)

from .fixtures import metadata

class FilepathTestCase(TestCase):

    def setUp(self):
        # Disable general logging for test case
        logging.disable(logging.CRITICAL)
        # Add a test source
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
        # Add some test media
        self.media = Media.objects.create(
            key='mediakey',
            source=self.source,
            metadata=metadata,
        )

    def test_source_media_format(self):
        # Check media format validation is working
        # Empty
        self.source.media_format = ''
        self.assertEqual(self.source.get_example_media_format(), '')
        # Invalid, bad key
        self.source.media_format = '{test}'
        self.assertEqual(self.source.get_example_media_format(), '')
        # Invalid, extra brackets
        self.source.media_format = '{key}}'
        self.assertEqual(self.source.get_example_media_format(), '')
        # Invalid, not a string
        self.source.media_format = 1
        self.assertEqual(self.source.get_example_media_format(), '')
        # Check all expected keys validate
        self.source.media_format = 'test-{yyyymmdd}'
        self.assertEqual(self.source.get_example_media_format(),
                         'test-' + timezone.now().strftime('%Y%m%d'))
        self.source.media_format = 'test-{yyyy_mm_dd}'
        self.assertEqual(self.source.get_example_media_format(),
                         'test-' + timezone.now().strftime('%Y-%m-%d'))
        self.source.media_format = 'test-{yyyy_0mm_dd}'
        self.assertEqual(self.source.get_example_media_format(),
                         'test-' + timezone.now().strftime('%Y-0%m-%d'))
        self.source.media_format = 'test-{yyyy}'
        self.assertEqual(self.source.get_example_media_format(),
                         'test-' + timezone.now().strftime('%Y'))
        self.source.media_format = 'test-{mm}'
        self.assertEqual(self.source.get_example_media_format(),
                         'test-' + timezone.now().strftime('%m'))
        self.source.media_format = 'test-{dd}'
        self.assertEqual(self.source.get_example_media_format(),
                         'test-' + timezone.now().strftime('%d'))
        self.source.media_format = 'test-{source}'
        self.assertEqual(self.source.get_example_media_format(),
                         'test-' + self.source.slugname)
        self.source.media_format = 'test-{source_full}'
        self.assertEqual(self.source.get_example_media_format(),
                         'test-' + self.source.name)
        self.source.media_format = 'test-{title}'
        self.assertEqual(self.source.get_example_media_format(),
                         'test-some-media-title-name')
        self.source.media_format = 'test-{title_full}'
        self.assertEqual(self.source.get_example_media_format(),
                         'test-Some Media Title Name')
        self.source.media_format = 'test-{key}'
        self.assertEqual(self.source.get_example_media_format(),
                         'test-SoMeUnIqUiD')
        self.source.media_format = 'test-{format}'
        self.assertEqual(self.source.get_example_media_format(),
                         'test-1080p-vp9-opus')
        self.source.media_format = 'test-{playlist_title}'
        self.assertEqual(self.source.get_example_media_format(),
                         'test-Some Playlist Title')
        self.source.media_format = 'test-{ext}'
        self.assertEqual(self.source.get_example_media_format(),
                         'test-' + self.source.extension)
        self.source.media_format = 'test-{resolution}'
        self.assertEqual(self.source.get_example_media_format(),
                         'test-' + self.source.source_resolution)
        self.source.media_format = 'test-{height}'
        self.assertEqual(self.source.get_example_media_format(),
                         'test-720')
        self.source.media_format = 'test-{width}'
        self.assertEqual(self.source.get_example_media_format(),
                         'test-1280')
        self.source.media_format = 'test-{vcodec}'
        self.assertEqual(self.source.get_example_media_format(),
                         'test-' + self.source.source_vcodec.lower())
        self.source.media_format = 'test-{acodec}'
        self.assertEqual(self.source.get_example_media_format(),
                         'test-' + self.source.source_acodec.lower())
        self.source.media_format = 'test-{fps}'
        self.assertEqual(self.source.get_example_media_format(),
                         'test-24')
        self.source.media_format = 'test-{hdr}'
        self.assertEqual(self.source.get_example_media_format(),
                         'test-hdr')

    def test_media_filename(self):
        # Check child directories work
        self.source.media_format = '{yyyy}/{key}.{ext}'
        self.assertEqual(self.media.directory_path,
                         self.source.directory_path / '2017')
        self.assertEqual(self.media.filename, '2017/mediakey.mkv')
        self.source.media_format = '{yyyy}/{yyyy_mm_dd}/{key}.{ext}'
        self.assertEqual(self.media.directory_path,
                         self.source.directory_path / '2017/2017-09-11')
        self.assertEqual(self.media.filename, '2017/2017-09-11/mediakey.mkv')
        # Check media specific media format keys work
        test_media = Media.objects.create(
            key='test',
            source=self.source,
            metadata=metadata,
            downloaded=True,
            download_date=timezone.now(),
            downloaded_format='720p',
            downloaded_height=720,
            downloaded_width=1280,
            downloaded_audio_codec='opus',
            downloaded_video_codec='vp9',
            downloaded_container='mkv',
            downloaded_fps=30,
            downloaded_hdr=True,
            downloaded_filesize=12345
        )
        # Bypass media-file-exists on-save signal
        test_media.downloaded = True
        self.source.media_format = ('{title}_{key}_{resolution}-{height}x{width}-'
                                    '{acodec}-{vcodec}-{fps}fps-{hdr}.{ext}')
        self.assertEqual(test_media.filename,
                         ('no-fancy-stuff-title_test_720p-720x1280-opus'
                          '-vp9-30fps-hdr.mkv'))

    def test_directory_prefix(self):
        # Confirm the setting exists and is valid
        self.assertTrue(hasattr(settings, 'SOURCE_DOWNLOAD_DIRECTORY_PREFIX'))
        self.assertTrue(isinstance(settings.SOURCE_DOWNLOAD_DIRECTORY_PREFIX, bool))
        # Test the default behavior for "True", forced "audio" or "video" parent directories for sources
        settings.SOURCE_DOWNLOAD_DIRECTORY_PREFIX = True
        self.source.source_resolution = Val(SourceResolution.AUDIO)
        test_audio_prefix_path = Path(self.source.directory_path)
        self.assertEqual(test_audio_prefix_path.parts[-2], 'audio')
        self.assertEqual(test_audio_prefix_path.parts[-1], 'testdirectory')
        self.source.source_resolution = Val(SourceResolution.VIDEO_1080P)
        test_video_prefix_path = Path(self.source.directory_path)
        self.assertEqual(test_video_prefix_path.parts[-2], 'video')
        self.assertEqual(test_video_prefix_path.parts[-1], 'testdirectory')
        # Test the default behavior for "False", no parent directories for sources
        settings.SOURCE_DOWNLOAD_DIRECTORY_PREFIX = False
        test_no_prefix_path = Path(self.source.directory_path)
        self.assertEqual(test_no_prefix_path.parts[-1], 'testdirectory')


