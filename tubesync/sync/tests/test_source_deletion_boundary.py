import logging
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch

from django.test import TransactionTestCase, override_settings

from sync import tasks


class SourceDirectoryDeletionTestCase(TransactionTestCase):

    def setUp(self):
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        self.base = Path(temp_dir.name)
        self.root = self.base / 'downloads'

    def delete(self, directory):
        directory.mkdir(parents=True, exist_ok=True)
        (directory / '.to_be_removed').touch()
        with override_settings(DOWNLOAD_ROOT=self.root), patch.object(tasks, 'rmtree') as rmtree:
            tasks.delete_all_media_for_source.func(str(uuid.uuid4()), 'Removed', str(directory))
        return rmtree

    def test_directory_inside_download_root_is_removed(self):
        directory = self.root / 'video' / 'removed'
        self.delete(directory).assert_called_once_with(directory, True)

    def test_symbolic_link_inside_download_root_is_not_followed(self):
        target = self.base / 'other-disk' / 'removed'
        target.mkdir(parents=True)
        link = self.root / 'removed'
        self.root.mkdir()
        try:
            link.symlink_to(target, target_is_directory=True)
        except OSError as e:
            self.skipTest(f'symbolic links unavailable: {e}')
        self.delete(link).assert_called_once_with(link, True)

    def test_directory_outside_download_root_is_kept(self):
        for directory in (self.root, self.base / 'elsewhere', self.root / '..' / 'elsewhere'):
            with self.subTest(directory=directory):
                self.delete(directory).assert_not_called()
