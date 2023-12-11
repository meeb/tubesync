'''
    Tests do not test the scheduled tasks that perform live requests to index media or
    download content. They only check for compliance of web interface and check
    the matching code logic is working as expected.
'''


import logging
from datetime import datetime, timedelta
from urllib.parse import urlsplit
from xml.etree import ElementTree
from django.conf import settings
from django.test import TestCase, Client
from django.utils import timezone
from background_task.models import Task
from .models import Source, Media
from .tasks import cleanup_old_media


class FrontEndTestCase(TestCase):

    def setUp(self):
        # Disable general logging for test case
        logging.disable(logging.CRITICAL)

    def test_dashboard(self):
        c = Client()
        response = c.get('/')
        self.assertEqual(response.status_code, 200)

    def test_validate_source(self):
        test_source_types = {
            'youtube-channel': Source.SOURCE_TYPE_YOUTUBE_CHANNEL,
            'youtube-channel-id': Source.SOURCE_TYPE_YOUTUBE_CHANNEL_ID,
            'youtube-playlist': Source.SOURCE_TYPE_YOUTUBE_PLAYLIST,
        }
        test_sources = {
            'youtube-channel': {
                'valid': (
                    'https://m.youtube.com/testchannel',
                    'https://m.youtube.com/c/testchannel',
                    'https://m.youtube.com/c/testchannel/videos',
                    'https://www.youtube.com/testchannel',
                    'https://www.youtube.com/c/testchannel',
                    'https://www.youtube.com/c/testchannel/videos',
                ),
                'invalid_schema': (
                    'http://www.youtube.com/c/playlist',
                    'ftp://www.youtube.com/c/playlist',
                ),
                'invalid_domain': (
                    'https://www.test.com/c/testchannel',
                    'https://www.example.com/c/testchannel',
                    'https://n.youtube.com/c/testchannel',
                ),
                'invalid_path': (
                    'https://www.youtube.com/test/invalid',
                    'https://www.youtube.com/c/test/invalid',
                ),
                'invalid_is_playlist': (
                    'https://www.youtube.com/c/playlist',
                ),
                'invalid_channel_with_id': (
                    'https://www.youtube.com/channel/channelid',
                    'https://www.youtube.com/channel/channelid/videos',
                ),
            },
            'youtube-channel-id': {
                'valid': (
                    'https://m.youtube.com/channel/channelid',
                    'https://m.youtube.com/channel/channelid/videos',
                    'https://www.youtube.com/channel/channelid',
                    'https://www.youtube.com/channel/channelid/videos',
                ),
                'invalid_schema': (
                    'http://www.youtube.com/channel/channelid',
                    'ftp://www.youtube.com/channel/channelid',
                ),
                'invalid_domain': (
                    'https://www.test.com/channel/channelid',
                    'https://www.example.com/channel/channelid',
                    'https://n.youtube.com/channel/channelid',
                ),
                'invalid_path': (
                    'https://www.youtube.com/test/invalid',
                    'https://www.youtube.com/channel/test/invalid',
                ),
                'invalid_is_named_channel': (
                    'https://www.youtube.com/c/testname',
                ),
            },
            'youtube-playlist': {
                'valid': (
                    'https://m.youtube.com/playlist?list=testplaylist',
                    'https://m.youtube.com/watch?v=testvideo&list=testplaylist',
                    'https://www.youtube.com/playlist?list=testplaylist',
                    'https://www.youtube.com/watch?v=testvideo&list=testplaylist',
                ),
                'invalid_schema': (
                    'http://www.youtube.com/playlist?list=testplaylist',
                    'ftp://www.youtube.com/playlist?list=testplaylist',
                ),
                'invalid_domain': (
                    'https://www.test.com/playlist?list=testplaylist',
                    'https://www.example.com/playlist?list=testplaylist',
                    'https://n.youtube.com/playlist?list=testplaylist',
                ),
                'invalid_path': (
                    'https://www.youtube.com/notplaylist?list=testplaylist',
                    'https://www.youtube.com/c/notplaylist?list=testplaylist',
                ),
                'invalid_is_channel': (
                    'https://www.youtube.com/testchannel',
                    'https://www.youtube.com/c/testchannel',
                    'https://www.youtube.com/channel/testchannel',
                ),
            }
        }
        c = Client()
        for source_type in test_sources.keys():
            response = c.get(f'/source-validate/{source_type}')
            self.assertEqual(response.status_code, 200)
        response = c.get('/source-validate/invalid')
        self.assertEqual(response.status_code, 404)
        for (source_type, tests) in test_sources.items():
            for test, urls in tests.items():
                for url in urls:
                    source_type_char = test_source_types.get(source_type)
                    data = {'source_url': url, 'source_type': source_type_char}
                    response = c.post(f'/source-validate/{source_type}', data)
                    if test == 'valid':
                        # Valid source tests should bounce to /source-add
                        self.assertEqual(response.status_code, 302)
                        url_parts = urlsplit(response.url)
                        self.assertEqual(url_parts.path, '/source-add')
                    else:
                        # Invalid source tests should reload the page with an error
                        self.assertEqual(response.status_code, 200)
                        self.assertIn('<ul class="errorlist">',
                                      response.content.decode())

    def test_add_source_prepopulation(self):
        c = Client()
        response = c.get('/source-add?key=testkey&name=testname&directory=testdir')
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        checked_key, checked_name, checked_directory = False, False, False
        for line in html.split('\n'):
            if 'id="id_key"' in line:
                self.assertIn('value="testkey', line)
                checked_key = True
            if 'id="id_name"' in line:
                self.assertIn('value="testname', line)
                checked_name = True
            if 'id="id_directory"' in line:
                self.assertIn('value="testdir', line)
                checked_directory = True
        self.assertTrue(checked_key)
        self.assertTrue(checked_name)
        self.assertTrue(checked_directory)

    def test_source(self):
        # Sources overview page
        c = Client()
        response = c.get('/sources')
        self.assertEqual(response.status_code, 200)
        # Add as source form
        response = c.get('/source-add')
        self.assertEqual(response.status_code, 200)
        # Create a new source
        data = {
            'source_type': 'c',
            'key': 'testkey',
            'name': 'testname',
            'directory': 'testdirectory',
            'media_format': settings.MEDIA_FORMATSTR_DEFAULT,
            'download_cap': 0,
            'filter_text':'.*',
            'index_schedule': 3600,
            'delete_old_media': False,
            'days_to_keep': 14,
            'source_resolution': '1080p',
            'source_vcodec': 'VP9',
            'source_acodec': 'OPUS',
            'prefer_60fps': False,
            'prefer_hdr': False,
            'fallback': 'f',
            'sub_langs': 'en',
        }
        response = c.post('/source-add', data)
        self.assertEqual(response.status_code, 302)
        url_parts = urlsplit(response.url)
        url_path = str(url_parts.path).strip()
        if url_path.startswith('/'):
            url_path = url_path[1:]
        path_parts = url_path.split('/')
        self.assertEqual(path_parts[0], 'source')
        source_uuid = path_parts[1]
        source = Source.objects.get(pk=source_uuid)
        self.assertEqual(str(source.pk), source_uuid)
        # Check a task was created to index the media for the new source
        source_uuid = str(source.pk)
        task = Task.objects.get_task('sync.tasks.index_source_task',
                                     args=(source_uuid,))[0]
        self.assertEqual(task.queue, source_uuid)
        # Check the source is now on the source overview page
        response = c.get('/sources')
        self.assertEqual(response.status_code, 200)
        self.assertIn(source_uuid, response.content.decode())
        # Check the source detail page loads
        response = c.get(f'/source/{source_uuid}')
        self.assertEqual(response.status_code, 200)
        # Update the source key
        data = {
            'source_type': Source.SOURCE_TYPE_YOUTUBE_CHANNEL,
            'key': 'updatedkey',  # changed
            'name': 'testname',
            'directory': 'testdirectory',
            'media_format': settings.MEDIA_FORMATSTR_DEFAULT,
            'download_cap': 0,
            'filter_text':'.*',
            'index_schedule': Source.IndexSchedule.EVERY_HOUR,
            'delete_old_media': False,
            'days_to_keep': 14,
            'source_resolution': Source.SOURCE_RESOLUTION_1080P,
            'source_vcodec': Source.SOURCE_VCODEC_VP9,
            'source_acodec': Source.SOURCE_ACODEC_OPUS,
            'prefer_60fps': False,
            'prefer_hdr': False,
            'fallback': Source.FALLBACK_FAIL,
            'sub_langs': 'en',
        }
        response = c.post(f'/source-update/{source_uuid}', data)
        self.assertEqual(response.status_code, 302)
        url_parts = urlsplit(response.url)
        url_path = str(url_parts.path).strip()
        if url_path.startswith('/'):
            url_path = url_path[1:]
        path_parts = url_path.split('/')
        self.assertEqual(path_parts[0], 'source')
        source_uuid = path_parts[1]
        source = Source.objects.get(pk=source_uuid)
        self.assertEqual(source.key, 'updatedkey')
        # Update the source index schedule which should recreate the scheduled task
        data = {
            'source_type': Source.SOURCE_TYPE_YOUTUBE_CHANNEL,
            'key': 'updatedkey',
            'name': 'testname',
            'directory': 'testdirectory',
            'media_format': settings.MEDIA_FORMATSTR_DEFAULT,
            'download_cap': 0,
            'filter_text':'.*',
            'index_schedule': Source.IndexSchedule.EVERY_2_HOURS,  # changed
            'delete_old_media': False,
            'days_to_keep': 14,
            'source_resolution': Source.SOURCE_RESOLUTION_1080P,
            'source_vcodec': Source.SOURCE_VCODEC_VP9,
            'source_acodec': Source.SOURCE_ACODEC_OPUS,
            'prefer_60fps': False,
            'prefer_hdr': False,
            'fallback': Source.FALLBACK_FAIL,
            'sub_langs': 'en',
        }
        response = c.post(f'/source-update/{source_uuid}', data)
        self.assertEqual(response.status_code, 302)
        url_parts = urlsplit(response.url)
        url_path = str(url_parts.path).strip()
        if url_path.startswith('/'):
            url_path = url_path[1:]
        path_parts = url_path.split('/')
        self.assertEqual(path_parts[0], 'source')
        source_uuid = path_parts[1]
        source = Source.objects.get(pk=source_uuid)
        # Check a new task has been created by seeing if the pk has changed
        new_task = Task.objects.get_task('sync.tasks.index_source_task',
                                         args=(source_uuid,))[0]
        self.assertNotEqual(task.pk, new_task.pk)
        # Delete source confirmation page
        response = c.get(f'/source-delete/{source_uuid}')
        self.assertEqual(response.status_code, 200)
        # Delete source
        response = c.post(f'/source-delete/{source_uuid}')
        self.assertEqual(response.status_code, 302)
        url_parts = urlsplit(response.url)
        self.assertEqual(url_parts.path, '/sources')
        try:
            Source.objects.get(pk=source_uuid)
            object_gone = False
        except Source.DoesNotExist:
            object_gone = True
        self.assertTrue(object_gone)
        # Check the source is now gone from the source overview page
        response = c.get('/sources')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(source_uuid, response.content.decode())
        # Check the source details page now 404s
        response = c.get(f'/source/{source_uuid}')
        self.assertEqual(response.status_code, 404)
        # Check the indexing media task was removed
        tasks = Task.objects.get_task('sync.tasks.index_source_task',
                                      args=(source_uuid,))
        self.assertFalse(tasks)

    def test_media(self):
        # Media overview page
        c = Client()
        response = c.get('/media')
        self.assertEqual(response.status_code, 200)
        # Add a test source
        test_source = Source.objects.create(
            source_type=Source.SOURCE_TYPE_YOUTUBE_CHANNEL,
            key='testkey',
            name='testname',
            directory='testdirectory',
            index_schedule=Source.IndexSchedule.EVERY_HOUR,
            delete_old_media=False,
            days_to_keep=14,
            source_resolution=Source.SOURCE_RESOLUTION_1080P,
            source_vcodec=Source.SOURCE_VCODEC_VP9,
            source_acodec=Source.SOURCE_ACODEC_OPUS,
            prefer_60fps=False,
            prefer_hdr=False,
            fallback=Source.FALLBACK_FAIL
        )
        # Add some media
        test_minimal_metadata = '''
            {
                "thumbnail":"https://example.com/thumb.jpg",
                "formats": [{
                    "format_id":"251",
                    "player_url":null,
                    "ext":"webm",
                    "format_note":"tiny",
                    "acodec":"opus",
                    "abr":160,
                    "asr":48000,
                    "filesize":6669827,
                    "fps":null,
                    "height":null,
                    "tbr":156.344,
                    "width":null,
                    "vcodec":"none",
                    "format":"251 - audio only (tiny)",
                    "protocol":"https"
                },
                {
                    "format_id":"248",
                    "player_url":null,
                    "ext":"webm",
                    "height":1080,
                    "format_note":"1080p",
                    "vcodec":"vp9",
                    "asr":null,
                    "filesize":63659748,
                    "fps":24,
                    "tbr":2747.461,
                    "width":1920,
                    "acodec":"none",
                    "format":"248 - 1920x1080 (1080p)",
                    "protocol":"https"
                }]
            } 
        '''
        past_date = timezone.make_aware(datetime(year=2000, month=1, day=1))
        test_media1 = Media.objects.create(
            key='mediakey1',
            source=test_source,
            published=past_date,
            metadata=test_minimal_metadata
        )
        test_media1_pk = str(test_media1.pk)
        test_media2 = Media.objects.create(
            key='mediakey2',
            source=test_source,
            published=past_date,
            metadata=test_minimal_metadata
        )
        test_media2_pk = str(test_media2.pk)
        test_media3 = Media.objects.create(
            key='mediakey3',
            source=test_source,
            published=past_date,
            metadata=test_minimal_metadata
        )
        test_media3_pk = str(test_media3.pk)
        # Check the tasks to fetch the media thumbnails have been scheduled
        found_thumbnail_task1 = False
        found_thumbnail_task2 = False
        found_thumbnail_task3 = False
        found_download_task1 = False
        found_download_task2 = False
        found_download_task3 = False
        q = {'queue': str(test_source.pk),
             'task_name': 'sync.tasks.download_media_thumbnail'}
        for task in Task.objects.filter(**q):
            if test_media1_pk in task.task_params:
                found_thumbnail_task1 = True
            if test_media2_pk in task.task_params:
                found_thumbnail_task2 = True
            if test_media3_pk in task.task_params:
                found_thumbnail_task3 = True
        q = {'queue': str(test_source.pk),
             'task_name': 'sync.tasks.download_media'}
        for task in Task.objects.filter(**q):
            if test_media1_pk in task.task_params:
                found_download_task1 = True
            if test_media2_pk in task.task_params:
                found_download_task2 = True
            if test_media3_pk in task.task_params:
                found_download_task3 = True
        self.assertTrue(found_thumbnail_task1)
        self.assertTrue(found_thumbnail_task2)
        self.assertTrue(found_thumbnail_task3)
        self.assertTrue(found_download_task1)
        self.assertTrue(found_download_task2)
        self.assertTrue(found_download_task3)
        # Check the media is listed on the media overview page
        response = c.get('/media')
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn(test_media1_pk, html)
        self.assertIn(test_media2_pk, html)
        self.assertIn(test_media3_pk, html)
        # Check the media detail pages load
        response = c.get(f'/media/{test_media1_pk}')
        self.assertEqual(response.status_code, 200)
        response = c.get(f'/media/{test_media2_pk}')
        self.assertEqual(response.status_code, 200)
        response = c.get(f'/media/{test_media3_pk}')
        self.assertEqual(response.status_code, 200)
        # Delete the media
        test_media1.delete()
        test_media2.delete()
        test_media3.delete()
        # Check the media detail pages now 404
        response = c.get(f'/media/{test_media1_pk}')
        self.assertEqual(response.status_code, 404)
        response = c.get(f'/media/{test_media2_pk}')
        self.assertEqual(response.status_code, 404)
        response = c.get(f'/media/{test_media3_pk}')
        self.assertEqual(response.status_code, 404)
        # Confirm any tasks have been deleted
        q = {'task_name': 'sync.tasks.download_media_thumbnail'}
        download_media_thumbnail_tasks = Task.objects.filter(**q)
        self.assertFalse(download_media_thumbnail_tasks)
        q = {'task_name': 'sync.tasks.download_media'}
        download_media_tasks = Task.objects.filter(**q)
        self.assertFalse(download_media_tasks)

    def test_tasks(self):
        # Tasks overview page
        c = Client()
        response = c.get('/tasks')
        self.assertEqual(response.status_code, 200)
        # Completed tasks overview page
        response = c.get('/tasks-completed')
        self.assertEqual(response.status_code, 200)

    def test_mediasevrers(self):
        # Media servers overview page
        c = Client()
        response = c.get('/mediaservers')
        self.assertEqual(response.status_code, 200)


