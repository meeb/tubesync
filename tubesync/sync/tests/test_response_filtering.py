import logging
from django.test import TestCase, override_settings
from sync.models import Source, Media
from sync.utils import filter_response
from sync.choices import (
    Val, Fallback, SourceResolution,
    YouTube_AudioCodec, YouTube_VideoCodec,
    YouTube_SourceType,
)

from .fixtures import all_test_metadata

class ResponseFilteringTestCase(TestCase):

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

    @override_settings(SHRINK_OLD_MEDIA_METADATA=False, SHRINK_NEW_MEDIA_METADATA=False)
    def test_metadata_20230629(self):
        self.media.metadata = all_test_metadata['20230629']
        self.media.save()

        unfiltered = self.media.loaded_metadata
        filtered = filter_response(self.media.loaded_metadata, True)
        self.assertIn('formats', unfiltered.keys())
        self.assertIn('formats', filtered.keys())
        # filtered 'downloader_options'
        self.assertIn('downloader_options', unfiltered['formats'][10].keys())
        self.assertNotIn('downloader_options', filtered['formats'][10].keys())
        # filtered 'http_headers'
        self.assertIn('http_headers', unfiltered['formats'][0].keys())
        self.assertNotIn('http_headers', filtered['formats'][0].keys())
        # did not lose any formats
        self.assertEqual(48, len(unfiltered['formats']))
        self.assertEqual(48, len(filtered['formats']))
        self.assertEqual(len(unfiltered['formats']), len(filtered['formats']))
        # did not remove everything with url
        self.assertIn('original_url', unfiltered.keys())
        self.assertIn('original_url', filtered.keys())
        self.assertEqual(unfiltered['original_url'], filtered['original_url'])
        # did reduce the size of the metadata
        self.assertTrue(len(str(filtered)) < len(str(unfiltered)))

        url_keys = []
        for format in unfiltered['formats']:
            for key in format.keys():
                if 'url' in key:
                    url_keys.append((format['format_id'], key, format[key],))
        unfiltered_url_keys = url_keys
        self.assertEqual(63, len(unfiltered_url_keys), msg=str(unfiltered_url_keys))

        url_keys = []
        for format in filtered['formats']:
            for key in format.keys():
                if 'url' in key:
                    url_keys.append((format['format_id'], key, format[key],))
        filtered_url_keys = url_keys
        self.assertEqual(3, len(filtered_url_keys), msg=str(filtered_url_keys))

        url_keys = []
        for lang_code, captions in filtered['automatic_captions'].items():
            for caption in captions:
                for key in caption.keys():
                    if 'url' in key:
                        url_keys.append((lang_code, caption['ext'], caption[key],))
        self.assertEqual(0, len(url_keys), msg=str(url_keys))


