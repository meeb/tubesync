"""Exercise deletion admission with fabricated paths and mocked database/queue writes."""
import ast
import contextlib
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock


class SourceDeletionBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.base = Path(self.directory.name)
        self.root = self.base / "downloads"
        self.root.mkdir()
        source = Path(__file__).resolve().parents[1] / "tasks.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        self.function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                             and node.name == "delete_all_media_for_source")
        self.function.decorator_list = []

    def task(self, present=True, remove=False):
        class MissingSource(Exception):
            pass
        source = SimpleNamespace(delete_removed_media=remove, delete=Mock(),
                                 uuid="synthetic-source", key="synthetic", name="Synthetic")
        objects = Mock()
        if present:
            objects.get.return_value = source
        else:
            objects.get.side_effect = MissingSource
        queryset = Mock()
        queryset.defer.return_value = queryset
        queryset.filter.return_value = queryset
        namespace = {"Source": SimpleNamespace(objects=objects, DoesNotExist=MissingSource),
                     "Media": SimpleNamespace(objects=SimpleNamespace(all=Mock(return_value=queryset))),
                     "settings": SimpleNamespace(DOWNLOAD_ROOT=self.root), "Path": Path,
                     "delete_media": Mock(), "qs_gen": lambda query: [],
                     "huey_lock_task": Mock(return_value=SimpleNamespace(acquired=False)),
                     "TaskQueue": SimpleNamespace(FS="synthetic-fs"), "Val": lambda value: value,
                     "update_model": Mock(),
                     "atomic": lambda **kwargs: contextlib.nullcontext(), "log": Mock(), "rmtree": Mock()}
        exec(compile(ast.Module(body=[self.function], type_ignores=[]), "tasks.py", "exec"), namespace)
        return namespace, source, queryset

    def test_invalid_inputs_are_refused_before_queue_or_database_access(self):
        outside = self.base / "outside"
        outside.mkdir()
        (outside / ".to_be_removed").touch()
        (self.root / ".to_be_removed").touch()
        valid = self.root / "valid"
        cases = [("", "Synthetic", str(valid)), ("id", "", str(valid)),
                 ("id", "Synthetic", ""), ("id", "Synthetic", None),
                 ("id", "Synthetic", str(self.root)), ("id", "Synthetic", str(outside)),
                 ("id", "Synthetic", str(self.base / "downloads-other")),
                 ("id", "Synthetic", str(self.root / ".." / "outside")),
                 ("id", "Synthetic", "relative-path")]
        for args in cases:
            with self.subTest(args=args):
                namespace, _, query = self.task(remove=True)
                with self.assertRaises(ValueError):
                    namespace["delete_all_media_for_source"](*args)
                namespace["Source"].objects.get.assert_not_called()
                namespace["Media"].objects.all.assert_not_called()
                namespace["delete_media"].map.assert_not_called()
                query.update.assert_not_called()
                query.delete.assert_not_called()
                namespace["rmtree"].assert_not_called()

    def test_valid_captured_directory_preserves_existing_and_missing_source_workflows(self):
        for present, remove, marker in [(True, False, False), (True, True, False),
                                        (False, False, True), (False, False, False)]:
            with self.subTest(present=present, remove=remove, marker=marker):
                path = self.root / f"source-{present}-{remove}-{marker}"
                path.mkdir()
                if marker:
                    (path / ".to_be_removed").touch()
                namespace, source, query = self.task(present, remove)
                namespace["delete_all_media_for_source"]("synthetic-id", "Synthetic", str(path))
                query.filter.assert_called_once_with(source=source if present else "synthetic-id")
                query.update.assert_called_once_with(manual_skip=True, skip=True)
                query.delete.assert_called_once()
                self.assertEqual(source.delete.call_count, int(present))
                if remove or marker:
                    namespace["rmtree"].assert_called_once_with(path, True)
                else:
                    namespace["rmtree"].assert_not_called()

    def test_already_missing_directory_still_allows_database_cleanup(self):
        namespace, _, query = self.task(present=False)
        namespace["delete_all_media_for_source"]("synthetic-id", "Synthetic", str(self.root / "missing"))
        query.delete.assert_called_once()
        namespace["rmtree"].assert_not_called()

    def test_symlink_escape_is_refused_before_side_effects(self):
        outside = self.base / "outside"
        outside.mkdir()
        link = self.root / "redirected"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"directory symlinks unavailable: {error}")
        namespace, _, _ = self.task(remove=True)
        with self.assertRaises(ValueError):
            namespace["delete_all_media_for_source"]("synthetic-id", "Synthetic", str(link))
        namespace["Media"].objects.all.assert_not_called()
        namespace["rmtree"].assert_not_called()


if __name__ == "__main__":
    unittest.main()