metadata_filepath = settings.BASE_DIR / 'sync' / 'testdata' / 'metadata.json'
metadata = open(metadata_filepath, 'rt').read()
metadata_hdr_filepath = settings.BASE_DIR / 'sync' / 'testdata' / 'metadata_hdr.json'
metadata_hdr = open(metadata_hdr_filepath, 'rt').read()
metadata_60fps_filepath = settings.BASE_DIR / 'sync' / 'testdata' / 'metadata_60fps.json'
metadata_60fps = open(metadata_60fps_filepath, 'rt').read()
metadata_60fps_hdr_filepath = settings.BASE_DIR / 'sync' / 'testdata' / 'metadata_60fps_hdr.json'
metadata_60fps_hdr = open(metadata_60fps_hdr_filepath, 'rt').read()
metadata_20230629_filepath = settings.BASE_DIR / 'sync' / 'testdata' / 'metadata_2023-06-29.json'
metadata_20230629 = open(metadata_20230629_filepath, 'rt').read()
all_test_metadata = {
    'boring': metadata,
    'hdr': metadata_hdr,
    '60fps': metadata_60fps,
    '60fps+hdr': metadata_60fps_hdr,
    '20230629': metadata_20230629,
}


class FilepathTestCase(TestCase):

    def setUp(self):
        # Disable general logging for test case
        logging.disable(logging.CRITICAL)
        # Add a test source
        self.source = Source.objects.create(
            source_type=Source.SOURCE_TYPE_YOUTUBE_CHANNEL,
            key='testkey',
            name='testname',
            directory='testdirectory',
            media_format=settings.MEDIA_FORMATSTR_DEFAULT,
            index_schedule=3600,
            delete_old_media=False,
            days_to_keep=14,
            source_resolution=Source.SOURCE_RESOLUTION_1080P,
            source_vcodec=Source.SOURCE_VCODEC_VP9,
            source_acodec=Source.SOURCE_ACODEC_OPUS,
            prefer_60fps=False,
            prefer_hdr=False,
            fallback=Source.FALLBACK_FAIL
        )
        # Add some test media
        self.media = Media.objects.create(
            key='mediakey',
            source=self.source,
            metadata=metadata,
        )

    def test_source_media_format(self):
        # Check media format validation is working
        # Empty
        self.source.media_format = ''
        self.assertEqual(self.source.get_example_media_format(), '')
        # Invalid, bad key
        self.source.media_format = '{test}'
        self.assertEqual(self.source.get_example_media_format(), '')
        # Invalid, extra brackets
        self.source.media_format = '{key}}'
        self.assertEqual(self.source.get_example_media_format(), '')
        # Invalid, not a string
        self.source.media_format = 1
        self.assertEqual(self.source.get_example_media_format(), '')
        # Check all expected keys validate
        self.source.media_format = 'test-{yyyymmdd}'
        self.assertEqual(self.source.get_example_media_format(),
                         'test-' + timezone.now().strftime('%Y%m%d'))
        self.source.media_format = 'test-{yyyy_mm_dd}'
        self.assertEqual(self.source.get_example_media_format(),
                         'test-' + timezone.now().strftime('%Y-%m-%d'))
        self.source.media_format = 'test-{yyyy}'
        self.assertEqual(self.source.get_example_media_format(),
                         'test-' + timezone.now().strftime('%Y'))
        self.source.media_format = 'test-{mm}'
        self.assertEqual(self.source.get_example_media_format(),
                         'test-' + timezone.now().strftime('%m'))
        self.source.media_format = 'test-{dd}'
        self.assertEqual(self.source.get_example_media_format(),
                         'test-' + timezone.now().strftime('%d'))
        self.source.media_format = 'test-{source}'
        self.assertEqual(self.source.get_example_media_format(),
                         'test-' + self.source.slugname)
        self.source.media_format = 'test-{source_full}'
        self.assertEqual(self.source.get_example_media_format(),
                         'test-' + self.source.name)
        self.source.media_format = 'test-{title}'
        self.assertEqual(self.source.get_example_media_format(),
                         'test-some-media-title-name')
        self.source.media_format = 'test-{title_full}'
        self.assertEqual(self.source.get_example_media_format(),
                         'test-Some Media Title Name')
        self.source.media_format = 'test-{key}'
        self.assertEqual(self.source.get_example_media_format(),
                         'test-SoMeUnIqUiD')
        self.source.media_format = 'test-{format}'
        self.assertEqual(self.source.get_example_media_format(),
                         'test-1080p-vp9-opus')
        self.source.media_format = 'test-{playlist_title}'
        self.assertEqual(self.source.get_example_media_format(),
                         'test-Some Playlist Title')
        self.source.media_format = 'test-{ext}'
        self.assertEqual(self.source.get_example_media_format(),
                         'test-' + self.source.extension)
        self.source.media_format = 'test-{resolution}'
        self.assertEqual(self.source.get_example_media_format(),
                         'test-' + self.source.source_resolution)
        self.source.media_format = 'test-{height}'
        self.assertEqual(self.source.get_example_media_format(),
                         'test-720')
        self.source.media_format = 'test-{width}'
        self.assertEqual(self.source.get_example_media_format(),
                         'test-1280')
        self.source.media_format = 'test-{vcodec}'
        self.assertEqual(self.source.get_example_media_format(),
                         'test-' + self.source.source_vcodec.lower())
        self.source.media_format = 'test-{acodec}'
        self.assertEqual(self.source.get_example_media_format(),
                         'test-' + self.source.source_acodec.lower())
        self.source.media_format = 'test-{fps}'
        self.assertEqual(self.source.get_example_media_format(),
                         'test-24')
        self.source.media_format = 'test-{hdr}'
        self.assertEqual(self.source.get_example_media_format(),
                         'test-hdr')

    def test_media_filename(self):
        # Check child directories work
        self.source.media_format = '{yyyy}/{key}.{ext}'
        self.assertEqual(self.media.directory_path,
                         str(self.source.directory_path / '2017'))
        self.assertEqual(self.media.filename, '2017/mediakey.mkv')
        self.source.media_format = '{yyyy}/{yyyy_mm_dd}/{key}.{ext}'
        self.assertEqual(self.media.directory_path,
                         str(self.source.directory_path / '2017/2017-09-11'))
        self.assertEqual(self.media.filename, '2017/2017-09-11/mediakey.mkv')
        # Check media specific media format keys work
        test_media = Media.objects.create(
            key='test',
            source=self.source,
            metadata=metadata,
            downloaded=True,
            download_date=timezone.now(),
            downloaded_format='720p',
            downloaded_height=720,
            downloaded_width=1280,
            downloaded_audio_codec='opus',
            downloaded_video_codec='vp9',
            downloaded_container='mkv',
            downloaded_fps=30,
            downloaded_hdr=True,
            downloaded_filesize=12345
        )
        # Bypass media-file-exists on-save signal
        test_media.downloaded = True
        self.source.media_format = ('{title}_{key}_{resolution}-{height}x{width}-'
                                    '{acodec}-{vcodec}-{fps}fps-{hdr}.{ext}')
        self.assertEqual(test_media.filename,
                         ('no-fancy-stuff-title_test_720p-720x1280-opus'
                          '-vp9-30fps-hdr.mkv'))


