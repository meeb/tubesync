import logging
from datetime import datetime
from urllib.parse import urlsplit
from django.conf import settings
from django.test import TestCase, Client
from django.utils import timezone
from django_huey import DJANGO_HUEY, get_queue
from common.models import TaskHistory
from sync.models import Source, Media
from sync.tasks import (
    check_source_directory_exists,
    get_media_download_task, get_media_thumbnail_task,
)
from sync.choices import (
    Val, Fallback, FilterSeconds, IndexSchedule, SourceResolution,
    TaskQueue, YouTube_AudioCodec, YouTube_VideoCodec,
    YouTube_SourceType,
)

class FrontEndTestCase(TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Use immediate mode to execute tasks in this process
        for qn in DJANGO_HUEY.get('queues', dict()):
            q = get_queue(qn)
            # Set the storage variable before using the property.
            q.immediate_use_memory = True
            q.immediate = False

    def setUp(self):
        # Disable general logging for test case
        logging.disable(logging.CRITICAL)

    def test_dashboard(self):
        c = Client()
        response = c.get('/')
        self.assertEqual(response.status_code, 200)

    def test_validate_source(self):
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
                'invalid_reserved_paths': (
                    'https://www.youtube.com/watch?v=OkMadb8cpIw',
                    'https://www.youtube.com/watch',
                    'https://www.youtube.com/shorts',
                    'https://www.youtube.com/live',
                    'https://www.youtube.com/feed',
                    'https://www.youtube.com/trending',
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
                    'https://www.youtube.com/test/invalid',
                ),
            }
        }
        c = Client()
        response = c.get('/source-validate')
        self.assertEqual(response.status_code, 200)
        for (source_type, tests) in test_sources.items():
            for test, urls in tests.items():
                for url in urls:
                    data = {'source_url': url}
                    response = c.post('/source-validate', data)
                    if test == 'valid':
                        # Valid source tests should bounce to /source-add
                        self.assertEqual(response.status_code, 302)
                        url_parts = urlsplit(response.url)
                        self.assertEqual(url_parts.path, '/source-add')
                    else:
                        # Invalid source tests should reload the page with an error
                        self.assertEqual(response.status_code, 200)
                        self.assertIn('<ul class="errorlist"',
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
        #logging.disable(logging.NOTSET)
        # Sources overview page
        c = Client()
        response = c.get('/sources')
        self.assertEqual(response.status_code, 200)
        # Add as source form
        response = c.get('/source-add')
        self.assertEqual(response.status_code, 200)
        # Create a new source
        data_categories = ('sponsor', 'preview', 'preview', 'sponsor',)
        expected_categories = ['sponsor', 'preview']
        data = {
            'source_type': 'c',
            'key': 'testkey',
            'name': 'testname',
            'directory': 'testdirectory',
            'media_format': settings.MEDIA_FORMATSTR_DEFAULT,
            'download_cap': 0,
            'filter_text': '.*',
            'filter_seconds_min': bool(FilterSeconds.MIN),
            'index_schedule': 3600,
            'download_media': False,
            'index_videos': True,
            'delete_old_media': False,
            'days_to_keep': 14,
            'source_resolution': '1080p',
            'source_vcodec': 'VP9',
            'source_acodec': 'OPUS',
            'prefer_60fps': False,
            'prefer_hdr': False,
            'fallback': 'f',
            'sponsorblock_categories': data_categories,
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
        # Check that the SponsorBlock categories were saved
        self.assertEqual(source.sponsorblock_categories.selected_choices,
                         expected_categories)
        # Run the check_source_directory_exists task
        check_source_directory_exists.call_local(source_uuid)
        # Check the source is now on the source overview page
        response = c.get('/sources')
        self.assertEqual(response.status_code, 200)
        self.assertIn(source_uuid, response.content.decode())
        # Check the source detail page loads
        response = c.get(f'/source/{source_uuid}')
        self.assertEqual(response.status_code, 200)
        # Check a task was created to index the media for the new source
        index_task_qs = TaskHistory.objects.filter(
            name='sync.tasks.index_source',
            task_params__0__0=source_uuid,
        ).order_by('end_at')
        self.assertTrue(index_task_qs)
        task = index_task_qs.last()
        self.assertEqual(task.queue, get_queue(Val(TaskQueue.LIMIT)).name)
        # save and refresh the Source
        source.refresh_from_db()
        source.sponsorblock_categories.selected_choices.append('sponsor')
        source.save()
        source.refresh_from_db()
        # Check that the SponsorBlock categories remain saved
        self.assertEqual(source.sponsorblock_categories.selected_choices,
                         expected_categories)
        # Update the source key
        data = {
            'source_type': Val(YouTube_SourceType.CHANNEL),
            'key': 'updatedkey',  # changed
            'name': 'testname',
            'directory': 'testdirectory',
            'media_format': settings.MEDIA_FORMATSTR_DEFAULT,
            'download_cap': 0,
            'filter_text': '.*',
            'filter_seconds_min': bool(FilterSeconds.MIN),
            'index_schedule': Val(IndexSchedule.EVERY_HOUR),
            'delete_old_media': False,
            'days_to_keep': 14,
            'source_resolution': Val(SourceResolution.VIDEO_1080P),
            'source_vcodec': Val(YouTube_VideoCodec.VP9),
            'source_acodec': Val(YouTube_AudioCodec.OPUS),
            'prefer_60fps': False,
            'prefer_hdr': False,
            'fallback': Val(Fallback.FAIL),
            'sponsorblock_categories': data_categories,
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
        # Check that the SponsorBlock categories remain saved
        source.refresh_from_db()
        self.assertEqual(source.sponsorblock_categories.selected_choices,
                         expected_categories)
        # Update the source index schedule which should recreate the scheduled task
        data = {
            'source_type': Val(YouTube_SourceType.CHANNEL),
            'key': 'updatedkey',
            'name': 'testname',
            'directory': 'testdirectory',
            'media_format': settings.MEDIA_FORMATSTR_DEFAULT,
            'download_cap': 0,
            'filter_text': '.*',
            'filter_seconds_min': bool(FilterSeconds.MIN),
            'index_schedule': Val(IndexSchedule.EVERY_2_HOURS),  # changed
            'delete_old_media': False,
            'days_to_keep': 14,
            'source_resolution': Val(SourceResolution.VIDEO_1080P),
            'source_vcodec': Val(YouTube_VideoCodec.VP9),
            'source_acodec': Val(YouTube_AudioCodec.OPUS),
            'prefer_60fps': False,
            'prefer_hdr': False,
            'fallback': Val(Fallback.FAIL),
            'sponsorblock_categories': data_categories,
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
        # Check that the SponsorBlock categories remain saved
        self.assertEqual(source.sponsorblock_categories.selected_choices,
                         expected_categories)
        # Check a new task has been created by seeing if the pk has changed
        new_task = index_task_qs.last()
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

    def test_media(self):
        # Media overview page
        c = Client()
        response = c.get('/media')
        self.assertEqual(response.status_code, 200)
        # Add a test source
        test_source = Source.objects.create(
            source_type=Val(YouTube_SourceType.CHANNEL),
            key='testkey',
            name='testname',
            directory='testdirectory',
            index_schedule=Val(IndexSchedule.EVERY_HOUR),
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
        from .fixtures import all_test_metadata
        test_minimal_metadata = all_test_metadata['minimal']
        before_dt = timezone.now()
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
        # simulate the tasks consumer signals having already run
        now_dt = timezone.now()
        TaskHistory.objects.filter(
            name__startswith='sync.tasks.download_media_',
        ).update(
            scheduled_at=before_dt,
            start_at=now_dt,
            end_at=now_dt,
        )
        # Check the tasks to fetch the media thumbnails have been scheduled
        found_download_task1 = get_media_download_task(test_media1_pk)
        found_download_task2 = get_media_download_task(test_media2_pk)
        found_download_task3 = get_media_download_task(test_media3_pk)
        found_thumbnail_task1 = get_media_thumbnail_task(test_media1_pk)
        found_thumbnail_task2 = get_media_thumbnail_task(test_media2_pk)
        found_thumbnail_task3 = get_media_thumbnail_task(test_media3_pk)
        self.assertTrue(found_download_task1)
        self.assertTrue(found_download_task2)
        self.assertTrue(found_download_task3)
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
        # simulate the tasks consumer signals having already run
        TaskHistory.objects.filter(
            name__startswith='sync.tasks.download_media_',
        ).update(end_at=timezone.now())
        # Confirm any tasks have been deleted
        found_download_task1 = get_media_download_task(test_media1_pk)
        found_download_task2 = get_media_download_task(test_media2_pk)
        found_download_task3 = get_media_download_task(test_media3_pk)
        found_thumbnail_task1 = get_media_thumbnail_task(test_media1_pk)
        found_thumbnail_task2 = get_media_thumbnail_task(test_media2_pk)
        found_thumbnail_task3 = get_media_thumbnail_task(test_media3_pk)
        self.assertFalse(found_download_task1)
        self.assertFalse(found_download_task2)
        self.assertFalse(found_download_task3)
        self.assertFalse(found_thumbnail_task1)
        self.assertFalse(found_thumbnail_task2)
        self.assertFalse(found_thumbnail_task3)

    def test_tasks(self):
        # Tasks overview page
        c = Client()
        response = c.get('/tasks')
        self.assertEqual(response.status_code, 200)
        # Completed tasks overview page
        response = c.get('/tasks-completed')
        self.assertEqual(response.status_code, 200)

    def test_mediaservers(self):
        # Media servers overview page
        c = Client()
        response = c.get('/mediaservers')
        self.assertEqual(response.status_code, 200)


