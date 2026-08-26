import logging
from datetime import timedelta
from unittest.mock import call, mock_open, patch

from django.test import TestCase
from django.utils import timezone

from huey import CancelExecution

from sync.models import Media, Metadata, Source
from sync.tasks import download_source_images
from sync.youtube import merge_image_thumbnails


class SourceImagesTestCase(TestCase):

    def setUp(self):
        # Disable general logging for test case
        logging.disable(logging.CRITICAL)

    def _source(self):
        return Source.objects.create(
            key='source-key',
            name='aaa',
            directory='/tmp/a',
        )

    def _response(self, **values):
        response = {
            'extractor_key': 'YoutubeTab',
            'id': 'channel-id',
            'title': 'Channel title',
            'description': 'Channel description',
            'thumbnails': [
                {'id': 'avatar_uncropped', 'height': 100, 'url': 'https://example.com/avatar.jpg'},
                {'id': 'banner_uncropped', 'height': 200, 'url': 'https://example.com/banner.jpg'},
                {'id': 'uncropped', 'height': 720, 'url': 'https://example.com/big.jpg'},
                {'id': 'uncropped', 'height': 360, 'url': 'https://example.com/small.jpg'},
            ],
            'entries': [{'id': 'video-id'}],
        }
        response.update(values)
        return response

    def test_get_index_stores_source_metadata_without_entries(self):
        source = self._source()
        response = self._response()
        index_url = source.get_index_url('videos')

        with patch.dict(source.INDEXERS, {
            source.source_type: lambda *args, **kwargs: response,
        }):
            entries = source.get_index('videos')

        self.assertEqual(entries, [{'id': 'video-id'}])
        metadata = Metadata.objects.get(
            source=source,
            media=None,
            site='YoutubeTab',
            key=index_url,
        )
        self.assertNotIn('entries', response)
        self.assertNotIn('entries', metadata.value)
        self.assertEqual(metadata.value['id'], 'channel-id')
        self.assertEqual(metadata.value['thumbnails'], self._response()['thumbnails'])

    def test_merge_image_thumbnails_normalises_invalid_dimensions(self):
        previous = [{
            'id': 'uncropped',
            'width': None,
            'height': None,
            'url': 'https://example.com/old.jpg',
        }]
        current = [{
            'id': 'uncropped',
            'width': None,
            'height': {},
            'url': 'https://example.com/current.jpg',
        }]

        self.assertEqual(merge_image_thumbnails(previous, current), current)

    def test_get_index_preserves_valid_metadata_values(self):
        source = self._source()
        replacement_avatar = {
            'id': 'avatar_uncropped',
            'height': 100,
            'url': 'https://example.com/new-avatar.jpg',
        }
        responses = [
            self._response(),
            self._response(
                title='Updated channel title',
                description=None,
                thumbnails=[replacement_avatar],
                entries=[],
            ),
        ]

        with patch.dict(source.INDEXERS, {
            source.source_type: lambda *args, **kwargs: responses.pop(0),
        }):
            source.get_index('videos')
            source.get_index('videos')

        self.assertEqual(Metadata.objects.filter(source=source).count(), 1)
        metadata = Metadata.objects.get(source=source)
        self.assertEqual(metadata.key, source.get_index_url('videos'))
        self.assertEqual(metadata.value['title'], 'Updated channel title')
        self.assertEqual(metadata.value['description'], 'Channel description')
        self.assertEqual(source.get_image_urls(source.videos.all()), (
            'https://example.com/new-avatar.jpg',
            'https://example.com/banner.jpg',
            'https://example.com/big.jpg',
        ))

    def test_get_index_uses_stable_identity_for_incomplete_responses(self):
        source = self._source()
        incomplete_response = self._response(
            extractor_key=None,
            id=None,
            title='Updated channel title',
            entries=[],
        )
        responses = [self._response(), incomplete_response]

        with patch.dict(source.INDEXERS, {
            source.source_type: lambda *args, **kwargs: responses.pop(0),
        }):
            source.get_index('videos')
            source.get_index('videos')

        self.assertEqual(Metadata.objects.filter(source=source).count(), 1)
        metadata = Metadata.objects.get(source=source)
        self.assertEqual(metadata.key, source.get_index_url('videos'))
        self.assertEqual(metadata.site, 'YoutubeTab')
        self.assertEqual(metadata.value['extractor_key'], 'YoutubeTab')
        self.assertEqual(metadata.value['id'], 'channel-id')
        self.assertEqual(metadata.value['title'], 'Updated channel title')

    def test_get_index_updates_the_default_site_for_later_complete_responses(self):
        source = self._source()
        incomplete_response = self._response(
            extractor_key=None,
            id=None,
            entries=[],
        )
        responses = [incomplete_response, self._response(entries=[])]

        with patch.dict(source.INDEXERS, {
            source.source_type: lambda *args, **kwargs: responses.pop(0),
        }):
            source.get_index('videos')
            source.get_index('videos')

        self.assertEqual(Metadata.objects.filter(source=source).count(), 1)
        metadata = Metadata.objects.get(source=source)
        self.assertEqual(metadata.key, source.get_index_url('videos'))
        self.assertEqual(metadata.site, 'YoutubeTab')

    def test_get_image_urls_prefers_videos_and_uses_streams_for_missing_images(self):
        source = self._source()
        source.index_streams = True
        source.save(update_fields={'index_streams'})
        Metadata.objects.create(
            source=source,
            site='YoutubeTab',
            key=source.get_index_url('videos'),
            retrieved=timezone.now() - timedelta(days=1),
            value={
                'thumbnails': [
                    {
                        'id': 'avatar_uncropped',
                        'height': 100,
                        'url': 'https://example.com/videos-avatar.jpg',
                    },
                    {
                        'id': 'uncropped',
                        'height': 720,
                        'url': 'https://example.com/videos-thumbnail.jpg',
                    },
                ],
            },
        )
        Metadata.objects.create(
            source=source,
            site='YoutubeTab',
            key=source.get_index_url('streams'),
            retrieved=timezone.now(),
            value={
                'thumbnails': [
                    {
                        'id': 'avatar_uncropped',
                        'height': 100,
                        'url': 'https://example.com/streams-avatar.jpg',
                    },
                    {
                        'id': 'banner_uncropped',
                        'height': 200,
                        'url': 'https://example.com/streams-banner.jpg',
                    },
                    {
                        'id': 'uncropped',
                        'height': 1080,
                        'url': 'https://example.com/streams-thumbnail.jpg',
                    },
                ],
            },
        )

        self.assertEqual(
            source.get_image_urls(source.videos.filter(media__isnull=True)),
            (
                'https://example.com/videos-avatar.jpg',
                'https://example.com/streams-banner.jpg',
                'https://example.com/videos-thumbnail.jpg',
            ),
        )

    def test_download_source_images_uses_index_metadata_without_extraction(self):
        source = self._source()
        Metadata.objects.create(
            source=source,
            site='YoutubeTab',
            key=source.get_index_url('videos'),
            value=self._response(entries=[]),
        )
        Media.objects.create(source=source, key='video-id')
        Metadata.objects.create(
            source=source,
            site='Youtube',
            key='video-id',
            value={
                'thumbnails': [
                    {'id': 'video', 'height': 1080, 'url': 'https://example.com/video.jpg'},
                ],
            },
        )

        class FakeImage:
            def save(self, image_file, *args, **kwargs):
                image_file.write(b'image')

        with patch('sync.tasks.get_remote_image', return_value=FakeImage()) as get_img, \
             patch('sync.youtube.yt_dlp.YoutubeDL') as youtube_dl, \
             patch('builtins.open', mock_open()):
            download_source_images.call_local(str(source.pk))

        self.assertEqual(get_img.call_args_list, [
            call('https://example.com/big.jpg'),
            call('https://example.com/banner.jpg'),
            call('https://example.com/avatar.jpg'),
        ])
        youtube_dl.assert_not_called()

    def test_download_source_images_retries_until_index_data_is_available(self):
        source = self._source()

        with self.assertRaisesRegex(CancelExecution, 'data not yet available') as raised:
            download_source_images.call_local(str(source.pk))

        self.assertIsNone(raised.exception.retry)

    def test_download_source_images_retries_when_index_data_has_no_images(self):
        source = self._source()
        Metadata.objects.create(
            source=source,
            site='YoutubeTab',
            key=source.get_index_url('videos'),
            value=self._response(thumbnails=None, entries=[]),
        )

        with self.assertRaisesRegex(CancelExecution, 'data not yet available'):
            download_source_images.call_local(str(source.pk))
