"""The processing cap must not make upstream media look removed."""
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from sync.models import Source


@override_settings(MAX_ENTRIES_PROCESSING=2, INDEXING_CLEANUP_UNAVAILABLE_POLICY='Published ')
class IndexCoverageTests(SimpleTestCase):
    def test_capped_queue_retains_complete_removal_keys(self):
        videos = [{"id": key} for key in ("video-a", "video-b", "video-c")]
        streams = [{"id": key} for key in ("stream-a", "stream-b", "stream-c")]
        for mixed in (False, True):
            with self.subTest(mixed=mixed):
                source = Source(index_videos=True, index_streams=mixed)
                with patch.object(source, "get_index", side_effect=lambda kind: videos if kind == "videos" else streams):
                    processing, upstream = source.index_media()
                self.assertEqual(len(processing), 2)
                expected = {row["id"] for row in videos + (streams if mixed else [])}
                self.assertEqual(upstream, expected)
                self.assertEqual((expected | {"genuinely-removed"}) - upstream, {"genuinely-removed"})