class MediaTestCase(TestCase):

    def setUp(self):
        # Disable general logging for test case
        logging.disable(logging.CRITICAL)
        # Add a test source
        self.source = Source.objects.create(
            source_type=Source.SOURCE_TYPE_YOUTUBE_CHANNEL,
            key='testkey',
            name='testname',
            directory='testdirectory',
            media_format=settings.MEDIA_FORMATSTR_DEFAULT,
            index_schedule=3600,
            delete_old_media=False,
            days_to_keep=14,
            source_resolution=Source.SOURCE_RESOLUTION_1080P,
            source_vcodec=Source.SOURCE_VCODEC_VP9,
            source_acodec=Source.SOURCE_ACODEC_OPUS,
            prefer_60fps=False,
            prefer_hdr=False,
            fallback=Source.FALLBACK_FAIL
        )
        # Add some test media
        self.media = Media.objects.create(
            key='mediakey',
            source=self.source,
            metadata=metadata,
        )
        # Fix a created datetime for predictable testing
        self.media.created = datetime(year=2020, month=1, day=1, hour=1,
                                      minute=1, second=1)

    def test_nfo(self):
        expected_nfo = [
            "<?xml version='1.0' encoding='utf8'?>",
            '<episodedetails>',
            '  <title>no fancy stuff title</title>',
            '  <showtitle>testname</showtitle>',
            '  <season>2017</season>',
            '  <episode></episode>',
            '  <ratings>',
            '    <rating default="True" max="5" name="youtube">',
            '      <value>1.2345</value>',
            '      <votes>579</votes>',
            '    </rating>',
            '  </ratings>',
            '  <plot>no fancy stuff desc</plot>',
            '  <thumb />',  # media.thumbfile is empty without media existing
            '  <mpaa>50</mpaa>',
            '  <runtime>401</runtime>',
            '  <id>mediakey</id>',
            '  <uniqueid default="True" type="youtube">mediakey</uniqueid>',
            '  <studio>test uploader</studio>',
            '  <aired>2017-09-11</aired>',
            '  <dateadded>2020-01-01 01:01:01</dateadded>',
            '  <genre>test category 1</genre>',
            '  <genre>test category 2</genre>',
            '</episodedetails>',
        ]
        expected_tree = ElementTree.fromstring('\n'.join(expected_nfo))
        nfo_tree = ElementTree.fromstring(self.media.nfoxml)
        # Check each node with attribs in expected_tree is present in test_nfo
        for expected_node in expected_tree:
            # Ignore checking <genre>, only tag we may have multiple of
            if expected_node.tag == 'genre':
                continue
            # Find the same node in the NFO XML tree
            nfo_node = nfo_tree.find(expected_node.tag)
            self.assertEqual(expected_node.attrib, nfo_node.attrib)
            self.assertEqual(expected_node.tag, nfo_node.tag)
            self.assertEqual(expected_node.text, nfo_node.text)


