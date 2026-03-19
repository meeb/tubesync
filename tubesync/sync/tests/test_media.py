import logging
from datetime import datetime
from xml.etree import ElementTree
from django.conf import settings
from django.test import TestCase
from django.utils import timezone
from sync.models import Source, Media
from sync.filtering import filter_media
from sync.choices import (
    Val, Fallback, SourceResolution,
    YouTube_AudioCodec, YouTube_VideoCodec,
    YouTube_SourceType,
)

from .fixtures import metadata

class MediaTestCase(TestCase):

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
        # Fix a created datetime for predictable testing
        self.media.created = datetime(year=2020, month=1, day=1, hour=1,
                                      minute=1, second=1)

    def test_nfo(self):
        expected_nfo = [
            "<?xml version='1.0' encoding='utf8'?>",
            '<episodedetails>',
            '  <title>no fancy stuff title</title>',
            '  <showtitle>testname</showtitle>',
            '  <season>2017</season>',
            '  <episode></episode>',
            '  <ratings>',
            '    <rating default="True" max="5" name="youtube">',
            '      <value>1.2345</value>',
            '      <votes>579</votes>',
            '    </rating>',
            '  </ratings>',
            '  <plot>no fancy stuff desc</plot>',
            '  <thumb />',  # media.thumbfile is empty without media existing
            '  <mpaa>50</mpaa>',
            '  <runtime>401</runtime>',
            '  <id>mediakey</id>',
            '  <uniqueid default="True" type="youtube">mediakey</uniqueid>',
            '  <studio>test uploader</studio>',
            '  <aired>2017-09-11</aired>',
            '  <dateadded>2020-01-01 01:01:01</dateadded>',
            '  <genre>test category 1</genre>',
            '  <genre>test category 2</genre>',
            '</episodedetails>',
        ]
        expected_tree = ElementTree.fromstring('\n'.join(expected_nfo))
        nfo_tree = ElementTree.fromstring(self.media.nfoxml)
        # Check each node with attribs in expected_tree is present in test_nfo
        for expected_node in expected_tree:
            # Ignore checking <genre>, only tag we may have multiple of
            if expected_node.tag == 'genre':
                continue
            # Find the same node in the NFO XML tree
            nfo_node = nfo_tree.find(expected_node.tag)
            self.assertEqual(expected_node.attrib, nfo_node.attrib)
            self.assertEqual(expected_node.tag, nfo_node.tag)
            self.assertEqual(expected_node.text, nfo_node.text)


