import logging
from unittest.mock import patch

from django.test import TestCase

from sync.models import Source
from sync.tasks import download_source_images


class SourceImageUrlsTestCase(TestCase):

    def setUp(self):
        # Disable general logging for test case
        logging.disable(logging.CRITICAL)

    def _source(self):
        return Source.objects.create(
            key='aaa',
            name='aaa',
            directory='/tmp/a',
        )

    def test_save_indexed_image_urls_captures_all_three(self):
        source = self._source()
        response = {
            'thumbnails': [
                {'id': 'avatar_uncropped', 'height': 100, 'url': 'https://example.com/avatar.jpg'},
                {'id': 'banner_uncropped', 'height': 200, 'url': 'https://example.com/banner.jpg'},
                {'id': 'uncropped', 'height': 720, 'url': 'https://example.com/big.jpg'},
                {'id': 'uncropped', 'height': 360, 'url': 'https://example.com/small.jpg'},
            ],
            'entries': [],
        }

        self.assertTrue(source.save_indexed_image_urls(response))
        source.refresh_from_db()
        self.assertEqual(source.avatar_image_url, 'https://example.com/avatar.jpg')
        self.assertEqual(source.banner_image_url, 'https://example.com/banner.jpg')
        self.assertEqual(source.thumbnail_image_url, 'https://example.com/big.jpg')

    def test_save_indexed_image_urls_missing_images_stay_none(self):
        source = self._source()

        self.assertTrue(source.save_indexed_image_urls({'thumbnails': []}) is False)
        source.refresh_from_db()
        self.assertIsNone(source.avatar_image_url)
        self.assertIsNone(source.banner_image_url)
        self.assertIsNone(source.thumbnail_image_url)

    def test_download_source_images_uses_stored_urls_without_extraction(self):
        source = self._source()
        source.avatar_image_url = 'https://example.com/avatar.jpg'
        source.banner_image_url = None
        source.thumbnail_image_url = 'https://example.com/thumb.jpg'
        source.save()

        class FakeImage:
            def save(self, *args, **kwargs):
                pass

        with patch('sync.tasks.get_remote_image', return_value=FakeImage()) as get_img, \
             patch('sync.youtube.get_yt_opts'), \
             patch('sync.models.source.get_youtube_image_info') as extract:
            download_source_images.call_local(str(source.pk))

        # Two URLs stored -> two image downloads...
        self.assertEqual(get_img.call_count, 2)
        # ...and zero separate extractions for the channel page.
        extract.assert_not_called()