class FormatMatchingTestCase(TestCase):

    def setUp(self):
        # Disable general logging for test case
        logging.disable(logging.CRITICAL)
        # Add a test source
        self.source = Source.objects.create(
            source_type=Source.SOURCE_TYPE_YOUTUBE_CHANNEL,
            key='testkey',
            name='testname',
            directory='testdirectory',
            index_schedule=3600,
            delete_old_media=False,
            days_to_keep=14,
            source_resolution=Source.SOURCE_RESOLUTION_1080P,
            source_vcodec=Source.SOURCE_VCODEC_VP9,
            source_acodec=Source.SOURCE_ACODEC_OPUS,
            prefer_60fps=False,
            prefer_hdr=False,
            fallback=Source.FALLBACK_FAIL
        )
        # Add some media
        self.media = Media.objects.create(
            key='mediakey',
            source=self.source,
            metadata='{}'
        )

    def test_combined_exact_format_matching(self):
        self.source.fallback = Source.FALLBACK_FAIL
        self.media.metadata = all_test_metadata['boring']
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
            expeceted_match_type, expected_format_code = expected
            self.source.source_resolution = resolution
            self.source.source_vcodec = vcodec
            self.source.source_acodec = acodec
            self.source.prefer_60fps = prefer_60fps
            self.source.prefer_hdr = prefer_hdr
            match_type, format_code = self.media.get_best_combined_format()
            self.assertEqual(format_code, expected_format_code)
            self.assertEqual(match_type, expeceted_match_type)

    def test_audio_exact_format_matching(self):
        self.source.fallback = Source.FALLBACK_FAIL
        self.media.metadata = all_test_metadata['boring']
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
        self.source.fallback = Source.FALLBACK_FAIL
        # Test no 60fps, no HDR metadata
        self.media.metadata = all_test_metadata['boring']
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

    def test_video_next_best_format_matching(self):
        self.source.fallback = Source.FALLBACK_NEXT_BEST
        # Test no 60fps, no HDR metadata
        self.media.metadata = all_test_metadata['boring']
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
        self.media.metadata = all_test_metadata['20230629']
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
            # The aim here is to execute the matching code to find error paths, specific testing isn't required
            self.media.get_best_video_format()
            self.media.get_best_audio_format()

    def test_is_regex_match(self):
        
        self.media.metadata = all_test_metadata['boring']
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
            self.assertEqual(self.source.is_regex_match(self.media.title), expected_match_result)

