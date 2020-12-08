'''
    Note these tests do not test the scheduled tasks that perform live requests to
    index media or download content. They only check for compliance of web
    interface and validation code.
'''


import logging
from urllib.parse import urlsplit
from django.test import TestCase, Client
from django.utils import timezone
from background_task.models import Task
from .models import Source, Media


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
            'youtube-playlist': Source.SOURCE_TYPE_YOUTUBE_PLAYLIST,
        }
        test_sources = {
            'youtube-channel': {
                'valid': (
                    'https://www.youtube.com/testchannel',
                    'https://www.youtube.com/c/testchannel',
                ),
                'invalid_schema': (
                    'http://www.youtube.com/c/playlist',
                    'ftp://www.youtube.com/c/playlist',
                ),
                'invalid_domain': (
                    'https://www.test.com/c/testchannel',
                    'https://www.example.com/c/testchannel',
                ),
                'invalid_path': (
                    'https://www.youtube.com/test/invalid',
                    'https://www.youtube.com/c/test/invalid',
                ),
                'invalid_is_playlist': (
                    'https://www.youtube.com/c/playlist',
                    'https://www.youtube.com/c/playlist',
                ),
            },
            'youtube-playlist': {
                'valid': (
                    'https://www.youtube.com/playlist?list=testplaylist'
                    'https://www.youtube.com/watch?v=testvideo&list=testplaylist'
                ),
                'invalid_schema': (
                    'http://www.youtube.com/playlist?list=testplaylist',
                    'ftp://www.youtube.com/playlist?list=testplaylist',
                ),
                'invalid_domain': (
                    'https://www.test.com/playlist?list=testplaylist',
                    'https://www.example.com/playlist?list=testplaylist',
                ),
                'invalid_path': (
                    'https://www.youtube.com/notplaylist?list=testplaylist',
                    'https://www.youtube.com/c/notplaylist?list=testplaylist',
                ),
                'invalid_is_channel': (
                    'https://www.youtube.com/testchannel',
                    'https://www.youtube.com/c/testchannel',
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
            for test, field in tests.items():
                source_type_char = test_source_types.get(source_type)
                data = {'source_url': field, 'source_type': source_type_char}
                response = c.post(f'/source-validate/{source_type}', data)
                if test == 'valid':
                    # Valid source tests should bounce to /source-add
                    self.assertEqual(response.status_code, 302)
                    url_parts = urlsplit(response.url)
                    self.assertEqual(url_parts.path, '/source-add')
                else:
                    # Invalid source tests should reload the page with an error message
                    self.assertEqual(response.status_code, 200)
                    self.assertIn('<ul class="errorlist">', response.content.decode())

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
            'index_schedule': 3600,
            'delete_old_media': False,
            'days_to_keep': 14,
            'source_resolution': '1080p',
            'source_vcodec': 'VP9',
            'source_acodec': 'OPUS',
            'prefer_60fps': False,
            'prefer_hdr': False,
            'fallback': 'f'
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
            'source_type': 'c',
            'key': 'updatedkey',  # changed
            'name': 'testname',
            'directory': 'testdirectory',
            'index_schedule': 3600,
            'delete_old_media': False,
            'days_to_keep': 14,
            'source_resolution': '1080p',
            'source_vcodec': 'VP9',
            'source_acodec': 'OPUS',
            'prefer_60fps': False,
            'prefer_hdr': False,
            'fallback': 'f'
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
            'source_type': 'c',
            'key': 'updatedkey',
            'name': 'testname',
            'directory': 'testdirectory',
            'index_schedule': 7200,
            'delete_old_media': False,
            'days_to_keep': 14,
            'source_resolution': '1080p',
            'source_vcodec': 'VP9',
            'source_acodec': 'OPUS',
            'prefer_60fps': False,
            'prefer_hdr': False,
            'fallback': 'f'
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
        test_source = Source.objects.create(**{
            'source_type': 'c',
            'key': 'testkey',
            'name': 'testname',
            'directory': 'testdirectory',
            'index_schedule': 3600,
            'delete_old_media': False,
            'days_to_keep': 14,
            'source_resolution': '1080p',
            'source_vcodec': 'VP9',
            'source_acodec': 'OPUS',
            'prefer_60fps': False,
            'prefer_hdr': False,
            'fallback': 'f'
        })
        # Add some media
        test_media1 = Media.objects.create(**{
            'key': 'mediakey1',
            'source': test_source,
            'metadata': '{"thumbnail":"https://example.com/thumb.jpg"}',
        })
        test_media1_pk = str(test_media1.pk)
        test_media2 = Media.objects.create(**{
            'key': 'mediakey2',
            'source': test_source,
            'metadata': '{"thumbnail":"https://example.com/thumb.jpg"}',
        })
        test_media2_pk = str(test_media2.pk)
        test_media3 = Media.objects.create(**{
            'key': 'mediakey3',
            'source': test_source,
            'metadata': '{"thumbnail":"https://example.com/thumb.jpg"}',
        })
        test_media3_pk = str(test_media3.pk)
        # Check the tasks to fetch the media thumbnails have been scheduled
        found_thumbnail_task1 = False
        found_thumbnail_task2 = False
        found_thumbnail_task3 = False
        q = {'queue': str(test_source.pk),
             'task_name': 'sync.tasks.download_media_thumbnail'}
        for task in Task.objects.filter(**q):
            if test_media1_pk in task.task_params:
                found_thumbnail_task1 = True
            if test_media2_pk in task.task_params:
                found_thumbnail_task2 = True
            if test_media3_pk in task.task_params:
                found_thumbnail_task3 = True
        self.assertTrue(found_thumbnail_task1)
        self.assertTrue(found_thumbnail_task2)
        self.assertTrue(found_thumbnail_task3)
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
        tasks = Task.objects.filter(**q)
        self.assertFalse(tasks)

    def test_tasks(self):
        # Tasks overview page
        c = Client()
        response = c.get('/tasks')
        self.assertEqual(response.status_code, 200)
        # Completed tasks overview page
        response = c.get('/tasks-completed')
        self.assertEqual(response.status_code, 200)


class FormatMatchingTestCase(TestCase):

    def setUp(self):
        # Disable general logging for test case
        logging.disable(logging.CRITICAL)
        # Test metadata pulled from https://youtube.com/watch?v=AIigN0EAGcA
        metadata = '''
            {
                "id":"AIigN0EAGcA",
                "uploader":"The HDR Channel",
                "uploader_id":"UCve7_yAZHFNipzeAGBI5t9g",
                "uploader_url":"http://www.youtube.com/channel/UCve7_yAZHFNipzeAGBI5t9g",
                "channel_id":"UCve7_yAZHFNipzeAGBI5t9g",
                "channel_url":"http://www.youtube.com/channel/UCve7_yAZHFNipzeAGBI5t9g",
                "upload_date":"20161202",
                "license":null,
                "creator":null,
                "title":"Real 4K HDR: Earth and Aurora Borealis seen from ISS - HDR UHD (Chromecast Ultra)",
                "alt_title":null,
                "thumbnails":[
                    {
                        "url":"[truncated]",
                        "width":168,
                        "height":94,
                        "resolution":"168x94",
                        "id":"0"
                    },
                    {
                        "url":"[truncated]",
                        "width":196,
                        "height":110,
                        "resolution":"196x110",
                        "id":"1"
                    },
                    {
                        "url":"[truncated]",
                        "width":246,
                        "height":138,
                        "resolution":"246x138",
                        "id":"2"
                    },
                    {
                        "url":"[truncated]",
                        "width":336,
                        "height":188,
                        "resolution":"336x188",
                        "id":"3"
                    },
                    {
                        "url":"[truncated]",
                        "width":1920,
                        "height":1080,
                        "resolution":"1920x1080",
                        "id":"4"
                    }
                ],
                "description":"[truncated]",
                "categories":[
                    "Travel & Events"
                ],
                "tags":[
                    "hdr",
                    "hdr10",
                    "4k",
                    "uhd",
                    "chromecast ultra",
                    "real hdr"
                ],
                "subtitles":{
                    
                },
                "automatic_captions":{
                    
                },
                "duration":353.0,
                "age_limit":0,
                "annotations":null,
                "chapters":null,
                "webpage_url":"https://www.youtube.com/watch?v=AIigN0EAGcA",
                "view_count":131816,
                "like_count":211,
                "dislike_count":20,
                "average_rating":4.6536798,
                "formats":[
                    {
                        "format_id":"249",
                        "url":"[truncated]",
                        "player_url":null,
                        "ext":"webm",
                        "format_note":"tiny",
                        "acodec":"opus",
                        "abr":50,
                        "asr":48000,
                        "filesize":2690312,
                        "fps":null,
                        "height":null,
                        "tbr":65.092,
                        "width":null,
                        "vcodec":"none",
                        "downloader_options":{
                            "http_chunk_size":10485760
                        },
                        "format":"249 - audio only (tiny)",
                        "protocol":"https",
                        "http_headers":{
                            "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3704.8 Safari/537.36",
                            "Accept-Charset":"ISO-8859-1,utf-8;q=0.7,*;q=0.7",
                            "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                            "Accept-Encoding":"gzip, deflate",
                            "Accept-Language":"en-us,en;q=0.5"
                        }
                    },
                    {
                        "format_id":"250",
                        "url":"[truncated]",
                        "player_url":null,
                        "ext":"webm",
                        "format_note":"tiny",
                        "acodec":"opus",
                        "abr":70,
                        "asr":48000,
                        "filesize":3502678,
                        "fps":null,
                        "height":null,
                        "tbr":85.607,
                        "width":null,
                        "vcodec":"none",
                        "downloader_options":{
                            "http_chunk_size":10485760
                        },
                        "format":"250 - audio only (tiny)",
                        "protocol":"https",
                        "http_headers":{
                            "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3704.8 Safari/537.36",
                            "Accept-Charset":"ISO-8859-1,utf-8;q=0.7,*;q=0.7",
                            "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                            "Accept-Encoding":"gzip, deflate",
                            "Accept-Language":"en-us,en;q=0.5"
                        }
                    },
                    {
                        "format_id":"140",
                        "url":"[truncated]",
                        "player_url":null,
                        "ext":"m4a",
                        "format_note":"tiny",
                        "acodec":"mp4a.40.2",
                        "abr":128,
                        "container":"m4a_dash",
                        "asr":44100,
                        "filesize":5703344,
                        "fps":null,
                        "height":null,
                        "tbr":130.563,
                        "width":null,
                        "vcodec":"none",
                        "downloader_options":{
                            "http_chunk_size":10485760
                        },
                        "format":"140 - audio only (tiny)",
                        "protocol":"https",
                        "http_headers":{
                            "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3704.8 Safari/537.36",
                            "Accept-Charset":"ISO-8859-1,utf-8;q=0.7,*;q=0.7",
                            "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                            "Accept-Encoding":"gzip, deflate",
                            "Accept-Language":"en-us,en;q=0.5"
                        }
                    },
                    {
                        "format_id":"251",
                        "url":"[truncated]",
                        "player_url":null,
                        "ext":"webm",
                        "format_note":"tiny",
                        "acodec":"opus",
                        "abr":160,
                        "asr":48000,
                        "filesize":6488055,
                        "fps":null,
                        "height":null,
                        "tbr":157.878,
                        "width":null,
                        "vcodec":"none",
                        "downloader_options":{
                            "http_chunk_size":10485760
                        },
                        "format":"251 - audio only (tiny)",
                        "protocol":"https",
                        "http_headers":{
                            "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3704.8 Safari/537.36",
                            "Accept-Charset":"ISO-8859-1,utf-8;q=0.7,*;q=0.7",
                            "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                            "Accept-Encoding":"gzip, deflate",
                            "Accept-Language":"en-us,en;q=0.5"
                        }
                    },
                    {
                        "format_id":"160",
                        "url":"[truncated]",
                        "player_url":null,
                        "ext":"mp4",
                        "height":144,
                        "format_note":"144p",
                        "vcodec":"avc1.4d400c",
                        "asr":null,
                        "filesize":1655725,
                        "fps":30,
                        "tbr":84.26,
                        "width":256,
                        "acodec":"none",
                        "downloader_options":{
                            "http_chunk_size":10485760
                        },
                        "format":"160 - 256x144 (144p)",
                        "protocol":"https",
                        "http_headers":{
                            "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3704.8 Safari/537.36",
                            "Accept-Charset":"ISO-8859-1,utf-8;q=0.7,*;q=0.7",
                            "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                            "Accept-Encoding":"gzip, deflate",
                            "Accept-Language":"en-us,en;q=0.5"
                        }
                    },
                    {
                        "format_id":"278",
                        "url":"[truncated]",
                        "player_url":null,
                        "ext":"webm",
                        "height":144,
                        "format_note":"144p",
                        "container":"webm",
                        "vcodec":"vp9",
                        "asr":null,
                        "filesize":3399643,
                        "fps":30,
                        "tbr":97.395,
                        "width":256,
                        "acodec":"none",
                        "downloader_options":{
                            "http_chunk_size":10485760
                        },
                        "format":"278 - 256x144 (144p)",
                        "protocol":"https",
                        "http_headers":{
                            "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3704.8 Safari/537.36",
                            "Accept-Charset":"ISO-8859-1,utf-8;q=0.7,*;q=0.7",
                            "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                            "Accept-Encoding":"gzip, deflate",
                            "Accept-Language":"en-us,en;q=0.5"
                        }
                    },
                    {
                        "format_id":"330",
                        "url":"[truncated]",
                        "player_url":null,
                        "asr":null,
                        "filesize":4569924,
                        "format_note":"144p HDR",
                        "fps":30,
                        "height":144,
                        "tbr":151.8,
                        "width":256,
                        "ext":"webm",
                        "vcodec":"vp9.2",
                        "acodec":"none",
                        "downloader_options":{
                            "http_chunk_size":10485760
                        },
                        "format":"330 - 256x144 (144p HDR)",
                        "protocol":"https",
                        "http_headers":{
                            "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3704.8 Safari/537.36",
                            "Accept-Charset":"ISO-8859-1,utf-8;q=0.7,*;q=0.7",
                            "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                            "Accept-Encoding":"gzip, deflate",
                            "Accept-Language":"en-us,en;q=0.5"
                        }
                    },
                    {
                        "format_id":"133",
                        "url":"[truncated]",
                        "player_url":null,
                        "ext":"mp4",
                        "height":240,
                        "format_note":"240p",
                        "vcodec":"avc1.4d4015",
                        "asr":null,
                        "filesize":3090930,
                        "fps":30,
                        "tbr":154.701,
                        "width":426,
                        "acodec":"none",
                        "downloader_options":{
                            "http_chunk_size":10485760
                        },
                        "format":"133 - 426x240 (240p)",
                        "protocol":"https",
                        "http_headers":{
                            "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3704.8 Safari/537.36",
                            "Accept-Charset":"ISO-8859-1,utf-8;q=0.7,*;q=0.7",
                            "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                            "Accept-Encoding":"gzip, deflate",
                            "Accept-Language":"en-us,en;q=0.5"
                        }
                    },
                    {
                        "format_id":"242",
                        "url":"[truncated]",
                        "player_url":null,
                        "ext":"webm",
                        "height":240,
                        "format_note":"240p",
                        "vcodec":"vp9",
                        "asr":null,
                        "filesize":5194185,
                        "fps":30,
                        "tbr":220.461,
                        "width":426,
                        "acodec":"none",
                        "downloader_options":{
                            "http_chunk_size":10485760
                        },
                        "format":"242 - 426x240 (240p)",
                        "protocol":"https",
                        "http_headers":{
                            "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3704.8 Safari/537.36",
                            "Accept-Charset":"ISO-8859-1,utf-8;q=0.7,*;q=0.7",
                            "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                            "Accept-Encoding":"gzip, deflate",
                            "Accept-Language":"en-us,en;q=0.5"
                        }
                    },
                    {
                        "format_id":"331",
                        "url":"[truncated]",
                        "player_url":null,
                        "asr":null,
                        "filesize":8625105,
                        "format_note":"240p HDR",
                        "fps":30,
                        "height":240,
                        "tbr":269.523,
                        "width":426,
                        "ext":"webm",
                        "vcodec":"vp9.2",
                        "acodec":"none",
                        "downloader_options":{
                            "http_chunk_size":10485760
                        },
                        "format":"331 - 426x240 (240p HDR)",
                        "protocol":"https",
                        "http_headers":{
                            "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3704.8 Safari/537.36",
                            "Accept-Charset":"ISO-8859-1,utf-8;q=0.7,*;q=0.7",
                            "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                            "Accept-Encoding":"gzip, deflate",
                            "Accept-Language":"en-us,en;q=0.5"
                        }
                    },
                    {
                        "format_id":"134",
                        "url":"[truncated]",
                        "player_url":null,
                        "ext":"mp4",
                        "height":360,
                        "format_note":"360p",
                        "vcodec":"avc1.4d401e",
                        "asr":null,
                        "filesize":7976121,
                        "fps":30,
                        "tbr":372.176,
                        "width":640,
                        "acodec":"none",
                        "downloader_options":{
                            "http_chunk_size":10485760
                        },
                        "format":"134 - 640x360 (360p)",
                        "protocol":"https",
                        "http_headers":{
                            "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3704.8 Safari/537.36",
                            "Accept-Charset":"ISO-8859-1,utf-8;q=0.7,*;q=0.7",
                            "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                            "Accept-Encoding":"gzip, deflate",
                            "Accept-Language":"en-us,en;q=0.5"
                        }
                    },
                    {
                        "format_id":"243",
                        "url":"[truncated]",
                        "player_url":null,
                        "ext":"webm",
                        "height":360,
                        "format_note":"360p",
                        "vcodec":"vp9",
                        "asr":null,
                        "filesize":10334380,
                        "fps":30,
                        "tbr":408.705,
                        "width":640,
                        "acodec":"none",
                        "downloader_options":{
                            "http_chunk_size":10485760
                        },
                        "format":"243 - 640x360 (360p)",
                        "protocol":"https",
                        "http_headers":{
                            "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3704.8 Safari/537.36",
                            "Accept-Charset":"ISO-8859-1,utf-8;q=0.7,*;q=0.7",
                            "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                            "Accept-Encoding":"gzip, deflate",
                            "Accept-Language":"en-us,en;q=0.5"
                        }
                    },
                    {
                        "format_id":"332",
                        "url":"[truncated]",
                        "player_url":null,
                        "asr":null,
                        "filesize":19094551,
                        "format_note":"360p HDR",
                        "fps":30,
                        "height":360,
                        "tbr":580.076,
                        "width":640,
                        "ext":"webm",
                        "vcodec":"vp9.2",
                        "acodec":"none",
                        "downloader_options":{
                            "http_chunk_size":10485760
                        },
                        "format":"332 - 640x360 (360p HDR)",
                        "protocol":"https",
                        "http_headers":{
                            "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3704.8 Safari/537.36",
                            "Accept-Charset":"ISO-8859-1,utf-8;q=0.7,*;q=0.7",
                            "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                            "Accept-Encoding":"gzip, deflate",
                            "Accept-Language":"en-us,en;q=0.5"
                        }
                    },
                    {
                        "format_id":"244",
                        "url":"[truncated]",
                        "player_url":null,
                        "ext":"webm",
                        "height":480,
                        "format_note":"480p",
                        "vcodec":"vp9",
                        "asr":null,
                        "filesize":18651778,
                        "fps":30,
                        "tbr":748.286,
                        "width":854,
                        "acodec":"none",
                        "downloader_options":{
                            "http_chunk_size":10485760
                        },
                        "format":"244 - 854x480 (480p)",
                        "protocol":"https",
                        "http_headers":{
                            "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3704.8 Safari/537.36",
                            "Accept-Charset":"ISO-8859-1,utf-8;q=0.7,*;q=0.7",
                            "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                            "Accept-Encoding":"gzip, deflate",
                            "Accept-Language":"en-us,en;q=0.5"
                        }
                    },
                    {
                        "format_id":"135",
                        "url":"[truncated]",
                        "player_url":null,
                        "ext":"mp4",
                        "height":480,
                        "format_note":"480p",
                        "vcodec":"avc1.4d401f",
                        "asr":null,
                        "filesize":17751590,
                        "fps":30,
                        "tbr":828.339,
                        "width":854,
                        "acodec":"none",
                        "downloader_options":{
                            "http_chunk_size":10485760
                        },
                        "format":"135 - 854x480 (480p)",
                        "protocol":"https",
                        "http_headers":{
                            "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3704.8 Safari/537.36",
                            "Accept-Charset":"ISO-8859-1,utf-8;q=0.7,*;q=0.7",
                            "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                            "Accept-Encoding":"gzip, deflate",
                            "Accept-Language":"en-us,en;q=0.5"
                        }
                    },
                    {
                        "format_id":"333",
                        "url":"[truncated]",
                        "player_url":null,
                        "asr":null,
                        "filesize":37534410,
                        "format_note":"480p HDR",
                        "fps":30,
                        "height":480,
                        "tbr":1088.473,
                        "width":854,
                        "ext":"webm",
                        "vcodec":"vp9.2",
                        "acodec":"none",
                        "downloader_options":{
                            "http_chunk_size":10485760
                        },
                        "format":"333 - 854x480 (480p HDR)",
                        "protocol":"https",
                        "http_headers":{
                            "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3704.8 Safari/537.36",
                            "Accept-Charset":"ISO-8859-1,utf-8;q=0.7,*;q=0.7",
                            "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                            "Accept-Encoding":"gzip, deflate",
                            "Accept-Language":"en-us,en;q=0.5"
                        }
                    },
                    {
                        "format_id":"136",
                        "url":"[truncated]",
                        "player_url":null,
                        "ext":"mp4",
                        "height":720,
                        "format_note":"720p",
                        "vcodec":"avc1.4d401f",
                        "asr":null,
                        "filesize":33269335,
                        "fps":30,
                        "tbr":1391.37,
                        "width":1280,
                        "acodec":"none",
                        "downloader_options":{
                            "http_chunk_size":10485760
                        },
                        "format":"136 - 1280x720 (720p)",
                        "protocol":"https",
                        "http_headers":{
                            "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3704.8 Safari/537.36",
                            "Accept-Charset":"ISO-8859-1,utf-8;q=0.7,*;q=0.7",
                            "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                            "Accept-Encoding":"gzip, deflate",
                            "Accept-Language":"en-us,en;q=0.5"
                        }
                    },
                    {
                        "format_id":"247",
                        "url":"[truncated]",
                        "player_url":null,
                        "ext":"webm",
                        "height":720,
                        "format_note":"720p",
                        "vcodec":"vp9",
                        "asr":null,
                        "filesize":38700375,
                        "fps":30,
                        "tbr":1509.156,
                        "width":1280,
                        "acodec":"none",
                        "downloader_options":{
                            "http_chunk_size":10485760
                        },
                        "format":"247 - 1280x720 (720p)",
                        "protocol":"https",
                        "http_headers":{
                            "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3704.8 Safari/537.36",
                            "Accept-Charset":"ISO-8859-1,utf-8;q=0.7,*;q=0.7",
                            "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                            "Accept-Encoding":"gzip, deflate",
                            "Accept-Language":"en-us,en;q=0.5"
                        }
                    },
                    {
                        "format_id":"334",
                        "url":"[truncated]",
                        "player_url":null,
                        "asr":null,
                        "filesize":84688291,
                        "format_note":"720p HDR",
                        "fps":30,
                        "height":720,
                        "tbr":2459.121,
                        "width":1280,
                        "ext":"webm",
                        "vcodec":"vp9.2",
                        "acodec":"none",
                        "downloader_options":{
                            "http_chunk_size":10485760
                        },
                        "format":"334 - 1280x720 (720p HDR)",
                        "protocol":"https",
                        "http_headers":{
                            "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3704.8 Safari/537.36",
                            "Accept-Charset":"ISO-8859-1,utf-8;q=0.7,*;q=0.7",
                            "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                            "Accept-Encoding":"gzip, deflate",
                            "Accept-Language":"en-us,en;q=0.5"
                        }
                    },
                    {
                        "format_id":"248",
                        "url":"[truncated]",
                        "player_url":null,
                        "ext":"webm",
                        "height":1080,
                        "format_note":"1080p",
                        "vcodec":"vp9",
                        "asr":null,
                        "filesize":74559430,
                        "fps":30,
                        "tbr":2655.043,
                        "width":1920,
                        "acodec":"none",
                        "downloader_options":{
                            "http_chunk_size":10485760
                        },
                        "format":"248 - 1920x1080 (1080p)",
                        "protocol":"https",
                        "http_headers":{
                            "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3704.8 Safari/537.36",
                            "Accept-Charset":"ISO-8859-1,utf-8;q=0.7,*;q=0.7",
                            "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                            "Accept-Encoding":"gzip, deflate",
                            "Accept-Language":"en-us,en;q=0.5"
                        }
                    },
                    {
                        "format_id":"137",
                        "url":"[truncated]",
                        "player_url":null,
                        "ext":"mp4",
                        "height":1080,
                        "format_note":"1080p",
                        "vcodec":"avc1.640028",
                        "asr":null,
                        "filesize":66088922,
                        "fps":30,
                        "tbr":3401.043,
                        "width":1920,
                        "acodec":"none",
                        "downloader_options":{
                            "http_chunk_size":10485760
                        },
                        "format":"137 - 1920x1080 (1080p)",
                        "protocol":"https",
                        "http_headers":{
                            "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3704.8 Safari/537.36",
                            "Accept-Charset":"ISO-8859-1,utf-8;q=0.7,*;q=0.7",
                            "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                            "Accept-Encoding":"gzip, deflate",
                            "Accept-Language":"en-us,en;q=0.5"
                        }
                    },
                    {
                        "format_id":"335",
                        "url":"[truncated]",
                        "player_url":null,
                        "asr":null,
                        "filesize":147068515,
                        "format_note":"1080p HDR",
                        "fps":30,
                        "height":1080,
                        "tbr":4143.689,
                        "width":1920,
                        "ext":"webm",
                        "vcodec":"vp9.2",
                        "acodec":"none",
                        "downloader_options":{
                            "http_chunk_size":10485760
                        },
                        "format":"335 - 1920x1080 (1080p HDR)",
                        "protocol":"https",
                        "http_headers":{
                            "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3704.8 Safari/537.36",
                            "Accept-Charset":"ISO-8859-1,utf-8;q=0.7,*;q=0.7",
                            "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                            "Accept-Encoding":"gzip, deflate",
                            "Accept-Language":"en-us,en;q=0.5"
                        }
                    },
                    {
                        "format_id":"271",
                        "url":"[truncated]",
                        "player_url":null,
                        "ext":"webm",
                        "height":1440,
                        "format_note":"1440p",
                        "vcodec":"vp9",
                        "asr":null,
                        "filesize":220803978,
                        "fps":30,
                        "tbr":8844.345,
                        "width":2560,
                        "acodec":"none",
                        "downloader_options":{
                            "http_chunk_size":10485760
                        },
                        "format":"271 - 2560x1440 (1440p)",
                        "protocol":"https",
                        "http_headers":{
                            "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3704.8 Safari/537.36",
                            "Accept-Charset":"ISO-8859-1,utf-8;q=0.7,*;q=0.7",
                            "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                            "Accept-Encoding":"gzip, deflate",
                            "Accept-Language":"en-us,en;q=0.5"
                        }
                    },
                    {
                        "format_id":"336",
                        "url":"[truncated]",
                        "player_url":null,
                        "asr":null,
                        "filesize":445968338,
                        "format_note":"1440p HDR",
                        "fps":30,
                        "height":1440,
                        "tbr":11013.316,
                        "width":2560,
                        "ext":"webm",
                        "vcodec":"vp9.2",
                        "acodec":"none",
                        "downloader_options":{
                            "http_chunk_size":10485760
                        },
                        "format":"336 - 2560x1440 (1440p HDR)",
                        "protocol":"https",
                        "http_headers":{
                            "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3704.8 Safari/537.36",
                            "Accept-Charset":"ISO-8859-1,utf-8;q=0.7,*;q=0.7",
                            "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                            "Accept-Encoding":"gzip, deflate",
                            "Accept-Language":"en-us,en;q=0.5"
                        }
                    },
                    {
                        "format_id":"313",
                        "url":"[truncated]",
                        "player_url":null,
                        "ext":"webm",
                        "height":2160,
                        "format_note":"2160p",
                        "vcodec":"vp9",
                        "asr":null,
                        "filesize":592906196,
                        "fps":30,
                        "tbr":17720.165,
                        "width":3840,
                        "acodec":"none",
                        "downloader_options":{
                            "http_chunk_size":10485760
                        },
                        "format":"313 - 3840x2160 (2160p)",
                        "protocol":"https",
                        "http_headers":{
                            "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3704.8 Safari/537.36",
                            "Accept-Charset":"ISO-8859-1,utf-8;q=0.7,*;q=0.7",
                            "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                            "Accept-Encoding":"gzip, deflate",
                            "Accept-Language":"en-us,en;q=0.5"
                        }
                    },
                    {
                        "format_id":"337",
                        "url":"[truncated]",
                        "player_url":null,
                        "asr":null,
                        "filesize":985983779,
                        "format_note":"2160p HDR",
                        "fps":30,
                        "height":2160,
                        "tbr":23857.847,
                        "width":3840,
                        "ext":"webm",
                        "vcodec":"vp9.2",
                        "acodec":"none",
                        "downloader_options":{
                            "http_chunk_size":10485760
                        },
                        "format":"337 - 3840x2160 (2160p HDR)",
                        "protocol":"https",
                        "http_headers":{
                            "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3704.8 Safari/537.36",
                            "Accept-Charset":"ISO-8859-1,utf-8;q=0.7,*;q=0.7",
                            "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                            "Accept-Encoding":"gzip, deflate",
                            "Accept-Language":"en-us,en;q=0.5"
                        }
                    },
                    {
                        "format_id":"18",
                        "url":"[truncated]",
                        "player_url":null,
                        "ext":"mp4",
                        "width":640,
                        "height":360,
                        "acodec":"mp4a.40.2",
                        "abr":96,
                        "vcodec":"avc1.42001E",
                        "asr":44100,
                        "filesize":23149671,
                        "format_note":"360p",
                        "fps":30,
                        "tbr":525.68,
                        "format":"18 - 640x360 (360p)",
                        "protocol":"https",
                        "http_headers":{
                            "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3704.8 Safari/537.36",
                            "Accept-Charset":"ISO-8859-1,utf-8;q=0.7,*;q=0.7",
                            "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                            "Accept-Encoding":"gzip, deflate",
                            "Accept-Language":"en-us,en;q=0.5"
                        }
                    },
                    {
                        "format_id":"22",
                        "url":"[truncated]",
                        "player_url":null,
                        "ext":"mp4",
                        "width":1280,
                        "height":720,
                        "acodec":"mp4a.40.2",
                        "abr":192,
                        "vcodec":"avc1.64001F",
                        "asr":44100,
                        "filesize":null,
                        "format_note":"720p",
                        "fps":30,
                        "tbr":884.489,
                        "format":"22 - 1280x720 (720p)",
                        "protocol":"https",
                        "http_headers":{
                            "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3704.8 Safari/537.36",
                            "Accept-Charset":"ISO-8859-1,utf-8;q=0.7,*;q=0.7",
                            "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                            "Accept-Encoding":"gzip, deflate",
                            "Accept-Language":"en-us,en;q=0.5"
                        }
                    }
                ],
                "is_live":null,
                "start_time":null,
                "end_time":null,
                "series":null,
                "season_number":null,
                "episode_number":null,
                "track":null,
                "artist":null,
                "album":null,
                "release_date":null,
                "release_year":null,
                "extractor":"youtube",
                "webpage_url_basename":"AIigN0EAGcA",
                "extractor_key":"Youtube",
                "n_entries":13,
                "playlist":"HDR",
                "playlist_id":"PL0ajMRlXs96rAqJhIMXiG34khg31MVWdP",
                "playlist_title":"HDR",
                "playlist_uploader":"4K",
                "playlist_uploader_id":"UCp5zSuQPhXhFEurTP0l4yCw",
                "playlist_index":13,
                "thumbnail":"https://i.ytimg.com/vi_webp/AIigN0EAGcA/maxresdefault.webp",
                "display_id":"AIigN0EAGcA",
                "requested_subtitles":null,
                "requested_formats":[
                    {
                        "format_id":"337",
                        "url":"[truncated]",
                        "player_url":null,
                        "asr":null,
                        "filesize":985983779,
                        "format_note":"2160p HDR",
                        "fps":30,
                        "height":2160,
                        "tbr":23857.847,
                        "width":3840,
                        "ext":"webm",
                        "vcodec":"vp9.2",
                        "acodec":"none",
                        "downloader_options":{
                            "http_chunk_size":10485760
                        },
                        "format":"337 - 3840x2160 (2160p HDR)",
                        "protocol":"https",
                        "http_headers":{
                            "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3704.8 Safari/537.36",
                            "Accept-Charset":"ISO-8859-1,utf-8;q=0.7,*;q=0.7",
                            "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                            "Accept-Encoding":"gzip, deflate",
                            "Accept-Language":"en-us,en;q=0.5"
                        }
                    },
                    {
                        "format_id":"251",
                        "url":"[truncated]",
                        "player_url":null,
                        "ext":"webm",
                        "format_note":"tiny",
                        "acodec":"opus",
                        "abr":160,
                        "asr":48000,
                        "filesize":6488055,
                        "fps":null,
                        "height":null,
                        "tbr":157.878,
                        "width":null,
                        "vcodec":"none",
                        "downloader_options":{
                            "http_chunk_size":10485760
                        },
                        "format":"251 - audio only (tiny)",
                        "protocol":"https",
                        "http_headers":{
                            "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3704.8 Safari/537.36",
                            "Accept-Charset":"ISO-8859-1,utf-8;q=0.7,*;q=0.7",
                            "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                            "Accept-Encoding":"gzip, deflate",
                            "Accept-Language":"en-us,en;q=0.5"
                        }
                    }
                ],
                "format":"337 - 3840x2160 (2160p HDR)+251 - audio only (tiny)",
                "format_id":"337+251",
                "width":3840,
                "height":2160,
                "resolution":null,
                "fps":30,
                "vcodec":"vp9.2",
                "vbr":null,
                "stretched_ratio":null,
                "acodec":"opus",
                "abr":160,
                "ext":"webm"
            }
        '''.strip()
        # Add a test source
        self.source = Source.objects.create(**{
            'source_type': 'c',
            'key': 'testkey',
            'name': 'testname',
            'directory': 'testdirectory',
            'index_schedule': 3600,
            'delete_old_media': False,
            'days_to_keep': 14,
            'source_resolution': '1080p',
            'source_vcodec': 'VP9',
            'source_acodec': 'OPUS',
            'prefer_60fps': False,
            'prefer_hdr': False,
            'fallback': 'f'
        })
        # Add some media
        self.media = Media.objects.create(**{
            'key': 'mediakey',
            'source': self.source,
            'metadata': metadata,
        })

    '''
        Parsed media format reference for test metadata:
            {'id': '249', 'format': 'TINY', 'format_verbose': '249 - audio only (tiny)', 'height': None, 'vcodec': None, 'vbr': 65.092, 'acodec': 'OPUS', 'abr': 50, 'is_60fps': False, 'is_hdr': False}
            {'id': '250', 'format': 'TINY', 'format_verbose': '250 - audio only (tiny)', 'height': None, 'vcodec': None, 'vbr': 85.607, 'acodec': 'OPUS', 'abr': 70, 'is_60fps': False, 'is_hdr': False}
            {'id': '140', 'format': 'TINY', 'format_verbose': '140 - audio only (tiny)', 'height': None, 'vcodec': None, 'vbr': 130.563, 'acodec': 'MP4A', 'abr': 128, 'is_60fps': False, 'is_hdr': False}
            {'id': '251', 'format': 'TINY', 'format_verbose': '251 - audio only (tiny)', 'height': None, 'vcodec': None, 'vbr': 157.878, 'acodec': 'OPUS', 'abr': 160, 'is_60fps': False, 'is_hdr': False}
            {'id': '160', 'format': '144P', 'format_verbose': '160 - 256x144 (144p)', 'height': 144, 'vcodec': 'AVC1', 'vbr': 84.26, 'acodec': None, 'abr': 0, 'is_60fps': False, 'is_hdr': False}
            {'id': '278', 'format': '144P', 'format_verbose': '278 - 256x144 (144p)', 'height': 144, 'vcodec': 'VP9', 'vbr': 97.395, 'acodec': None, 'abr': 0, 'is_60fps': False, 'is_hdr': False}
            {'id': '330', 'format': '144P HDR', 'format_verbose': '330 - 256x144 (144p HDR)', 'height': 144, 'vcodec': 'VP9', 'vbr': 151.8, 'acodec': None, 'abr': 0, 'is_60fps': False, 'is_hdr': True}
            {'id': '133', 'format': '240P', 'format_verbose': '133 - 426x240 (240p)', 'height': 240, 'vcodec': 'AVC1', 'vbr': 154.701, 'acodec': None, 'abr': 0, 'is_60fps': False, 'is_hdr': False}
            {'id': '242', 'format': '240P', 'format_verbose': '242 - 426x240 (240p)', 'height': 240, 'vcodec': 'VP9', 'vbr': 220.461, 'acodec': None, 'abr': 0, 'is_60fps': False, 'is_hdr': False}
            {'id': '331', 'format': '240P HDR', 'format_verbose': '331 - 426x240 (240p HDR)', 'height': 240, 'vcodec': 'VP9', 'vbr': 269.523, 'acodec': None, 'abr': 0, 'is_60fps': False, 'is_hdr': True}
            {'id': '134', 'format': '360P', 'format_verbose': '134 - 640x360 (360p)', 'height': 360, 'vcodec': 'AVC1', 'vbr': 372.176, 'acodec': None, 'abr': 0, 'is_60fps': False, 'is_hdr': False}
            {'id': '243', 'format': '360P', 'format_verbose': '243 - 640x360 (360p)', 'height': 360, 'vcodec': 'VP9', 'vbr': 408.705, 'acodec': None, 'abr': 0, 'is_60fps': False, 'is_hdr': False}
            {'id': '332', 'format': '360P HDR', 'format_verbose': '332 - 640x360 (360p HDR)', 'height': 360, 'vcodec': 'VP9', 'vbr': 580.076, 'acodec': None, 'abr': 0, 'is_60fps': False, 'is_hdr': True}
            {'id': '244', 'format': '480P', 'format_verbose': '244 - 854x480 (480p)', 'height': 480, 'vcodec': 'VP9', 'vbr': 748.286, 'acodec': None, 'abr': 0, 'is_60fps': False, 'is_hdr': False}
            {'id': '135', 'format': '480P', 'format_verbose': '135 - 854x480 (480p)', 'height': 480, 'vcodec': 'AVC1', 'vbr': 828.339, 'acodec': None, 'abr': 0, 'is_60fps': False, 'is_hdr': False}
            {'id': '333', 'format': '480P HDR', 'format_verbose': '333 - 854x480 (480p HDR)', 'height': 480, 'vcodec': 'VP9', 'vbr': 1088.473, 'acodec': None, 'abr': 0, 'is_60fps': False, 'is_hdr': True}
            {'id': '136', 'format': '720P', 'format_verbose': '136 - 1280x720 (720p)', 'height': 720, 'vcodec': 'AVC1', 'vbr': 1391.37, 'acodec': None, 'abr': 0, 'is_60fps': False, 'is_hdr': False}
            {'id': '247', 'format': '720P', 'format_verbose': '247 - 1280x720 (720p)', 'height': 720, 'vcodec': 'VP9', 'vbr': 1509.156, 'acodec': None, 'abr': 0, 'is_60fps': False, 'is_hdr': False}
            {'id': '334', 'format': '720P HDR', 'format_verbose': '334 - 1280x720 (720p HDR)', 'height': 720, 'vcodec': 'VP9', 'vbr': 2459.121, 'acodec': None, 'abr': 0, 'is_60fps': False, 'is_hdr': True}
            {'id': '248', 'format': '1080P', 'format_verbose': '248 - 1920x1080 (1080p)', 'height': 1080, 'vcodec': 'VP9', 'vbr': 2655.043, 'acodec': None, 'abr': 0, 'is_60fps': False, 'is_hdr': False}
            {'id': '137', 'format': '1080P', 'format_verbose': '137 - 1920x1080 (1080p)', 'height': 1080, 'vcodec': 'AVC1', 'vbr': 3401.043, 'acodec': None, 'abr': 0, 'is_60fps': False, 'is_hdr': False}
            {'id': '335', 'format': '1080P HDR', 'format_verbose': '335 - 1920x1080 (1080p HDR)', 'height': 1080, 'vcodec': 'VP9', 'vbr': 4143.689, 'acodec': None, 'abr': 0, 'is_60fps': False, 'is_hdr': True}
            {'id': '271', 'format': '1440P', 'format_verbose': '271 - 2560x1440 (1440p)', 'height': 1440, 'vcodec': 'VP9', 'vbr': 8844.345, 'acodec': None, 'abr': 0, 'is_60fps': False, 'is_hdr': False}
            {'id': '336', 'format': '1440P HDR', 'format_verbose': '336 - 2560x1440 (1440p HDR)', 'height': 1440, 'vcodec': 'VP9', 'vbr': 11013.316, 'acodec': None, 'abr': 0, 'is_60fps': False, 'is_hdr': True}
            {'id': '313', 'format': '2160P', 'format_verbose': '313 - 3840x2160 (2160p)', 'height': 2160, 'vcodec': 'VP9', 'vbr': 17720.165, 'acodec': None, 'abr': 0, 'is_60fps': False, 'is_hdr': False}
            {'id': '337', 'format': '2160P HDR', 'format_verbose': '337 - 3840x2160 (2160p HDR)', 'height': 2160, 'vcodec': 'VP9', 'vbr': 23857.847, 'acodec': None, 'abr': 0, 'is_60fps': False, 'is_hdr': True}
            {'id': '18', 'format': '360P', 'format_verbose': '18 - 640x360 (360p)', 'height': 360, 'vcodec': 'AVC1', 'vbr': 525.68, 'acodec': 'MP4A', 'abr': 96, 'is_60fps': False, 'is_hdr': False}
            {'id': '22', 'format': '720P', 'format_verbose': '22 - 1280x720 (720p)', 'height': 720, 'vcodec': 'AVC1', 'vbr': 884.489, 'acodec': 'MP4A', 'abr': 192, 'is_60fps': False, 'is_hdr': False}

    '''

    def test_combined_format_matching(self):
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
            self.assertEqual(match_type, expeceted_match_type)
            self.assertEqual(format_code, expected_format_code)

    def test_audio_format_matching(self):
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
            self.assertEqual(match_type, expeceted_match_type)
            self.assertEqual(format_code, expected_format_code)

    def test_video_format_matching(self):
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
        }
        for params, expected in expected_matches.items():
            resolution, vcodec, acodec, prefer_60fps, prefer_hdr = params
            expeceted_match_type, expected_format_code = expected
            self.source.source_resolution = resolution
            self.source.source_vcodec = vcodec
            self.source.source_acodec = acodec
            self.source.prefer_60fps = prefer_60fps
            self.source.prefer_hdr = prefer_hdr
            match_type, format_code = self.media.get_best_video_format()
            print((resolution, vcodec, acodec, prefer_60fps, prefer_hdr), match_type, format_code)
            #self.assertEqual(match_type, expeceted_match_type)
            #self.assertEqual(format_code, expected_format_code)