class MediaFilterTestCase(TestCase):

    def setUp(self):
        # Disable general logging for test case
        # logging.disable(logging.CRITICAL)
        # Add a test source
        self.source = Source.objects.create(
            source_type=Val(YouTube_SourceType.CHANNEL),
            key="testkey",
            name="testname",
            directory="testdirectory",
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
        # Add some test media
        self.media = Media.objects.create(
            key="mediakey",
            source=self.source,
            metadata=metadata,
            skip=False,
            published=timezone.make_aware(
                datetime(year=2020, month=1, day=1, hour=1, minute=1, second=1)
            ),
        )
        # Fix a created datetime for predictable testing
        self.media.created = datetime(
            year=2020, month=1, day=1, hour=1, minute=1, second=1
        )

    def test_filter_unpublished_skip(self):
        # Check if unpublished that we skip download it
        self.media.skip = False
        self.media.published = False
        changed = filter_media(self.media)
        self.assertTrue(changed)
        self.assertTrue(self.media.skip)

    def test_filter_published_unskip(self):
        # Check if we had previously skipped it, but now it's published, we won't skip it
        self.media.skip = True
        self.media.published = timezone.make_aware(
            datetime(year=2020, month=1, day=1, hour=1, minute=1, second=1)
        )
        changed = filter_media(self.media)
        self.assertTrue(changed)
        self.assertFalse(self.media.skip)

    def test_filter_filter_text_nomatch(self):
        # Check that if we don't match the filter text, we skip
        self.media.source.filter_text = "No fancy stuff"
        self.media.skip = False
        self.media.published = timezone.make_aware(
            datetime(year=2020, month=1, day=1, hour=1, minute=1, second=1)
        )
        changed = filter_media(self.media)
        self.assertTrue(changed)
        self.assertTrue(self.media.skip)

    def test_filter_filter_text_match(self):
        # Check that if we match the filter text, we don't skip
        self.media.source.filter_text = "(?i)No fancy stuff"
        self.media.skip = True
        self.media.published = timezone.make_aware(
            datetime(year=2020, month=1, day=1, hour=1, minute=1, second=1)
        )
        changed = filter_media(self.media)
        self.assertTrue(changed)
        self.assertFalse(self.media.skip)

    def test_filter_filter_text_invert_nomatch(self):
        # Check that if we don't match the filter text, we don't skip
        self.media.source.filter_text = "No fancy stuff"
        self.media.source.filter_text_invert = True
        self.media.skip = True
        self.media.published = timezone.make_aware(
            datetime(year=2020, month=1, day=1, hour=1, minute=1, second=1)
        )
        changed = filter_media(self.media)
        self.assertTrue(changed)
        self.assertFalse(self.media.skip)

    def test_filter_filter_text_invert_match(self):
        # Check that if we match the filter text and do skip
        self.media.source.filter_text = "(?i)No fancy stuff"
        self.media.source.filter_text_invert = True
        self.media.skip = False
        self.media.published = timezone.make_aware(
            datetime(year=2020, month=1, day=1, hour=1, minute=1, second=1)
        )
        changed = filter_media(self.media)
        self.assertTrue(changed)
        self.assertTrue(self.media.skip)

    def test_filter_max_cap_skip(self):
        # Check if it's older than the max_cap, we don't download it (1 second so it will always fail)
        self.media.source.download_cap = 1
        self.media.skip = False
        self.media.published = timezone.make_aware(
            datetime(year=2020, month=1, day=1, hour=1, minute=1, second=1)
        )
        changed = filter_media(self.media)
        self.assertTrue(changed)
        self.assertTrue(self.media.skip)

    def test_filter_max_cap_unskip(self):
        # Make sure it's newer than the cap so we download it, ensure that we are published in the last seconds
        self.media.source.download_cap = 3600
        self.media.skip = True
        self.media.published = timezone.now()
        changed = filter_media(self.media)
        self.assertTrue(changed)
        self.assertFalse(self.media.skip)

    def test_filter_below_min(self):
        # Filter videos shorter than the minimum limit
        self.media.skip = False
        self.media.source.filter_seconds_min = True
        self.media.source.filter_seconds = 500
        self.media.published = timezone.make_aware(
            datetime(year=2020, month=1, day=1, hour=1, minute=1, second=1)
        )
        changed = filter_media(self.media)
        self.assertTrue(changed)
        self.assertTrue(self.media.skip)

    def test_filter_above_min(self):
        # Video is longer than the minimum, allow it
        self.media.skip = True
        self.media.source.filter_seconds_min = True
        self.media.source.filter_seconds = 300
        self.media.published = timezone.make_aware(
            datetime(year=2020, month=1, day=1, hour=1, minute=1, second=1)
        )
        changed = filter_media(self.media)
        self.assertTrue(changed)
        self.assertFalse(self.media.skip)

    def test_filter_above_max(self):
        # Filter videos longer than the maximum limit
        self.media.skip = False
        self.media.source.filter_seconds_min = False
        self.media.source.filter_seconds = 300
        self.media.published = timezone.make_aware(
            datetime(year=2020, month=1, day=1, hour=1, minute=1, second=1)
        )
        changed = filter_media(self.media)
        self.assertTrue(changed)
        self.assertTrue(self.media.skip)

    def test_filter_below_max(self):
        # Video is below the maximum, allow it
        self.media.skip = True
        self.media.source.filter_seconds_min = False
        self.media.source.filter_seconds = 500
        self.media.published = timezone.make_aware(
            datetime(year=2020, month=1, day=1, hour=1, minute=1, second=1)
        )
        changed = filter_media(self.media)
        self.assertTrue(changed)
        self.assertFalse(self.media.skip)

    def test_download_finished_clears_stale_video_fields_for_audio(self):
        filepath = self.media.filepath.parent / 'downloaded-audio.ogg'
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_bytes(b'test-audio')

        self.media.downloaded_format = '1080p'
        self.media.downloaded_height = 1080
        self.media.downloaded_width = 1920
        self.media.downloaded_video_codec = 'vp9'
        self.media.downloaded_fps = 50
        self.media.downloaded_hdr = True

        self.media.download_finished('249', 'ogg', downloaded_filepath=filepath)

        self.assertTrue(self.media.downloaded)
        self.assertEqual(self.media.downloaded_format, Val(SourceResolution.AUDIO))
        self.assertEqual(self.media.downloaded_container, 'ogg')
        self.assertIsNone(self.media.downloaded_height)
        self.assertIsNone(self.media.downloaded_width)
        self.assertIsNone(self.media.downloaded_video_codec)
        self.assertIsNone(self.media.downloaded_fps)
        self.assertFalse(self.media.downloaded_hdr)
