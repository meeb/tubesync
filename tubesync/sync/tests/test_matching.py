from unittest import TestCase
from sync.models import Source, Media
from sync.matching_copy import get_best_video_format
from sync.choices import (
    Val, Fallback, SourceResolution,
    YouTube_AudioCodec, YouTube_VideoCodec,
    YouTube_SourceType,
)
from .fixtures import all_test_metadata

metadata = all_test_metadata['issue1639']

class MatchingFallbackTestCase(TestCase):
    def setUp(self):
        self.source = Source(
            source_type=Val(YouTube_SourceType.CHANNEL),
            source_resolution=Val(SourceResolution.VIDEO_4320P),
            source_vcodec=Val(YouTube_VideoCodec.VP9),
            source_acodec=Val(YouTube_AudioCodec.OPUS),
            prefer_60fps=True,
            prefer_hdr=False,
            fallback=Val(Fallback.NEXT_BEST_RESOLUTION)
        )
        self.media = Media(
            key='mediakey',
            source=self.source,
            metadata=metadata,
        )

    def test_next_best_resolution_ignores_codec(self):
        expected_format = self.media.formats[0]["format_id"]
        exact_match, actual_format = get_best_video_format(self.media)

        self.assertEqual(expected_format, actual_format)