class TasksTestCase(TestCase):
    def setUp(self):
        # Disable general logging for test case
        logging.disable(logging.CRITICAL)

    def test_delete_old_media(self):
        src1 = Source.objects.create(key='aaa', name='aaa', directory='/tmp/a', delete_old_media=False, days_to_keep=14)
        src2 = Source.objects.create(key='bbb', name='bbb', directory='/tmp/b', delete_old_media=True, days_to_keep=14)

        now = timezone.now()

        m11 = Media.objects.create(source=src1, downloaded=True, key='a11', download_date=now - timedelta(days=5))
        m12 = Media.objects.create(source=src1, downloaded=True, key='a12', download_date=now - timedelta(days=25))
        m13 = Media.objects.create(source=src1, downloaded=False, key='a13')

        m21 = Media.objects.create(source=src2, downloaded=True, key='a21', download_date=now - timedelta(days=5))
        m22 = Media.objects.create(source=src2, downloaded=True, key='a22', download_date=now - timedelta(days=25))
        m23 = Media.objects.create(source=src2, downloaded=False, key='a23')

        self.assertEquals(src1.media_source.all().count(), 3)
        self.assertEquals(src2.media_source.all().count(), 3)

        cleanup_old_media()

        self.assertEquals(src1.media_source.all().count(), 3)
        self.assertEquals(src2.media_source.all().count(), 2)
        self.assertEquals(Media.objects.filter(pk=m22.pk).exists(), False)
