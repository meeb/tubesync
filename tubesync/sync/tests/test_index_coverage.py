"""The processing cap must not make upstream media look removed."""
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from sync.models import Source


VIDEOS = [{"id": key} for key in ("video-a", "video-b", "video-c")]
STREAMS = [{"id": key} for key in ("stream-a", "stream-b", "stream-c")]


class IndexCoverageTests(SimpleTestCase):
    def index(self, cap, mixed):
        source = Source(index_videos=True, index_streams=mixed)
        with override_settings(MAX_ENTRIES_PROCESSING=cap), patch.object(
            source, "get_index", side_effect=lambda kind: VIDEOS if kind == "videos" else STREAMS,
        ):
            processing, published = source.index_media()
        return [row["id"] for row in processing], published

    def test_processing_order_is_unchanged(self):
        # The order index_media() produced before it also returned the published keys.
        expected = {
            (0, False): ["video-c", "video-b", "video-a"],
            (0, True): ["video-c", "video-b", "video-a", "stream-c", "stream-b", "stream-a"],
            (2, False): ["video-b", "video-a"],
            (2, True): ["video-a", "stream-a"],
            (4, False): ["video-c", "video-b", "video-a"],
            (4, True): ["video-b", "video-a", "stream-b", "stream-a"],
        }
        for (cap, mixed), order in expected.items():
            with self.subTest(cap=cap, mixed=mixed):
                self.assertEqual(self.index(cap, mixed)[0], order)

    def test_published_keys_include_media_beyond_the_cap(self):
        for cap in (0, 2, 4):
            for mixed in (False, True):
                with self.subTest(cap=cap, mixed=mixed):
                    expected = {row["id"] for row in VIDEOS + (STREAMS if mixed else [])}
                    self.assertEqual(self.index(cap, mixed)[1], expected)
