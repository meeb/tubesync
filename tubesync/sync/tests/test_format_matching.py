import logging
from django.test import TestCase
from sync.models import Source, Media
from sync.choices import (
    Val, Fallback, SourceResolution,
    YouTube_AudioCodec, YouTube_VideoCodec,
    YouTube_SourceType,
)

from .fixtures import all_test_metadata

class FormatMatchingTestCase(TestCase):

    def setUp(self):
        # Disable general logging for test case
        logging.disable(logging.CRITICAL)
        # Add a test source
        self.source = Source.objects.create(
            source_type=Val(YouTube_SourceType.CHANNEL),
            key='testkey',
            name='testname',
            directory='testdirectory',
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
        # Add some media
        self.media = Media.objects.create(
            key='mediakey',
            source=self.source,
            metadata='{}'
        )

    def test_combined_exact_format_matching(self):
        self.source.fallback = Val(Fallback.FAIL)
        self.media.metadata = all_test_metadata['boring']
        self.media.save()
        expected_matches = {
            # (format, vcodec, acodec, prefer_60fps, prefer_hdr): (match_type, code),
            ('360p', 'AVC1', 'MP4A', True, False): (False, False),
            ('360p', 'AVC1', 'MP4A', False, True): (False, False),
            ('360p', 'AVC1', 'MP4A', False, False): (True, '18'),      # Exact match
            ('360p', 'AVC1', 'OPUS', True, True): (False, False),
            ('360p', 'AVC1', 'OPUS', True, False): (False, False),
            ('360p', 'AVC1', 'OPUS', False, True): (False, False),
            ('360p', 'AVC1', 'OPUS', False, False): (False, False),
            ('360p', 'VP9', 'MP4A', True, True): (False, False),
            ('360p', 'VP9', 'MP4A', True, False): (False, False),
            ('360p', 'VP9', 'MP4A', False, True): (False, False),
            ('360p', 'VP9', 'MP4A', False, False): (False, False),
            ('360p', 'VP9', 'OPUS', True, True): (False, False),
            ('360p', 'VP9', 'OPUS', True, False): (False, False),
            ('360p', 'VP9', 'OPUS', False, True): (False, False),
            ('360p', 'VP9', 'OPUS', False, False): (False, False),
            ('480p', 'AVC1', 'MP4A', True, True): (False, False),
            ('480p', 'AVC1', 'MP4A', True, False): (False, False),
            ('480p', 'AVC1', 'MP4A', False, True): (False, False),
            ('480p', 'AVC1', 'MP4A', False, False): (False, False),
            ('480p', 'AVC1', 'OPUS', True, True): (False, False),
            ('480p', 'AVC1', 'OPUS', True, False): (False, False),
            ('480p', 'AVC1', 'OPUS', False, True): (False, False),
            ('480p', 'AVC1', 'OPUS', False, False): (False, False),
            ('480p', 'VP9', 'MP4A', True, True): (False, False),
            ('480p', 'VP9', 'MP4A', True, False): (False, False),
            ('480p', 'VP9', 'MP4A', False, True): (False, False),
            ('480p', 'VP9', 'MP4A', False, False): (False, False),
            ('480p', 'VP9', 'OPUS', True, True): (False, False),
            ('480p', 'VP9', 'OPUS', True, False): (False, False),
            ('480p', 'VP9', 'OPUS', False, True): (False, False),
            ('480p', 'VP9', 'OPUS', False, False): (False, False),
            ('720p', 'AVC1', 'MP4A', True, True): (False, False),
            ('720p', 'AVC1', 'MP4A', True, False): (False, False),
            ('720p', 'AVC1', 'MP4A', False, True): (False, False),
            ('720p', 'AVC1', 'MP4A', False, False): (True, '22'),      # Exact match
            ('720p', 'AVC1', 'OPUS', True, True): (False, False),
            ('720p', 'AVC1', 'OPUS', True, False): (False, False),
            ('720p', 'AVC1', 'OPUS', False, True): (False, False),
            ('720p', 'AVC1', 'OPUS', False, False): (False, False),
            ('720p', 'VP9', 'MP4A', True, True): (False, False),
            ('720p', 'VP9', 'MP4A', True, False): (False, False),
            ('720p', 'VP9', 'MP4A', False, True): (False, False),
            ('720p', 'VP9', 'MP4A', False, False): (False, False),
            ('720p', 'VP9', 'OPUS', True, True): (False, False),
            ('720p', 'VP9', 'OPUS', True, False): (False, False),
            ('720p', 'VP9', 'OPUS', False, True): (False, False),
            ('720p', 'VP9', 'OPUS', False, False): (False, False),
            ('1080p', 'AVC1', 'MP4A', True, True): (False, False),
            ('1080p', 'AVC1', 'MP4A', True, False): (False, False),
            ('1080p', 'AVC1', 'MP4A', False, True): (False, False),
            ('1080p', 'AVC1', 'MP4A', False, False): (False, False),
            ('1080p', 'AVC1', 'OPUS', True, True): (False, False),
            ('1080p', 'AVC1', 'OPUS', True, False): (False, False),
            ('1080p', 'AVC1', 'OPUS', False, True): (False, False),
            ('1080p', 'AVC1', 'OPUS', False, False): (False, False),
            ('1080p', 'VP9', 'MP4A', True, True): (False, False),
            ('1080p', 'VP9', 'MP4A', True, False): (False, False),
            ('1080p', 'VP9', 'MP4A', False, True): (False, False),
            ('1080p', 'VP9', 'MP4A', False, False): (False, False),
            ('1080p', 'VP9', 'OPUS', True, True): (False, False),
            ('1080p', 'VP9', 'OPUS', True, False): (False, False),
            ('1080p', 'VP9', 'OPUS', False, True): (False, False),
            ('1080p', 'VP9', 'OPUS', False, False): (False, False),
            ('1440p', 'AVC1', 'MP4A', True, True): (False, False),
            ('1440p', 'AVC1', 'MP4A', True, False): (False, False),
            ('1440p', 'AVC1', 'MP4A', False, True): (False, False),
            ('1440p', 'AVC1', 'MP4A', False, False): (False, False),
            ('1440p', 'AVC1', 'OPUS', True, True): (False, False),
            ('1440p', 'AVC1', 'OPUS', True, False): (False, False),
            ('1440p', 'AVC1', 'OPUS', False, True): (False, False),
            ('1440p', 'AVC1', 'OPUS', False, False): (False, False),
            ('1440p', 'VP9', 'MP4A', True, True): (False, False),
            ('1440p', 'VP9', 'MP4A', True, False): (False, False),
            ('1440p', 'VP9', 'MP4A', False, True): (False, False),
            ('1440p', 'VP9', 'MP4A', False, False): (False, False),
            ('1440p', 'VP9', 'OPUS', True, True): (False, False),
            ('1440p', 'VP9', 'OPUS', True, False): (False, False),
            ('1440p', 'VP9', 'OPUS', False, True): (False, False),
            ('1440p', 'VP9', 'OPUS', False, False): (False, False),
            ('2160p', 'AVC1', 'MP4A', True, True): (False, False),
            ('2160p', 'AVC1', 'MP4A', True, False): (False, False),
            ('2160p', 'AVC1', 'MP4A', False, True): (False, False),
            ('2160p', 'AVC1', 'MP4A', False, False): (False, False),
            ('2160p', 'AVC1', 'OPUS', True, True): (False, False),
            ('2160p', 'AVC1', 'OPUS', True, False): (False, False),
            ('2160p', 'AVC1', 'OPUS', False, True): (False, False),
            ('2160p', 'AVC1', 'OPUS', False, False): (False, False),
            ('2160p', 'VP9', 'MP4A', True, True): (False, False),
            ('2160p', 'VP9', 'MP4A', True, False): (False, False),
            ('2160p', 'VP9', 'MP4A', False, True): (False, False),
            ('2160p', 'VP9', 'MP4A', False, False): (False, False),
            ('2160p', 'VP9', 'OPUS', True, True): (False, False),
            ('2160p', 'VP9', 'OPUS', True, False): (False, False),
            ('2160p', 'VP9', 'OPUS', False, True): (False, False),
            ('2160p', 'VP9', 'OPUS', False, False): (False, False),
            ('4320p', 'AVC1', 'MP4A', True, True): (False, False),
            ('4320p', 'AVC1', 'MP4A', True, False): (False, False),
            ('4320p', 'AVC1', 'MP4A', False, True): (False, False),
            ('4320p', 'AVC1', 'MP4A', False, False): (False, False),
            ('4320p', 'AVC1', 'OPUS', True, True): (False, False),
            ('4320p', 'AVC1', 'OPUS', True, False): (False, False),
            ('4320p', 'AVC1', 'OPUS', False, True): (False, False),
            ('4320p', 'AVC1', 'OPUS', False, False): (False, False),
            ('4320p', 'VP9', 'MP4A', True, True): (False, False),
            ('4320p', 'VP9', 'MP4A', True, False): (False, False),
            ('4320p', 'VP9', 'MP4A', False, True): (False, False),
            ('4320p', 'VP9', 'MP4A', False, False): (False, False),
            ('4320p', 'VP9', 'OPUS', True, True): (False, False),
            ('4320p', 'VP9', 'OPUS', True, False): (False, False),
            ('4320p', 'VP9', 'OPUS', False, True): (False, False),
            ('4320p', 'VP9', 'OPUS', False, False): (False, False),
        }
        for params, expected in expected_matches.items():
            resolution, vcodec, acodec, prefer_60fps, prefer_hdr = params
            expected_match_type, expected_format_code = expected
            self.source.source_resolution = resolution
            self.source.source_vcodec = vcodec
            self.source.source_acodec = acodec
            self.source.prefer_60fps = prefer_60fps
            self.source.prefer_hdr = prefer_hdr
            match_type, format_code = self.media.get_best_combined_format()
            self.assertEqual(format_code, expected_format_code)
            self.assertEqual(match_type, expected_match_type)

    def test_audio_exact_format_matching(self):
        self.source.fallback = Val(Fallback.FAIL)
        self.media.metadata = all_test_metadata['boring']
        self.media.save()
        expected_matches = {
            # (format, vcodec, acodec, prefer_60fps, prefer_hdr): (match_type, code),
            ('360p', 'AVC1', 'MP4A', True, False): (True, '140'),
            ('360p', 'AVC1', 'MP4A', False, True): (True, '140'),
            ('360p', 'AVC1', 'MP4A', False, False): (True, '140'),
            ('360p', 'AVC1', 'OPUS', True, True): (True, '251'),
            ('360p', 'AVC1', 'OPUS', True, False): (True, '251'),
            ('360p', 'AVC1', 'OPUS', False, True): (True, '251'),
            ('360p', 'AVC1', 'OPUS', False, False): (True, '251'),
            ('360p', 'VP9', 'MP4A', True, True): (True, '140'),
            ('360p', 'VP9', 'MP4A', True, False): (True, '140'),
            ('360p', 'VP9', 'MP4A', False, True): (True, '140'),
            ('360p', 'VP9', 'MP4A', False, False): (True, '140'),
            ('360p', 'VP9', 'OPUS', True, True): (True, '251'),
            ('360p', 'VP9', 'OPUS', True, False): (True, '251'),
            ('360p', 'VP9', 'OPUS', False, True): (True, '251'),
            ('360p', 'VP9', 'OPUS', False, False): (True, '251'),
            ('480p', 'AVC1', 'MP4A', True, True): (True, '140'),
            ('480p', 'AVC1', 'MP4A', True, False): (True, '140'),
            ('480p', 'AVC1', 'MP4A', False, True): (True, '140'),
            ('480p', 'AVC1', 'MP4A', False, False): (True, '140'),
            ('480p', 'AVC1', 'OPUS', True, True): (True, '251'),
            ('480p', 'AVC1', 'OPUS', True, False): (True, '251'),
            ('480p', 'AVC1', 'OPUS', False, True): (True, '251'),
            ('480p', 'AVC1', 'OPUS', False, False): (True, '251'),
            ('480p', 'VP9', 'MP4A', True, True): (True, '140'),
            ('480p', 'VP9', 'MP4A', True, False): (True, '140'),
            ('480p', 'VP9', 'MP4A', False, True): (True, '140'),
            ('480p', 'VP9', 'MP4A', False, False): (True, '140'),
            ('480p', 'VP9', 'OPUS', True, True): (True, '251'),
            ('480p', 'VP9', 'OPUS', True, False): (True, '251'),
            ('480p', 'VP9', 'OPUS', False, True): (True, '251'),
            ('480p', 'VP9', 'OPUS', False, False): (True, '251'),
            ('720p', 'AVC1', 'MP4A', True, True): (True, '140'),
            ('720p', 'AVC1', 'MP4A', True, False): (True, '140'),
            ('720p', 'AVC1', 'MP4A', False, True): (True, '140'),
            ('720p', 'AVC1', 'MP4A', False, False): (True, '140'),
            ('720p', 'AVC1', 'OPUS', True, True): (True, '251'),
            ('720p', 'AVC1', 'OPUS', True, False): (True, '251'),
            ('720p', 'AVC1', 'OPUS', False, True): (True, '251'),
            ('720p', 'AVC1', 'OPUS', False, False): (True, '251'),
            ('720p', 'VP9', 'MP4A', True, True): (True, '140'),
            ('720p', 'VP9', 'MP4A', True, False): (True, '140'),
            ('720p', 'VP9', 'MP4A', False, True): (True, '140'),
            ('720p', 'VP9', 'MP4A', False, False): (True, '140'),
            ('720p', 'VP9', 'OPUS', True, True): (True, '251'),
            ('720p', 'VP9', 'OPUS', True, False): (True, '251'),
            ('720p', 'VP9', 'OPUS', False, True): (True, '251'),
            ('720p', 'VP9', 'OPUS', False, False): (True, '251'),
            ('1080p', 'AVC1', 'MP4A', True, True): (True, '140'),
            ('1080p', 'AVC1', 'MP4A', True, False): (True, '140'),
            ('1080p', 'AVC1', 'MP4A', False, True): (True, '140'),
            ('1080p', 'AVC1', 'MP4A', False, False): (True, '140'),
            ('1080p', 'AVC1', 'OPUS', True, True): (True, '251'),
            ('1080p', 'AVC1', 'OPUS', True, False): (True, '251'),
            ('1080p', 'AVC1', 'OPUS', False, True): (True, '251'),
            ('1080p', 'AVC1', 'OPUS', False, False): (True, '251'),
            ('1080p', 'VP9', 'MP4A', True, True): (True, '140'),
            ('1080p', 'VP9', 'MP4A', True, False): (True, '140'),
            ('1080p', 'VP9', 'MP4A', False, True): (True, '140'),
            ('1080p', 'VP9', 'MP4A', False, False): (True, '140'),
            ('1080p', 'VP9', 'OPUS', True, True): (True, '251'),
            ('1080p', 'VP9', 'OPUS', True, False): (True, '251'),
            ('1080p', 'VP9', 'OPUS', False, True): (True, '251'),
            ('1080p', 'VP9', 'OPUS', False, False): (True, '251'),
            ('1440p', 'AVC1', 'MP4A', True, True): (True, '140'),
            ('1440p', 'AVC1', 'MP4A', True, False): (True, '140'),
            ('1440p', 'AVC1', 'MP4A', False, True): (True, '140'),
            ('1440p', 'AVC1', 'MP4A', False, False): (True, '140'),
            ('1440p', 'AVC1', 'OPUS', True, True): (True, '251'),
            ('1440p', 'AVC1', 'OPUS', True, False): (True, '251'),
            ('1440p', 'AVC1', 'OPUS', False, True): (True, '251'),
            ('1440p', 'AVC1', 'OPUS', False, False): (True, '251'),
            ('1440p', 'VP9', 'MP4A', True, True): (True, '140'),
            ('1440p', 'VP9', 'MP4A', True, False): (True, '140'),
            ('1440p', 'VP9', 'MP4A', False, True): (True, '140'),
            ('1440p', 'VP9', 'MP4A', False, False): (True, '140'),
            ('1440p', 'VP9', 'OPUS', True, True): (True, '251'),
            ('1440p', 'VP9', 'OPUS', True, False): (True, '251'),
            ('1440p', 'VP9', 'OPUS', False, True): (True, '251'),
            ('1440p', 'VP9', 'OPUS', False, False): (True, '251'),
            ('2160p', 'AVC1', 'MP4A', True, True): (True, '140'),
            ('2160p', 'AVC1', 'MP4A', True, False): (True, '140'),
            ('2160p', 'AVC1', 'MP4A', False, True): (True, '140'),
            ('2160p', 'AVC1', 'MP4A', False, False): (True, '140'),
            ('2160p', 'AVC1', 'OPUS', True, True): (True, '251'),
            ('2160p', 'AVC1', 'OPUS', True, False): (True, '251'),
            ('2160p', 'AVC1', 'OPUS', False, True): (True, '251'),
            ('2160p', 'AVC1', 'OPUS', False, False): (True, '251'),
            ('2160p', 'VP9', 'MP4A', True, True): (True, '140'),
            ('2160p', 'VP9', 'MP4A', True, False): (True, '140'),
            ('2160p', 'VP9', 'MP4A', False, True): (True, '140'),
            ('2160p', 'VP9', 'MP4A', False, False): (True, '140'),
            ('2160p', 'VP9', 'OPUS', True, True): (True, '251'),
            ('2160p', 'VP9', 'OPUS', True, False): (True, '251'),
            ('2160p', 'VP9', 'OPUS', False, True): (True, '251'),
            ('2160p', 'VP9', 'OPUS', False, False): (True, '251'),
            ('4320p', 'AVC1', 'MP4A', True, True): (True, '140'),
            ('4320p', 'AVC1', 'MP4A', True, False): (True, '140'),
            ('4320p', 'AVC1', 'MP4A', False, True): (True, '140'),
            ('4320p', 'AVC1', 'MP4A', False, False): (True, '140'),
            ('4320p', 'AVC1', 'OPUS', True, True): (True, '251'),
            ('4320p', 'AVC1', 'OPUS', True, False): (True, '251'),
            ('4320p', 'AVC1', 'OPUS', False, True): (True, '251'),
            ('4320p', 'AVC1', 'OPUS', False, False): (True, '251'),
            ('4320p', 'VP9', 'MP4A', True, True): (True, '140'),
            ('4320p', 'VP9', 'MP4A', True, False): (True, '140'),
            ('4320p', 'VP9', 'MP4A', False, True): (True, '140'),
            ('4320p', 'VP9', 'MP4A', False, False): (True, '140'),
            ('4320p', 'VP9', 'OPUS', True, True): (True, '251'),
            ('4320p', 'VP9', 'OPUS', True, False): (True, '251'),
            ('4320p', 'VP9', 'OPUS', False, True): (True, '251'),
            ('4320p', 'VP9', 'OPUS', False, False): (True, '251'),
            ('audio', 'AVC1', 'MP4A', True, True): (True, '140'),
            ('audio', 'AVC1', 'MP4A', True, False): (True, '140'),
            ('audio', 'AVC1', 'MP4A', False, True): (True, '140'),
            ('audio', 'AVC1', 'MP4A', False, False): (True, '140'),
            ('audio', 'AVC1', 'OPUS', True, True): (True, '251'),
            ('audio', 'AVC1', 'OPUS', True, False): (True, '251'),
            ('audio', 'AVC1', 'OPUS', False, True): (True, '251'),
            ('audio', 'AVC1', 'OPUS', False, False): (True, '251'),
            ('audio', 'VP9', 'MP4A', True, True): (True, '140'),
            ('audio', 'VP9', 'MP4A', True, False): (True, '140'),
            ('audio', 'VP9', 'MP4A', False, True): (True, '140'),
            ('audio', 'VP9', 'MP4A', False, False): (True, '140'),
            ('audio', 'VP9', 'OPUS', True, True): (True, '251'),
            ('audio', 'VP9', 'OPUS', True, False): (True, '251'),
            ('audio', 'VP9', 'OPUS', False, True): (True, '251'),
            ('audio', 'VP9', 'OPUS', False, False): (True, '251'),
        }
        for params, expected in expected_matches.items():
            resolution, vcodec, acodec, prefer_60fps, prefer_hdr = params
            expeceted_match_type, expected_format_code = expected
            self.source.source_resolution = resolution
            self.source.source_vcodec = vcodec
            self.source.source_acodec = acodec
            self.source.prefer_60fps = prefer_60fps
            self.source.prefer_hdr = prefer_hdr
            match_type, format_code = self.media.get_best_audio_format()
            self.assertEqual(format_code, expected_format_code)
            self.assertEqual(match_type, expeceted_match_type)

    def test_video_exact_format_matching(self):
        self.source.fallback = Val(Fallback.FAIL)
        # Test no 60fps, no HDR metadata
        self.media.metadata = all_test_metadata['boring']
        self.media.save()
        expected_matches = {
            # (format, vcodec, prefer_60fps, prefer_hdr): (match_type, code),
            ('360p', 'AVC1', False, True): (False, False),
            ('360p', 'AVC1', True, False): (False, False),
            ('360p', 'AVC1', True, True): (False, False),
            ('360p', 'VP9', False, False): (True, '243'),              # Exact match
            ('360p', 'VP9', False, True): (False, False),
            ('360p', 'VP9', True, False): (False, False),
            ('360p', 'VP9', True, True): (False, False),
            ('480p', 'AVC1', False, False): (True, '135'),             # Exact match
            ('480p', 'AVC1', False, True): (False, False),
            ('480p', 'AVC1', True, False): (False, False),
            ('480p', 'AVC1', True, True): (False, False),
            ('480p', 'VP9', False, False): (True, '244'),              # Exact match
            ('480p', 'VP9', False, True): (False, False),
            ('480p', 'VP9', True, False): (False, False),
            ('480p', 'VP9', True, True): (False, False),
            ('720p', 'AVC1', False, False): (True, '136'),             # Exact match
            ('720p', 'AVC1', False, True): (False, False),
            ('720p', 'AVC1', True, False): (False, False),
            ('720p', 'AVC1', True, True): (False, False),
            ('720p', 'VP9', False, False): (True, '247'),              # Exact match
            ('720p', 'VP9', False, True): (False, False),
            ('720p', 'VP9', True, False): (False, False),
            ('720p', 'VP9', True, True): (False, False),
            ('1080p', 'AVC1', False, False): (True, '137'),            # Exact match
            ('1080p', 'AVC1', False, True): (False, False),
            ('1080p', 'AVC1', True, False): (False, False),
            ('1080p', 'AVC1', True, True): (False, False),
            ('1080p', 'VP9', False, False): (True, '248'),             # Exact match
            ('1080p', 'VP9', False, True): (False, False),
            ('1080p', 'VP9', True, False): (False, False),
            ('1080p', 'VP9', True, True): (False, False),
            # No test formats in 'boring' metadata > 1080p
        }
        for params, expected in expected_matches.items():
            resolution, vcodec, prefer_60fps, prefer_hdr = params
            expeceted_match_type, expected_format_code = expected
            self.source.source_resolution = resolution
            self.source.source_vcodec = vcodec
            self.source.prefer_60fps = prefer_60fps
            self.source.prefer_hdr = prefer_hdr
            match_type, format_code = self.media.get_best_video_format()
            self.assertEqual(format_code, expected_format_code)
            self.assertEqual(match_type, expeceted_match_type)
        # Test 60fps metadata
        self.media.metadata = all_test_metadata['60fps']
        self.media.save()
        expected_matches = {
            # (format, vcodec, prefer_60fps, prefer_hdr): (match_type, code),
            ('360p', 'AVC1', False, True): (False, False),
            ('360p', 'AVC1', True, False): (False, False),
            ('360p', 'AVC1', True, True): (False, False),
            ('360p', 'VP9', False, False): (True, '243'),              # Exact match
            ('360p', 'VP9', False, True): (False, False),
            ('360p', 'VP9', True, False): (False, False),
            ('360p', 'VP9', True, True): (False, False),
            ('480p', 'AVC1', False, False): (True, '135'),             # Exact match
            ('480p', 'AVC1', False, True): (False, False),
            ('480p', 'AVC1', True, False): (False, False),
            ('480p', 'AVC1', True, True): (False, False),
            ('480p', 'VP9', False, False): (True, '244'),              # Exact match
            ('480p', 'VP9', False, True): (False, False),
            ('480p', 'VP9', True, False): (False, False),
            ('480p', 'VP9', True, True): (False, False),
            ('720p', 'AVC1', False, False): (True, '136'),             # Exact match
            ('720p', 'AVC1', False, True): (False, False),
            ('720p', 'AVC1', True, False): (True, '298'),              # Exact match, 60fps
            ('720p', 'AVC1', True, True): (False, False),
            ('720p', 'VP9', False, False): (True, '247'),              # Exact match
            ('720p', 'VP9', False, True): (False, False),
            ('720p', 'VP9', True, False): (True, '302'),               # Exact match, 60fps
            ('720p', 'VP9', True, True): (False, False),
            # No test formats in '60fps' metadata > 720p
        }
        for params, expected in expected_matches.items():
            resolution, vcodec, prefer_60fps, prefer_hdr = params
            expeceted_match_type, expected_format_code = expected
            self.source.source_resolution = resolution
            self.source.source_vcodec = vcodec
            self.source.prefer_60fps = prefer_60fps
            self.source.prefer_hdr = prefer_hdr
            match_type, format_code = self.media.get_best_video_format()
            self.assertEqual(format_code, expected_format_code)
            self.assertEqual(match_type, expeceted_match_type)
        # Test hdr metadata
        self.media.metadata = all_test_metadata['hdr']
        self.media.save()
        expected_matches = {
            # (format, vcodec, prefer_60fps, prefer_hdr): (match_type, code),
            ('360p', 'AVC1', False, True): (False, False),
            ('360p', 'AVC1', True, False): (False, False),
            ('360p', 'AVC1', True, True): (False, False),
            ('360p', 'VP9', False, False): (True, '243'),              # Exact match
            ('360p', 'VP9', False, True): (True, '332'),               # Exact match, hdr
            ('360p', 'VP9', True, False): (False, False),
            ('360p', 'VP9', True, True): (False, False),
            ('480p', 'AVC1', False, False): (True, '135'),             # Exact match
            ('480p', 'AVC1', False, True): (False, False),
            ('480p', 'AVC1', True, False): (False, False),
            ('480p', 'AVC1', True, True): (False, False),
            ('480p', 'VP9', False, False): (True, '244'),              # Exact match
            ('480p', 'VP9', False, True): (True, '333'),               # Exact match, hdr
            ('480p', 'VP9', True, False): (False, False),
            ('480p', 'VP9', True, True): (False, False),
            ('720p', 'AVC1', False, False): (True, '136'),             # Exact match
            ('720p', 'AVC1', False, True): (False, False),
            ('720p', 'AVC1', True, False): (False, False),
            ('720p', 'AVC1', True, True): (False, False),
            ('720p', 'VP9', False, False): (True, '247'),              # Exact match
            ('720p', 'VP9', False, True): (True, '334'),               # Exact match, hdr
            ('720p', 'VP9', True, False): (False, False),
            ('720p', 'VP9', True, True): (False, False),
            ('1440p', 'AVC1', False, False): (False, False),
            ('1440p', 'AVC1', False, True): (False, False),
            ('1440p', 'AVC1', True, False): (False, False),
            ('1440p', 'AVC1', True, True): (False, False),
            ('1440p', 'VP9', False, False): (True, '271'),             # Exact match
            ('1440p', 'VP9', False, True): (True, '336'),              # Exact match, hdr
            ('1440p', 'VP9', True, False): (False, False),
            ('1440p', 'VP9', True, True): (False, False),
            ('2160p', 'AVC1', False, False): (False, False),
            ('2160p', 'AVC1', False, True): (False, False),
            ('2160p', 'AVC1', True, False): (False, False),
            ('2160p', 'AVC1', True, True): (False, False),
            ('2160p', 'VP9', False, False): (True, '313'),             # Exact match
            ('2160p', 'VP9', False, True): (True, '337'),              # Exact match, hdr
            ('2160p', 'VP9', True, False): (False, False),
            ('2160p', 'VP9', True, True): (False, False),
            # No test formats in 'hdr' metadata > 4k
        }
        for params, expected in expected_matches.items():
            resolution, vcodec, prefer_60fps, prefer_hdr = params
            expeceted_match_type, expected_format_code = expected
            self.source.source_resolution = resolution
            self.source.source_vcodec = vcodec
            self.source.prefer_60fps = prefer_60fps
            self.source.prefer_hdr = prefer_hdr
            match_type, format_code = self.media.get_best_video_format()
            self.assertEqual(format_code, expected_format_code)
            self.assertEqual(match_type, expeceted_match_type)
        # Test 60fps+hdr metadata
        self.media.metadata = all_test_metadata['60fps+hdr']
        self.media.save()
        expected_matches = {
            # (format, vcodec, prefer_60fps, prefer_hdr): (match_type, code),
            ('360p', 'AVC1', False, True): (False, False),
            ('360p', 'AVC1', True, False): (False, False),
            ('360p', 'AVC1', True, True): (False, False),
            ('360p', 'VP9', False, False): (True, '243'),              # Exact match
            ('360p', 'VP9', False, True): (True, '332'),               # Exact match, hdr
            ('360p', 'VP9', True, False): (False, False),
            ('360p', 'VP9', True, True): (True, '332'),                # Exact match, 60fps+hdr
            ('480p', 'AVC1', False, False): (True, '135'),             # Exact match
            ('480p', 'AVC1', False, True): (False, False),
            ('480p', 'AVC1', True, False): (False, False),
            ('480p', 'AVC1', True, True): (False, False),
            ('480p', 'VP9', False, False): (True, '244'),              # Exact match
            ('480p', 'VP9', False, True): (True, '333'),               # Exact match, hdr
            ('480p', 'VP9', True, False): (False, False),
            ('480p', 'VP9', True, True): (True, '333'),                # Exact match, 60fps+hdr
            ('720p', 'AVC1', False, False): (True, '136'),             # Exact match
            ('720p', 'AVC1', False, True): (False, False),
            ('720p', 'AVC1', True, False): (True, '298'),              # Exact match, 60fps
            ('720p', 'AVC1', True, True): (False, False),
            ('720p', 'VP9', False, False): (True, '247'),              # Exact match
            ('720p', 'VP9', False, True): (True, '334'),               # Exact match, hdr
            ('720p', 'VP9', True, False): (True, '302'),               # Exact match, 60fps
            ('720p', 'VP9', True, True): (True, '334'),                # Exact match, 60fps+hdr
            ('1440p', 'AVC1', False, False): (False, False),
            ('1440p', 'AVC1', False, True): (False, False),
            ('1440p', 'AVC1', True, False): (False, False),
            ('1440p', 'AVC1', True, True): (False, False),
            ('1440p', 'VP9', False, False): (False, False),
            ('1440p', 'VP9', False, True): (True, '336'),              # Exact match, hdr
            ('1440p', 'VP9', True, False): (True, '308'),              # Exact match, 60fps
            ('1440p', 'VP9', True, True): (True, '336'),               # Exact match, 60fps+hdr
            ('2160p', 'AVC1', False, False): (False, False),
            ('2160p', 'AVC1', False, True): (False, False),
            ('2160p', 'AVC1', True, False): (False, False),
            ('2160p', 'AVC1', True, True): (False, False),
            ('2160p', 'VP9', False, False): (False, False),
            ('2160p', 'VP9', False, True): (True, '337'),              # Exact match, hdr
            ('2160p', 'VP9', True, False): (True, '315'),              # Exact match, 60fps
            ('2160p', 'VP9', True, True): (True, '337'),               # Exact match, 60fps+hdr
            ('4320p', 'AVC1', False, False): (False, False),
            ('4320p', 'AVC1', False, True): (False, False),
            ('4320p', 'AVC1', True, False): (False, False),
            ('4320p', 'AVC1', True, True): (False, False),
            ('4320p', 'VP9', False, False): (False, False),
            ('4320p', 'VP9', False, True): (False, False),
            ('4320p', 'VP9', True, False): (True, '272'),              # Exact match, 60fps
            ('4320p', 'VP9', True, True): (False, False),
        }
        for params, expected in expected_matches.items():
            resolution, vcodec, prefer_60fps, prefer_hdr = params
            expeceted_match_type, expected_format_code = expected
            self.source.source_resolution = resolution
            self.source.source_vcodec = vcodec
            self.source.prefer_60fps = prefer_60fps
            self.source.prefer_hdr = prefer_hdr
            match_type, format_code = self.media.get_best_video_format()
            self.assertEqual(format_code, expected_format_code)
            self.assertEqual(match_type, expeceted_match_type)

    def test_video_require_codec_format_matching(self):
        self.media.source.fallback = Val(Fallback.REQUIRE_CODEC)
        # Test no 60fps, no HDR metadata
        self.media.metadata = all_test_metadata['boring']
        self.media.save()
        expected_matches = {
            # (format, vcodec, prefer_60fps, prefer_hdr): (match_type, code),
            ('360p', 'AVC1', False, False): (True, '134'),             # Exact match
            ('360p', 'AVC1', False, True): (False, '134'),             # Fallback match, no hdr
            ('360p', 'AVC1', True, False): (False, '134'),             # Fallback match, no 60fps
            ('360p', 'AVC1', True, True): (False, '134'),              # Fallback match, no 60fps+hdr
            ('360p', 'VP9', False, False): (True, '243'),              # Exact match
            ('360p', 'VP9', False, True): (False, '243'),              # Fallback match, no hdr
            ('360p', 'VP9', True, False): (False, '243'),              # Fallback match, no 60fps
            ('360p', 'VP9', True, True): (False, '243'),               # Fallback match, no 60fps+hdr
            ('480p', 'AVC1', False, False): (True, '135'),             # Exact match
            ('480p', 'AVC1', False, True): (False, '135'),             # Fallback match, no hdr
            ('480p', 'AVC1', True, False): (False, '135'),             # Fallback match, no 60fps
            ('480p', 'AVC1', True, True): (False, '135'),              # Fallback match, no 60fps+hdr
            ('480p', 'VP9', False, False): (True, '244'),              # Exact match
            ('480p', 'VP9', False, True): (False, '244'),              # Fallback match, no hdr
            ('480p', 'VP9', True, False): (False, '244'),              # Fallback match, no 60fps
            ('480p', 'VP9', True, True): (False, '244'),               # Fallback match, no 60fps+hdr
            ('720p', 'AVC1', False, False): (True, '136'),             # Exact match
            ('720p', 'AVC1', False, True): (False, '136'),             # Fallback match, no hdr
            ('720p', 'AVC1', True, False): (False, '136'),             # Fallback match, no 60fps
            ('720p', 'AVC1', True, True): (False, '136'),              # Fallback match, no 60fps+hdr
            ('720p', 'VP9', False, False): (True, '247'),              # Exact match
            ('720p', 'VP9', False, True): (False, '247'),              # Fallback match, no hdr
            ('720p', 'VP9', True, False): (False, '247'),              # Fallback match, no 60fps
            ('720p', 'VP9', True, True): (False, '247'),               # Fallback match, no 60fps+hdr
            ('1080p', 'AVC1', False, False): (True, '137'),            # Exact match
            ('1080p', 'AVC1', False, True): (False, '137'),            # Fallback match, no hdr
            ('1080p', 'AVC1', True, False): (False, '137'),            # Fallback match, no 60fps
            ('1080p', 'AVC1', True, True): (False, '137'),             # Fallback match, no 60fps+hdr
            ('1080p', 'VP9', False, False): (True, '248'),             # Exact match
            ('1080p', 'VP9', False, True): (False, '248'),             # Fallback match, no hdr
            ('1080p', 'VP9', True, False): (False, '248'),             # Fallback match, no 60fps
            ('1080p', 'VP9', True, True): (False, '248'),              # Fallback match, no 60fps+hdr
            # No test formats in 'boring' metadata > 1080p
        }
        for params, expected in expected_matches.items():
            resolution, vcodec, prefer_60fps, prefer_hdr = params
            expeceted_match_type, expected_format_code = expected
            self.source.source_resolution = resolution
            self.source.source_vcodec = vcodec
            self.source.prefer_60fps = prefer_60fps
            self.source.prefer_hdr = prefer_hdr
            match_type, format_code = self.media.get_best_video_format()
            self.assertEqual(format_code, expected_format_code)
            self.assertEqual(match_type, expeceted_match_type)
        # Test 60fps metadata
        self.media.metadata = all_test_metadata['60fps']
        self.media.save()
        expected_matches = {
            # (format, vcodec, prefer_60fps, prefer_hdr): (match_type, code),
            ('360p', 'AVC1', False, False): (True, '134'),             # Exact match
            ('360p', 'AVC1', False, True): (False, '134'),             # Fallback match, no hdr
            ('360p', 'AVC1', True, False): (False, '134'),             # Fallback match, no 60fps
            ('360p', 'AVC1', True, True): (False, '134'),              # Fallback match, no 60fps+hdr
            ('360p', 'VP9', False, False): (True, '243'),              # Exact match
            ('360p', 'VP9', False, True): (False, '243'),              # Fallback match, no hdr
            ('360p', 'VP9', True, False): (False, '243'),              # Fallback match, no 60fps
            ('360p', 'VP9', True, True): (False, '243'),               # Fallback match, no 60fps+hdr
            ('480p', 'AVC1', False, False): (True, '135'),             # Exact match
            ('480p', 'AVC1', False, True): (False, '135'),             # Fallback match, no hdr
            ('480p', 'AVC1', True, False): (False, '135'),             # Fallback match, no 60fps
            ('480p', 'AVC1', True, True): (False, '135'),              # Fallback match, no 60fps+hdr
            ('480p', 'VP9', False, False): (True, '244'),              # Exact match
            ('480p', 'VP9', False, True): (False, '244'),              # Fallback match, no hdr
            ('480p', 'VP9', True, False): (False, '244'),              # Fallback match, no 60fps
            ('480p', 'VP9', True, True): (False, '244'),               # Fallback match, no 60fps+hdr
            ('720p', 'AVC1', False, False): (True, '136'),             # Exact match
            ('720p', 'AVC1', False, True): (False, '136'),             # Fallback match, no hdr
            ('720p', 'AVC1', True, False): (True, '298'),              # Exact match, 60fps
            ('720p', 'AVC1', True, True): (False, '298'),              # Fallback match, 60fps, no hdr
            ('720p', 'VP9', False, False): (True, '247'),              # Exact match
            ('720p', 'VP9', False, True): (False, '247'),              # Fallback match, no hdr
            ('720p', 'VP9', True, False): (True, '302'),               # Exact match, 60fps
            ('720p', 'VP9', True, True): (False, '302'),               # Fallback match, 60fps, no hdr
            # No test formats in '60fps' metadata > 720p
        }
        for params, expected in expected_matches.items():
            resolution, vcodec, prefer_60fps, prefer_hdr = params
            expeceted_match_type, expected_format_code = expected
            self.source.source_resolution = resolution
            self.source.source_vcodec = vcodec
            self.source.prefer_60fps = prefer_60fps
            self.source.prefer_hdr = prefer_hdr
            match_type, format_code = self.media.get_best_video_format()
            self.assertEqual(format_code, expected_format_code)
            self.assertEqual(match_type, expeceted_match_type)
        # Test hdr metadata
        self.media.metadata = all_test_metadata['hdr']
        self.media.save()
        expected_matches = {
            # (format, vcodec, prefer_60fps, prefer_hdr): (match_type, code),
            ('360p', 'AVC1', False, False): (True, '134'),             # Exact match
            ('360p', 'AVC1', False, True): (False, '134'),             # Fallback match, no hdr
            ('360p', 'AVC1', True, False): (False, '134'),             # Fallback match, no 60fps
            ('360p', 'AVC1', True, True): (False, '134'),              # Fallback match, no 60fps+hdr
            ('360p', 'VP9', False, False): (True, '243'),              # Exact match
            ('360p', 'VP9', False, True): (True, '332'),               # Exact match, hdr
            ('360p', 'VP9', True, False): (False, '243'),              # Fallback match, no 60fps
            ('360p', 'VP9', True, True): (False, '332'),               # Fallback match, hdr, no 60fps
            ('480p', 'AVC1', False, False): (True, '135'),             # Exact match
            ('480p', 'AVC1', False, True): (False, '135'),             # Fallback match, no hdr
            ('480p', 'AVC1', True, False): (False, '135'),             # Fallback match, no 60fps
            ('480p', 'AVC1', True, True): (False, '135'),              # Fallback match, no 60fps+hdr
            ('480p', 'VP9', False, False): (True, '244'),              # Exact match
            ('480p', 'VP9', False, True): (True, '333'),               # Exact match, hdr
            ('480p', 'VP9', True, False): (False, '244'),              # Fallback match, no 60fps
            ('480p', 'VP9', True, True): (False, '333'),               # Fallback match, hdr, no 60fps
            ('720p', 'AVC1', False, False): (True, '136'),             # Exact match
            ('720p', 'AVC1', False, True): (False, '136'),             # Fallback match, no hdr
            ('720p', 'AVC1', True, False): (False, '136'),             # Fallback match, no 60fps
            ('720p', 'AVC1', True, True): (False, '136'),              # Fallback match, no 60fps+hdr
            ('720p', 'VP9', False, False): (True, '247'),              # Exact match
            ('720p', 'VP9', False, True): (True, '334'),               # Exact match, hdr
            ('720p', 'VP9', True, False): (False, '247'),              # Fallback match, no 60fps
            ('720p', 'VP9', True, True): (False, '334'),               # Fallback match, hdr, no 60fps
            ('1440p', 'AVC1', False, False): (False, '137'),           # Fallback match, dropped to 1080p (no 1440p AVC1)
            ('1440p', 'AVC1', False, True): (False, '137'),            # Fallback match, no hdr, dropped to 1080p (no 1440p AVC1)
            ('1440p', 'AVC1', True, False): (False, '137'),            # Fallback match, no 60fps, dropped to 1080p (no 1440p AVC1)
            ('1440p', 'AVC1', True, True): (False, '137'),             # Fallback match, no 60fps+hdr, dropped to 1080p (no 1440p AVC1)
            ('1440p', 'VP9', False, False): (True, '271'),             # Exact match
            ('1440p', 'VP9', False, True): (True, '336'),              # Exact match, hdr
            ('1440p', 'VP9', True, False): (False, '271'),             # Fallback match, no 60fps
            ('1440p', 'VP9', True, True): (False, '336'),              # Fallback match, hdr, no 60fps
            ('2160p', 'AVC1', False, False): (False, '137'),           # Fallback match, dropped to 1080p (no 2160p AVC1)
            ('2160p', 'AVC1', False, True): (False, '137'),            # Fallback match, no hdr, dropped to 1080p (no 2160p AVC1)
            ('2160p', 'AVC1', True, False): (False, '137'),            # Fallback match, no 60fps, dropped to 1080p (no 2160p AVC1)
            ('2160p', 'AVC1', True, True): (False, '137'),             # Fallback match, no 60fps+hdr, dropped to 1080p (no 2160p AVC1)
            ('2160p', 'VP9', False, False): (True, '313'),             # Exact match
            ('2160p', 'VP9', False, True): (True, '337'),              # Exact match, hdr
            ('2160p', 'VP9', True, False): (False, '313'),             # Fallback match, no 60fps
            ('2160p', 'VP9', True, True): (False, '337'),              # Fallback match, hdr, no 60fps
            # No test formats in 'hdr' metadata > 4k
        }
        for params, expected in expected_matches.items():
            resolution, vcodec, prefer_60fps, prefer_hdr = params
            expeceted_match_type, expected_format_code = expected
            self.source.source_resolution = resolution
            self.source.source_vcodec = vcodec
            self.source.prefer_60fps = prefer_60fps
            self.source.prefer_hdr = prefer_hdr
            match_type, format_code = self.media.get_best_video_format()
            self.assertEqual(format_code, expected_format_code)
            self.assertEqual(match_type, expeceted_match_type)
        # Test 60fps+hdr metadata
        self.media.metadata = all_test_metadata['60fps+hdr']
        self.media.save()
        expected_matches = {
            # (format, vcodec, prefer_60fps, prefer_hdr): (match_type, code),
            ('360p', 'AVC1', False, False): (True, '134'),             # Exact match
            ('360p', 'AVC1', False, True): (False, '134'),             # Fallback match, no hdr
            ('360p', 'AVC1', True, False): (False, '134'),             # Fallback match, no 60fps
            ('360p', 'AVC1', True, True): (False, '134'),              # Fallback match, no 60fps+hdr
            ('360p', 'VP9', False, False): (True, '243'),              # Exact match
            ('360p', 'VP9', False, True): (True, '332'),               # Exact match, hdr
            ('360p', 'VP9', True, False): (False, '332'),              # Fallback match, 60fps, extra hdr
            ('360p', 'VP9', True, True): (True, '332'),                # Exact match, 60fps+hdr
            ('480p', 'AVC1', False, False): (True, '135'),             # Exact match
            ('480p', 'AVC1', False, True): (False, '135'),             # Fallback match, no hdr
            ('480p', 'AVC1', True, False): (False, '135'),             # Fallback match, no 60fps
            ('480p', 'AVC1', True, True): (False, '135'),              # Fallback match, no 60fps+hdr
            ('480p', 'VP9', False, False): (True, '244'),              # Exact match
            ('480p', 'VP9', False, True): (True, '333'),               # Exact match, hdr
            ('480p', 'VP9', True, False): (False, '333'),              # Fallback match, 60fps, extra hdr
            ('480p', 'VP9', True, True): (True, '333'),                # Exact match, 60fps+hdr
            ('720p', 'AVC1', False, False): (True, '136'),             # Exact match
            ('720p', 'AVC1', False, True): (False, '136'),             # Fallback match, no hdr
            ('720p', 'AVC1', True, False): (True, '298'),              # Exact match, 60fps
            ('720p', 'AVC1', True, True): (False, '298'),              # Fallback match, no hdr, 60fps
            ('720p', 'VP9', False, False): (True, '247'),              # Exact match
            ('720p', 'VP9', False, True): (True, '334'),               # Exact match, hdr, extra 60fps
            ('720p', 'VP9', True, False): (True, '302'),               # Exact match, 60fps
            ('720p', 'VP9', True, True): (True, '334'),                # Exact match, 60fps+hdr
            ('1440p', 'AVC1', False, False): (False, '136'),           # Fallback match, dropped to 720p (no 1440p AVC1)
            ('1440p', 'AVC1', False, True): (False, '299'),            # Fallback match, no hdr, extra 60fps, dropped to 1080p (no 1440p AVC1)
            ('1440p', 'AVC1', True, False): (False, '299'),            # Fallback match, no hdr, 60fps, dropped to 1080p (no 1440p AVC1)
            ('1440p', 'AVC1', True, True): (False, '299'),             # Fallback match, no hdr, 60fps, dropped to 1080p (no 1440p AVC1)
            ('1440p', 'VP9', False, False): (False, '308'),            # Fallback match, extra 60fps
            ('1440p', 'VP9', False, True): (True, '336'),              # Exact match, hdr, extra 60fps
            ('1440p', 'VP9', True, False): (True, '308'),              # Exact match, 60fps
            ('1440p', 'VP9', True, True): (True, '336'),               # Exact match, 60fps+hdr
            ('2160p', 'AVC1', False, False): (False, '136'),           # Fallback match, dropped to 720p (no 2160p AVC1)
            ('2160p', 'AVC1', False, True): (False, '299'),            # Fallback match, no hdr, extra 60fps, dropped to 1080p (no 2160p AVC1)
            ('2160p', 'AVC1', True, False): (False, '299'),            # Fallback match, no hdr, 60fps, dropped to 1080p (no 2160p AVC1)
            ('2160p', 'AVC1', True, True): (False, '299'),             # Fallback match, no hdr, 60fps, dropped to 1080p (no 2160p AVC1)
            ('2160p', 'VP9', False, False): (False, '315'),            # Fallback match, extra 60fps
            ('2160p', 'VP9', False, True): (True, '337'),              # Exact match, hdr, extra 60fps
            ('2160p', 'VP9', True, False): (True, '315'),              # Exact match, 60fps
            ('2160p', 'VP9', True, True): (True, '337'),               # Exact match, 60fps+hdr
            ('4320p', 'AVC1', False, False): (False, '136'),           # Fallback match, dropped to 720p (no 4320p AVC1)
            ('4320p', 'AVC1', False, True): (False, '299'),            # Fallback match, no hdr, extra 60fps, dropped to 1080p (no 4320p AVC1)
            ('4320p', 'AVC1', True, False): (False, '299'),            # Fallback match, no hdr, 60fps, dropped to 1080p (no 4320p AVC1)
            ('4320p', 'AVC1', True, True): (False, '299'),             # Fallback match, no hdr, 60fps, dropped to 1080p (no 4320p AVC1)
            ('4320p', 'VP9', False, False): (False, '272'),            # Fallback match, extra 60fps (no other 8k streams)
            ('4320p', 'VP9', False, True): (False, '272'),             # Fallback match, no hdr, 60fps (no other 8k streams)
            ('4320p', 'VP9', True, False): (True, '272'),              # Exact match, 60fps
            ('4320p', 'VP9', True, True): (False, '272'),              # Fallback match, no hdr, 60fps (no other 8k streams)
        }
        for params, expected in expected_matches.items():
            resolution, vcodec, prefer_60fps, prefer_hdr = params
            expeceted_match_type, expected_format_code = expected
            self.source.source_resolution = resolution
            self.source.source_vcodec = vcodec
            self.source.prefer_60fps = prefer_60fps
            self.source.prefer_hdr = prefer_hdr
            match_type, format_code = self.media.get_best_video_format()
            self.assertEqual(format_code, expected_format_code)
            self.assertEqual(match_type, expeceted_match_type)
        # test AV1 codec
        self.media.metadata = all_test_metadata['20230629']
        self.media.save()
        expected_matches = {
            # (format, vcodec, prefer_60fps, prefer_hdr): (match_type, code),
            ('360p', 'AV1', False, False): (True, '396'),              # Exact match
            ('360p', 'AV1', False, True): (False, '396'),              # Fallback match, no hdr
            ('360p', 'AV1', True, False): (False, '396'),              # Fallback match, no 60fps
            ('360p', 'AV1', True, True): (False, '396'),               # Fallback match, no 60fps+hdr
            ('480p', 'AV1', False, False): (True, '397'),              # Exact match
            ('480p', 'AV1', False, True): (False, '397'),              # Fallback match, no hdr
            ('480p', 'AV1', True, False): (False, '397'),              # Fallback match, no 60fps
            ('480p', 'AV1', True, True): (False, '397'),               # Fallback match, no 60fps+hdr
            ('720p', 'AV1', False, False): (True, '398'),              # Exact match
            ('720p', 'AV1', False, True): (False, '398'),              # Fallback match, no hdr
            ('720p', 'AV1', True, False): (False, '398'),              # Fallback match, no 60fps
            ('720p', 'AV1', True, True): (False, '398'),               # Fallback match, no 60fps+hdr
            ('1080p', 'AV1', False, False): (True, '399'),             # Exact match
            ('1080p', 'AV1', False, True): (False, '399'),             # Fallback match, no hdr
            ('1080p', 'AV1', True, False): (False, '399'),             # Fallback match, no 60fps
            ('1080p', 'AV1', True, True): (False, '399'),              # Fallback match, no 60fps+hdr
            ('1440p', 'AV1', False, False): (False, '399'),            # Fallback match, dropped to 1080p (no 1440p AV1)
            ('1440p', 'AV1', False, True): (False, '399'),             # Fallback match, no hdr, dropped to 1080p (no 1440p AV1)
            ('1440p', 'AV1', True, False): (False, '399'),             # Fallback match, no 60fps, dropped to 1080p (no 1440p AV1)
            ('1440p', 'AV1', True, True): (False, '399'),              # Fallback match, no 60fps+hdr, dropped to 1080p (no 1440p AV1)
            ('2160p', 'AV1', False, False): (False, '399'),            # Fallback match, dropped to 1080p (no 2160p AV1)
            ('2160p', 'AV1', False, True): (False, '399'),             # Fallback match, no hdr, dropped to 1080p (no 2160p AV1)
            ('2160p', 'AV1', True, False): (False, '399'),             # Fallback match, no 60fps, dropped to 1080p (no 2160p AV1)
            ('2160p', 'AV1', True, True): (False, '399'),              # Fallback match, no 60fps+hdr, dropped to 1080p (no 2160p AV1)
            ('4320p', 'AV1', False, False): (False, '399'),            # Fallback match, dropped to 1080p (no 4320p AV1, no other 8k streams)
            ('4320p', 'AV1', False, True): (False, '399'),             # Fallback match, no hdr, dropped to 1080p (no 4320p AV1, no other 8k streams)
            ('4320p', 'AV1', True, False): (False, '399'),             # Fallback match, no 60fps, dropped to 1080p (no 4320p AV1, no other 8k streams)
            ('4320p', 'AV1', True, True): (False, '399'),              # Fallback match, no 60fps+hdr, dropped to 1080p (no 4320p AV1, no other 8k streams)
        }
        for params, expected in expected_matches.items():
            resolution, vcodec, prefer_60fps, prefer_hdr = params
            expeceted_match_type, expected_format_code = expected
            self.source.source_resolution = resolution
            self.source.source_vcodec = vcodec
            self.source.prefer_60fps = prefer_60fps
            self.source.prefer_hdr = prefer_hdr
            match_type, format_code = self.media.get_best_video_format()
            self.assertEqual(format_code, expected_format_code)
            self.assertEqual(match_type, expeceted_match_type)

    def test_video_next_best_format_matching(self):
        self.source.fallback = Val(Fallback.NEXT_BEST_RESOLUTION)
        # Test no 60fps, no HDR metadata
        self.media.metadata = all_test_metadata['boring']
        self.media.save()
        expected_matches = {
            # (format, vcodec, prefer_60fps, prefer_hdr): (match_type, code),
            ('360p', 'AVC1', False, True): (False, '134'),             # Fallback match, no hdr
            ('360p', 'AVC1', True, False): (False, '134'),             # Fallback match, no 60fps
            ('360p', 'AVC1', True, True): (False, '134'),              # Fallback match, no 60fps+hdr
            ('360p', 'VP9', False, False): (True, '243'),              # Exact match
            ('360p', 'VP9', False, True): (False, '243'),              # Fallback match, no hdr
            ('360p', 'VP9', True, False): (False, '243'),              # Fallback match, no 60fps
            ('360p', 'VP9', True, True): (False, '243'),               # Fallback match, no 60fps+hdr
            ('480p', 'AVC1', False, False): (True, '135'),             # Exact match
            ('480p', 'AVC1', False, True): (False, '135'),             # Fallback match, no hdr
            ('480p', 'AVC1', True, False): (False, '135'),             # Fallback match, no 60fps
            ('480p', 'AVC1', True, True): (False, '135'),              # Fallback match, no 60fps+hdr
            ('480p', 'VP9', False, False): (True, '244'),              # Exact match
            ('480p', 'VP9', False, True): (False, '244'),              # Fallback match, no hdr
            ('480p', 'VP9', True, False): (False, '244'),              # Fallback match, no 60fps
            ('480p', 'VP9', True, True): (False, '244'),               # Fallback match, no 60fps+hdr
            ('720p', 'AVC1', False, False): (True, '136'),             # Exact match
            ('720p', 'AVC1', False, True): (False, '136'),             # Fallback match, no hdr
            ('720p', 'AVC1', True, False): (False, '136'),             # Fallback match, no 60fps
            ('720p', 'AVC1', True, True): (False, '136'),              # Fallback match, no 60fps+hdr
            ('720p', 'VP9', False, False): (True, '247'),              # Exact match
            ('720p', 'VP9', False, True): (False, '247'),              # Fallback match, no hdr
            ('720p', 'VP9', True, False): (False, '247'),              # Fallback match, no 60fps
            ('720p', 'VP9', True, True): (False, '247'),               # Fallback match, no 60fps+hdr
            ('1080p', 'AVC1', False, False): (True, '137'),            # Exact match
            ('1080p', 'AVC1', False, True): (False, '137'),            # Fallback match, no hdr
            ('1080p', 'AVC1', True, False): (False, '137'),            # Fallback match, no 60fps
            ('1080p', 'AVC1', True, True): (False, '137'),             # Fallback match, no 60fps+hdr
            ('1080p', 'VP9', False, False): (True, '248'),             # Exact match
            ('1080p', 'VP9', False, True): (False, '248'),             # Fallback match, no hdr
            ('1080p', 'VP9', True, False): (False, '248'),             # Fallback match, no 60fps
            ('1080p', 'VP9', True, True): (False, '248'),              # Fallback match, no 60fps+hdr
            # No test formats in 'boring' metadata > 1080p
        }
        for params, expected in expected_matches.items():
            resolution, vcodec, prefer_60fps, prefer_hdr = params
            expeceted_match_type, expected_format_code = expected
            self.source.source_resolution = resolution
            self.source.source_vcodec = vcodec
            self.source.prefer_60fps = prefer_60fps
            self.source.prefer_hdr = prefer_hdr
            match_type, format_code = self.media.get_best_video_format()
            self.assertEqual(format_code, expected_format_code)
            self.assertEqual(match_type, expeceted_match_type)
        # Test 60fps metadata
        self.media.metadata = all_test_metadata['60fps']
        self.media.save()
        expected_matches = {
            # (format, vcodec, prefer_60fps, prefer_hdr): (match_type, code),
            ('360p', 'AVC1', False, True): (False, '134'),             # Fallback match, no hdr
            ('360p', 'AVC1', True, False): (False, '134'),             # Fallback match, no 60fps
            ('360p', 'AVC1', True, True): (False, '134'),              # Fallback match, no 60fps+hdr
            ('360p', 'VP9', False, False): (True, '243'),              # Exact match
            ('360p', 'VP9', False, True): (False, '243'),              # Fallback match, no hdr
            ('360p', 'VP9', True, False): (False, '243'),              # Fallback match, no 60fps
            ('360p', 'VP9', True, True): (False, '243'),               # Fallback match, no 60fps+hdr
            ('480p', 'AVC1', False, False): (True, '135'),             # Exact match
            ('480p', 'AVC1', False, True): (False, '135'),             # Fallback match, no hdr
            ('480p', 'AVC1', True, False): (False, '135'),             # Fallback match, no 60fps
            ('480p', 'AVC1', True, True): (False, '135'),              # Fallback match, no 60fps+hdr
            ('480p', 'VP9', False, False): (True, '244'),              # Exact match
            ('480p', 'VP9', False, True): (False, '244'),              # Fallback match, no hdr
            ('480p', 'VP9', True, False): (False, '244'),              # Fallback match, no 60fps
            ('480p', 'VP9', True, True): (False, '244'),               # Fallback match, no 60fps+hdr
            ('720p', 'AVC1', False, False): (True, '136'),             # Exact match
            ('720p', 'AVC1', False, True): (False, '136'),             # Fallback match, no hdr
            ('720p', 'AVC1', True, False): (True, '298'),              # Exact match, 60fps
            ('720p', 'AVC1', True, True): (False, '298'),              # Fallback, 60fps, no hdr
            ('720p', 'VP9', False, False): (True, '247'),              # Exact match
            ('720p', 'VP9', False, True): (False, '247'),              # Fallback match, no hdr
            ('720p', 'VP9', True, False): (True, '302'),               # Exact match, 60fps
            ('720p', 'VP9', True, True): (False, '302'),               # Fallback, 60fps, no hdr
            # No test formats in '60fps' metadata > 720p
        }
        for params, expected in expected_matches.items():
            resolution, vcodec, prefer_60fps, prefer_hdr = params
            expeceted_match_type, expected_format_code = expected
            self.source.source_resolution = resolution
            self.source.source_vcodec = vcodec
            self.source.prefer_60fps = prefer_60fps
            self.source.prefer_hdr = prefer_hdr
            match_type, format_code = self.media.get_best_video_format()
            self.assertEqual(format_code, expected_format_code)
            self.assertEqual(match_type, expeceted_match_type)
        # Test hdr metadata
        self.media.metadata = all_test_metadata['hdr']
        self.media.save()
        expected_matches = {
            # (format, vcodec, prefer_60fps, prefer_hdr): (match_type, code),
            ('360p', 'AVC1', False, True): (False, '332'),             # Fallback match, hdr, switched to VP9
            ('360p', 'AVC1', True, False): (False, '134'),             # Fallback match, no 60fps
            ('360p', 'AVC1', True, True): (False, '332'),              # Fallback match, 60fps+hdr, switched to VP9
            ('360p', 'VP9', False, False): (True, '243'),              # Exact match
            ('360p', 'VP9', False, True): (True, '332'),               # Exact match, hdr
            ('360p', 'VP9', True, False): (False, '243'),              # Fallback match, no 60fps
            ('360p', 'VP9', True, True): (False, '332'),               # Fallback match, hdr, no 60fps
            ('480p', 'AVC1', False, False): (True, '135'),             # Exact match
            ('480p', 'AVC1', False, True): (False, '333'),             # Fallback match, hdr, switched to VP9
            ('480p', 'AVC1', True, False): (False, '135'),             # Fallback match, no 60fps
            ('480p', 'AVC1', True, True): (False, '333'),              # Fallback match, hdr, switched to VP9
            ('480p', 'VP9', False, False): (True, '244'),              # Exact match
            ('480p', 'VP9', False, True): (True, '333'),               # Exact match, hdr
            ('480p', 'VP9', True, False): (False, '244'),              # Fallback match, no 60fps
            ('480p', 'VP9', True, True): (False, '333'),               # Fallback match, hdr, no 60fps
            ('720p', 'AVC1', False, False): (True, '136'),             # Exact match
            ('720p', 'AVC1', False, True): (False, '334'),             # Fallback match, hdr, switched to VP9
            ('720p', 'AVC1', True, False): (False, '136'),             # Fallback match, no 60fps
            ('720p', 'AVC1', True, True): (False, '334'),              # Fallback match, hdr, switched to VP9
            ('720p', 'VP9', False, False): (True, '247'),              # Exact match
            ('720p', 'VP9', False, True): (True, '334'),               # Exact match, hdr
            ('720p', 'VP9', True, False): (False, '247'),              # Fallback match, no 60fps
            ('720p', 'VP9', True, True): (False, '334'),               # Fallback match, no 60fps
            ('1440p', 'AVC1', False, False): (False, '271'),           # Fallback match, switched to VP9
            ('1440p', 'AVC1', False, True): (False, '336'),            # Fallback match, hdr, switched to VP9
            ('1440p', 'AVC1', True, False): (False, '336'),            # Fallback match, hdr, switched to VP9, no 60fps
            ('1440p', 'AVC1', True, True): (False, '336'),             # Fallback match, hdr, switched to VP9, no 60fps
            ('1440p', 'VP9', False, False): (True, '271'),             # Exact match
            ('1440p', 'VP9', False, True): (True, '336'),              # Exact match, hdr
            ('1440p', 'VP9', True, False): (False, '271'),             # Fallback match, no 60fps
            ('1440p', 'VP9', True, True): (False, '336'),              # Fallback match, no 60fps
            ('2160p', 'AVC1', False, False): (False, '313'),           # Fallback match, switched to VP9
            ('2160p', 'AVC1', False, True): (False, '337'),            # Fallback match, hdr, switched to VP9
            ('2160p', 'AVC1', True, False): (False, '337'),            # Fallback match, hdr, switched to VP9, no 60fps
            ('2160p', 'AVC1', True, True): (False, '337'),             # Fallback match, hdr, switched to VP9, no 60fps
            ('2160p', 'VP9', False, False): (True, '313'),             # Exact match
            ('2160p', 'VP9', False, True): (True, '337'),              # Exact match, hdr
            ('2160p', 'VP9', True, False): (False, '313'),             # Fallback match, no 60fps
            ('2160p', 'VP9', True, True): (False, '337'),              # Fallback match, no 60fps
            # No test formats in 'hdr' metadata > 4k
        }
        for params, expected in expected_matches.items():
            resolution, vcodec, prefer_60fps, prefer_hdr = params
            expeceted_match_type, expected_format_code = expected
            self.source.source_resolution = resolution
            self.source.source_vcodec = vcodec
            self.source.prefer_60fps = prefer_60fps
            self.source.prefer_hdr = prefer_hdr
            match_type, format_code = self.media.get_best_video_format()
            self.assertEqual(format_code, expected_format_code)
            self.assertEqual(match_type, expeceted_match_type)
        # Test 60fps+hdr metadata
        self.media.metadata = all_test_metadata['60fps+hdr']
        self.media.save()
        expected_matches = {
            # (format, vcodec, prefer_60fps, prefer_hdr): (match_type, code),
            ('360p', 'AVC1', False, True): (False, '134'),             # Fallback match, no hdr
            ('360p', 'AVC1', True, False): (False, '134'),             # Fallback match, no 60fps
            ('360p', 'AVC1', True, True): (False, '332'),              # Fallback match, 60fps+hdr, switched to VP9
            ('360p', 'VP9', False, False): (True, '243'),              # Exact match
            ('360p', 'VP9', False, True): (True, '332'),               # Exact match, hdr
            ('360p', 'VP9', True, False): (False, '332'),              # Fallback match, 60fps, extra hdr
            ('360p', 'VP9', True, True): (True, '332'),                # Exact match, 60fps+hdr
            ('480p', 'AVC1', False, False): (True, '135'),             # Exact match
            ('480p', 'AVC1', False, True): (False, '135'),             # Fallback match, no hdr
            ('480p', 'AVC1', True, False): (False, '135'),             # Fallback match, no 60fps
            ('480p', 'AVC1', True, True): (False, '333'),              # Fallback match, 60fps+hdr, switched to VP9
            ('480p', 'VP9', False, False): (True, '244'),              # Exact match
            ('480p', 'VP9', False, True): (True, '333'),               # Exact match, hdr
            ('480p', 'VP9', True, False): (False, '333'),              # Fallback match, 60fps, extra hdr
            ('480p', 'VP9', True, True): (True, '333'),                # Exact match, 60fps+hdr
            ('720p', 'AVC1', False, False): (True, '136'),             # Exact match
            ('720p', 'AVC1', False, True): (False, '136'),             # Fallback match, no hdr
            ('720p', 'AVC1', True, False): (True, '298'),              # Exact match, 60fps
            ('720p', 'AVC1', True, True): (False, '334'),              # Fallback match, 60fps+hdr, switched to VP9
            ('720p', 'VP9', False, False): (True, '247'),              # Exact match
            ('720p', 'VP9', False, True): (True, '334'),               # Exact match, hdr
            ('720p', 'VP9', True, False): (True, '302'),               # Exact match, 60fps
            ('720p', 'VP9', True, True): (True, '334'),                # Exact match, 60fps+hdr
            ('1440p', 'AVC1', False, False): (False, '308'),           # Fallback match, 60fps, switched to VP9 (no 1440p AVC1)
            ('1440p', 'AVC1', False, True): (False, '336'),            # Fallback match, 60fps+hdr, switched to VP9 (no 1440p AVC1)
            ('1440p', 'AVC1', True, False): (False, '308'),            # Fallback match, 60fps, switched to VP9 (no 1440p AVC1)
            ('1440p', 'AVC1', True, True): (False, '336'),             # Fallback match, 60fps+hdr, switched to VP9 (no 1440p AVC1)
            ('1440p', 'VP9', False, False): (False, '308'),            # Fallback, 60fps
            ('1440p', 'VP9', False, True): (True, '336'),              # Exact match, hdr
            ('1440p', 'VP9', True, False): (True, '308'),              # Exact match, 60fps
            ('1440p', 'VP9', True, True): (True, '336'),               # Exact match, 60fps+hdr
            ('2160p', 'AVC1', False, False): (False, '315'),           # Fallback, 60fps, switched to VP9 (no 2160p AVC1)
            ('2160p', 'AVC1', False, True): (False, '337'),            # Fallback match, 60fps+hdr, switched to VP9 (no 2160p AVC1)
            ('2160p', 'AVC1', True, False): (False, '315'),            # Fallback, switched to VP9 (no 2160p AVC1)
            ('2160p', 'AVC1', True, True): (False, '337'),             # Fallback match, 60fps+hdr, switched to VP9 (no 2160p AVC1)
            ('2160p', 'VP9', False, False): (False, '315'),            # Fallback, 60fps
            ('2160p', 'VP9', False, True): (True, '337'),              # Exact match, hdr
            ('2160p', 'VP9', True, False): (True, '315'),              # Exact match, 60fps
            ('2160p', 'VP9', True, True): (True, '337'),               # Exact match, 60fps+hdr
            ('4320p', 'AVC1', False, False): (False, '272'),           # Fallback, 60fps, switched to VP9 (no 4320p AVC1, no other 8k streams)
            ('4320p', 'AVC1', False, True): (False, '272'),            # Fallback, 60fps, switched to VP9 (no 4320p AVC1, no other 8k streams)
            ('4320p', 'AVC1', True, False): (False, '272'),            # Fallback, 60fps, switched to VP9 (no 4320p AVC1, no other 8k streams)
            ('4320p', 'AVC1', True, True): (False, '272'),             # Fallback, 60fps, switched to VP9 (no 4320p AVC1, no other 8k streams)
            ('4320p', 'VP9', False, False): (False, '272'),            # Fallback, 60fps (no other 8k streams)
            ('4320p', 'VP9', False, True): (False, '272'),             # Fallback, 60fps (no other 8k streams)
            ('4320p', 'VP9', True, False): (True, '272'),              # Exact match, 60fps
            ('4320p', 'VP9', True, True): (False, '272'),              # Fallback, 60fps (no other 8k streams)
        }
        for params, expected in expected_matches.items():
            resolution, vcodec, prefer_60fps, prefer_hdr = params
            expeceted_match_type, expected_format_code = expected
            self.source.source_resolution = resolution
            self.source.source_vcodec = vcodec
            self.source.prefer_60fps = prefer_60fps
            self.source.prefer_hdr = prefer_hdr
            match_type, format_code = self.media.get_best_video_format()
            self.assertEqual(format_code, expected_format_code)
            self.assertEqual(match_type, expeceted_match_type)

    def test_metadata_20230629(self):
        self.source.fallback = Val(Fallback.NEXT_BEST_RESOLUTION)
        self.media.metadata = all_test_metadata['20230629']
        self.media.save()
        expected_matches = {
            # (format, vcodec, prefer_60fps, prefer_hdr): (match_type, code),
            ('360p', 'AVC1', False, False): (True, '230'),             # Exact match
            ('360p', 'AVC1', False, True): (False, '230'),             # Fallback match, no hdr
            ('360p', 'AVC1', True, False): (False, '230'),             # Fallback match, no 60fps
            ('360p', 'AVC1', True, True): (False, '230'),              # Fallback match, no 60fps+hdr
            ('360p', 'VP9', False, False): (True, '605'),              # Exact match
            ('360p', 'VP9', False, True): (False, '605'),              # Fallback match, no hdr
            ('360p', 'VP9', True, False): (False, '605'),              # Fallback match, no 60fps
            ('360p', 'VP9', True, True): (False, '605'),               # Fallback match, no 60fps+hdr
            ('360p', 'AV1', False, False): (True, '396'),              # Exact match
            ('360p', 'AV1', False, True): (False, '396'),              # Fallback match, no hdr
            ('360p', 'AV1', True, False): (False, '396'),              # Fallback match, no 60fps
            ('360p', 'AV1', True, True): (False, '396'),               # Fallback match, no 60fps+hdr
            ('480p', 'AVC1', False, False): (True, '231'),             # Exact match
            ('480p', 'AVC1', False, True): (False, '231'),             # Fallback match, no hdr
            ('480p', 'AVC1', True, False): (False, '231'),             # Fallback match, no 60fps
            ('480p', 'AVC1', True, True): (False, '231'),              # Fallback match, no 60fps+hdr
            ('480p', 'VP9', False, False): (True, '606'),              # Exact match
            ('480p', 'VP9', False, True): (False, '606'),              # Fallback match, no hdr
            ('480p', 'VP9', True, False): (False, '606'),              # Fallback match, no 60fps
            ('480p', 'VP9', True, True): (False, '606'),               # Fallback match, no 60fps+hdr
            ('480p', 'AV1', False, False): (True, '397'),              # Exact match
            ('480p', 'AV1', False, True): (False, '397'),              # Fallback match, no hdr
            ('480p', 'AV1', True, False): (False, '397'),              # Fallback match, no 60fps
            ('480p', 'AV1', True, True): (False, '397'),               # Fallback match, no 60fps+hdr
            ('720p', 'AVC1', False, False): (True, '232'),             # Exact match
            ('720p', 'AVC1', False, True): (False, '232'),             # Fallback match, no hdr
            ('720p', 'AVC1', True, False): (False, '232'),             # Fallback match, no 60fps
            ('720p', 'AVC1', True, True): (False, '232'),              # Fallback match, no 60fps+hdr
            ('720p', 'VP9', False, False): (True, '609'),              # Exact match
            ('720p', 'VP9', False, True): (False, '609'),              # Fallback match, no hdr
            ('720p', 'VP9', True, False): (False, '609'),              # Fallback match, no 60fps
            ('720p', 'VP9', True, True): (False, '609'),               # Fallback match, no 60fps+hdr
            ('720p', 'AV1', False, False): (True, '398'),              # Exact match
            ('720p', 'AV1', False, True): (False, '398'),              # Fallback match, no hdr
            ('720p', 'AV1', True, False): (False, '398'),              # Fallback match, no 60fps
            ('720p', 'AV1', True, True): (False, '398'),               # Fallback match, no 60fps+hdr
            ('1440p', 'AVC1', False, False): (False, '270'),           # Fallback match, dropped to 1080p (no 1440p AVC1)
            ('1440p', 'AVC1', False, True): (False, '270'),            # Fallback match, no hdr, dropped to 1080p (no 1440p AVC1)
            ('1440p', 'AVC1', True, False): (False, '270'),            # Fallback match, no 60fps, dropped to 1080p (no 1440p AVC1)
            ('1440p', 'AVC1', True, True): (False, '270'),             # Fallback match, no 60fps+hdr, dropped to 1080p (no 1440p AVC1)
            ('1440p', 'VP9', False, False): (False, '614'),            # Fallback match, dropped to 1080p (no 1440p VP9)
            ('1440p', 'VP9', False, True): (False, '614'),             # Fallback match, no hdr, dropped to 1080p (no 1440p VP9)
            ('1440p', 'VP9', True, False): (False, '614'),             # Fallback match, no 60fps, dropped to 1080p (no 1440p VP9)
            ('1440p', 'VP9', True, True): (False, '614'),              # Fallback match, no 60fps+hdr, dropped to 1080p (no 1440p VP9)
            ('1440p', 'AV1', False, False): (False, '399'),            # Fallback match, dropped to 1080p (no 1440p AV1)
            ('1440p', 'AV1', False, True): (False, '399'),             # Fallback match, no hdr, dropped to 1080p (no 1440p AV1)
            ('1440p', 'AV1', True, False): (False, '399'),             # Fallback match, no 60fps, dropped to 1080p (no 1440p AV1)
            ('1440p', 'AV1', True, True): (False, '399'),              # Fallback match, no 60fps+hdr, dropped to 1080p (no 1440p AV1)
            ('2160p', 'AVC1', False, False): (False, '270'),           # Fallback match, dropped to 1080p (no 2160p AVC1)
            ('2160p', 'AVC1', False, True): (False, '270'),            # Fallback match, no hdr, dropped to 1080p (no 2160p AVC1)
            ('2160p', 'AVC1', True, False): (False, '270'),            # Fallback match, no 60fps, dropped to 1080p (no 2160p AVC1)
            ('2160p', 'AVC1', True, True): (False, '270'),             # Fallback match, no 60fps+hdr, dropped to 1080p (no 2160p AVC1)
            ('2160p', 'VP9', False, False): (False, '614'),            # Fallback match, dropped to 1080p (no 2160p VP9)
            ('2160p', 'VP9', False, True): (False, '614'),             # Fallback match, no hdr, dropped to 1080p (no 2160p VP9)
            ('2160p', 'VP9', True, False): (False, '614'),             # Fallback match, no 60fps, dropped to 1080p (no 2160p VP9)
            ('2160p', 'VP9', True, True): (False, '614'),              # Fallback match, no 60fps+hdr, dropped to 1080p (no 2160p VP9)
            ('2160p', 'AV1', False, False): (False, '399'),            # Fallback match, dropped to 1080p (no 2160p AV1)
            ('2160p', 'AV1', False, True): (False, '399'),             # Fallback match, no hdr, dropped to 1080p (no 2160p AV1)
            ('2160p', 'AV1', True, False): (False, '399'),             # Fallback match, no 60fps, dropped to 1080p (no 2160p AV1)
            ('2160p', 'AV1', True, True): (False, '399'),              # Fallback match, no 60fps+hdr, dropped to 1080p (no 2160p AV1)
            ('4320p', 'AVC1', False, False): (False, '270'),           # Fallback match, dropped to 1080p (no 4320p AVC1)
            ('4320p', 'AVC1', False, True): (False, '270'),            # Fallback match, no hdr, dropped to 1080p (no 4320p AVC1)
            ('4320p', 'AVC1', True, False): (False, '270'),            # Fallback match, no 60fps, dropped to 1080p (no 4320p AVC1)
            ('4320p', 'AVC1', True, True): (False, '270'),             # Fallback match, no 60fps+hdr, dropped to 1080p (no 4320p AVC1)
            ('4320p', 'VP9', False, False): (False, '614'),            # Fallback match, dropped to 1080p (no 4320p VP9)
            ('4320p', 'VP9', False, True): (False, '614'),             # Fallback match, no hdr, dropped to 1080p (no 4320p VP9)
            ('4320p', 'VP9', True, False): (False, '614'),             # Fallback match, no 60fps, dropped to 1080p (no 4320p VP9)
            ('4320p', 'VP9', True, True): (False, '614'),              # Fallback match, no 60fps+hdr, dropped to 1080p (no 4320p VP9)
            ('4320p', 'AV1', False, False): (False, '399'),            # Fallback match, dropped to 1080p (no 4320p AV1)
            ('4320p', 'AV1', False, True): (False, '399'),             # Fallback match, no hdr, dropped to 1080p (no 4320p AV1)
            ('4320p', 'AV1', True, False): (False, '399'),             # Fallback match, no 60fps, dropped to 1080p (no 4320p AV1)
            ('4320p', 'AV1', True, True): (False, '399'),              # Fallback match, no 60fps+hdr, dropped to 1080p (no 4320p AV1)
        }
        for params, expected in expected_matches.items():
            resolution, vcodec, prefer_60fps, prefer_hdr = params
            expeceted_match_type, expected_format_code = expected
            self.source.source_resolution = resolution
            self.source.source_vcodec = vcodec
            self.source.prefer_60fps = prefer_60fps
            self.source.prefer_hdr = prefer_hdr
            match_type, format_code = self.media.get_best_video_format()
            self.assertEqual(format_code, expected_format_code)
            self.assertEqual(match_type, expeceted_match_type)
            # The aim here is to execute the matching code to find error paths, specific testing isn't required
            self.media.get_best_audio_format()

    def test_is_regex_match(self):

        self.media.metadata = all_test_metadata['boring']
        self.media.save()
        expected_matches = {
            ('.*'): (True),
            ('no fancy stuff'): (True),
            ('No fancy stuff'): (False),
            ('(?i)No fancy stuff'): (True), #set case insensitive flag
            ('no'): (True),
            ('Foo'): (False),
            ('^(?!.*fancy).*$'): (False),
            ('^(?!.*funny).*$'): (True),
            ('(?=.*f.*)(?=.{0,2}|.{4,})'): (True),
            ('f{4,}'): (False),
            ('^[^A-Z]*$'): (True),
            ('^[^a-z]*$'): (False),
            ('^[^\\s]*$'): (False)
        }

        for params, expected in expected_matches.items():
            self.source.filter_text = params
            expected_match_result = expected
            self.assertEqual(
                self.source.is_regex_match(self.media.title),
                expected_match_result,
                msg=f'Media title "{self.media.title}" checked against regex "{self.source.filter_text}" failed '
                    f'expected {expected_match_result}')


