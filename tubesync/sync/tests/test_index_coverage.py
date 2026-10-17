"""The processing cap must not make upstream media look removed."""
import ast
from collections import deque
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase


class IndexCoverageTests(TestCase):
    def test_capped_queue_retains_complete_removal_keys(self):
        # Exercise the method without importing installation settings or scheduling downloads.
        source = Path(__file__).resolve().parents[1] / "models" / "source.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        model = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Source")
        method = next(node for node in model.body if isinstance(node, ast.FunctionDef) and node.name == "index_media")
        namespace = {"queue": deque, "settings": SimpleNamespace(MAX_ENTRIES_PROCESSING=2)}
        exec(compile(ast.Module(body=[method], type_ignores=[]), str(source), "exec"), namespace)
        videos = [{"id": key} for key in ("video-a", "video-b", "video-c")]
        streams = [{"id": key} for key in ("stream-a", "stream-b", "stream-c")]
        for mixed in (False, True):
            with self.subTest(mixed=mixed):
                model = SimpleNamespace(index_videos=True, index_streams=mixed,
                                        is_playlist=False, key_field="id",
                                        get_index=lambda kind: videos if kind == "videos" else streams)
                processing, upstream = namespace["index_media"](model)
                self.assertEqual(len(processing), 2)
                expected = {row["id"] for row in videos + (streams if mixed else [])}
                self.assertEqual(upstream, expected)
                self.assertEqual((expected | {"genuinely-removed"}) - upstream, {"genuinely-removed"})
