import json
import logging
from pathlib import Path
from unittest.mock import patch

from django.test import Client, TestCase, override_settings
from django_huey import DJANGO_HUEY, get_queue

from sync import direct_download as dd
from sync.models import DirectDownloadJob


VID_A = 'aaaaaaaaaaa'
VID_B = 'bbbbbbbbbbb'
VID_C = 'ccccccccccc'


class DirectDownloadAPITestCase(TestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        for qn in DJANGO_HUEY.get('queues', dict()):
            q = get_queue(qn)
            q.immediate_use_memory = True
            q.immediate = False

    def setUp(self):
        logging.disable(logging.CRITICAL)
        self.client = Client()

    def _post(self, payload):
        return self.client.post(
            '/api/downloads',
            data=json.dumps(payload),
            content_type='application/json',
        )

    # -- POST /api/downloads --------------------------------------------------

    def test_create_audio_job(self):
        resp = self._post({
            'audio': True, 'acodec': 'mp4a',
            'playlists': [{'title': 'Lib', 'video_ids': [VID_A]}],
        })
        self.assertEqual(resp.status_code, 201, resp.content)
        job = DirectDownloadJob.objects.get(pk=resp.json()['id'])
        self.assertTrue(job.audio)
        self.assertEqual(job.acodec, 'mp4a')
        self.assertTrue(job.as_status_dict()['audio'])

    def test_create_job_defaults_to_video(self):
        resp = self._post({'playlists': [{'title': 'V', 'video_ids': [VID_A]}]})
        job = DirectDownloadJob.objects.get(pk=resp.json()['id'])
        self.assertFalse(job.audio)
        self.assertEqual(job.acodec, 'opus')

    def test_create_job(self):
        resp = self._post({'playlists': [
            {'title': 'My List', 'playlist_id': 'PL1', 'video_ids': [VID_A, VID_B]},
            {'title': 'Other', 'video_ids': [VID_C]},
        ]})
        self.assertEqual(resp.status_code, 201, resp.content)
        body = resp.json()
        self.assertEqual(body['total'], 3)
        self.assertEqual(body['playlists'], 2)

        job = DirectDownloadJob.objects.get(pk=body['id'])
        self.assertEqual(job.status, DirectDownloadJob.Status.RUNNING)
        self.assertEqual(job.total, 3)
        self.assertEqual(job.playlists[0]['directory'], 'my-list')
        self.assertEqual(job.playlists[0]['video_ids'], [VID_A, VID_B])

    def test_directory_dedupe_and_traversal_guard(self):
        resp = self._post({'playlists': [
            {'title': 'Garten', 'video_ids': [VID_A]},
            {'title': 'Garten', 'video_ids': [VID_B]},
        ]})
        self.assertEqual(resp.status_code, 201)
        job = DirectDownloadJob.objects.get(pk=resp.json()['id'])
        self.assertEqual(
            [p['directory'] for p in job.playlists], ['garten', 'garten-2'],
        )

        resp = self._post({'playlists': [
            {'title': 'x', 'directory': '../etc', 'video_ids': [VID_A]},
        ]})
        self.assertEqual(resp.status_code, 400)

    def test_rejects_invalid_ids_and_empty(self):
        resp = self._post({'playlists': [{'title': 'x', 'video_ids': ['short', 123]}]})
        self.assertEqual(resp.status_code, 400)
        resp = self._post({'playlists': []})
        self.assertEqual(resp.status_code, 400)

    def test_only_one_running_job(self):
        r1 = self._post({'playlists': [{'title': 'a', 'video_ids': [VID_A]}]})
        self.assertEqual(r1.status_code, 201)
        r2 = self._post({'playlists': [{'title': 'b', 'video_ids': [VID_B]}]})
        self.assertEqual(r2.status_code, 409)

    def test_too_many_videos(self):
        from sync.views import api as api_mod
        with patch.object(api_mod, 'MAX_DIRECT_VIDEOS', 2):
            resp = self._post({'playlists': [
                {'title': 'a', 'video_ids': [VID_A, VID_B, VID_C]},
            ]})
        self.assertEqual(resp.status_code, 400)

    # -- GET / stop --------------------------------------------------------

    def test_status_and_stop(self):
        jid = self._post({'playlists': [{'title': 'a', 'video_ids': [VID_A]}]}).json()['id']

        resp = self.client.get(f'/api/downloads/{jid}')
        self.assertEqual(resp.status_code, 200)
        s = resp.json()
        self.assertEqual(s['overall']['total'], 1)
        self.assertEqual(s['phase'], 'running')

        resp = self.client.post(
            f'/api/downloads/{jid}', data=json.dumps({'stop': True}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(DirectDownloadJob.objects.get(pk=jid).stop_requested)

        self.assertEqual(self.client.get('/api/downloads/deadbeef-dead-dead-dead-deaddeafbeef').status_code, 404)

    def test_list(self):
        self._post({'playlists': [{'title': 'a', 'video_ids': [VID_A]}]})
        resp = self.client.get('/api/downloads')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['count'], 1)


class DirectDownloadEngineTestCase(TestCase):

    def setUp(self):
        logging.disable(logging.CRITICAL)

    @patch('sync.direct_download.interruptible_sleep', lambda *_: None)
    @patch('sync.direct_download.time.sleep', lambda *_: None)
    @patch('sync.direct_download.patch_info_json')
    @patch('sync.direct_download.download_one')
    def test_run_job_advances_and_finishes(self, m_dl, m_patch):
        m_dl.return_value = 'ok'
        job = DirectDownloadJob.objects.create(
            playlists=[
                {'title': 'A', 'playlist_id': 'PLA', 'directory': 'a', 'video_ids': [VID_A, VID_B]},
                {'title': 'B', 'playlist_id': 'PLB', 'directory': 'b', 'video_ids': [VID_C]},
            ],
            total=3,
            status=DirectDownloadJob.Status.RUNNING,
        )
        with override_settings(DOWNLOAD_ROOT=self._tmp()):
            dd.run_job(job)
        job.refresh_from_db()
        self.assertEqual(job.status, DirectDownloadJob.Status.DONE)
        self.assertEqual(job.completed, 3)
        self.assertEqual(job.failed, 0)
        self.assertEqual(job.playlists_done, 2)
        self.assertEqual(m_dl.call_count, 3)
        self.assertEqual(m_patch.call_count, 2)

    @patch('sync.direct_download.interruptible_sleep', lambda *_: None)
    @patch('sync.direct_download.time.sleep', lambda *_: None)
    @patch('sync.direct_download.patch_info_json')
    @patch('sync.direct_download.download_one')
    def test_run_job_audio_uses_audio_dir(self, m_dl, m_patch):
        m_dl.return_value = 'ok'
        job = DirectDownloadJob.objects.create(
            playlists=[{'title': 'Lib', 'directory': 'lib', 'video_ids': [VID_A]}],
            total=1, audio=True, acodec='opus',
            status=DirectDownloadJob.Status.RUNNING,
        )
        with override_settings(DOWNLOAD_ROOT=self._tmp()):
            dd.run_job(job)
        self.assertEqual(m_dl.call_count, 1)
        _args, kwargs = m_dl.call_args
        self.assertTrue(kwargs['audio'])
        self.assertEqual(kwargs['acodec'], 'opus')
        self.assertIn('/audio/lib', str(m_dl.call_args[0][1]).replace('\\', '/'))

    @patch('sync.direct_download.interruptible_sleep', lambda *_: None)
    @patch('sync.direct_download.time.sleep', lambda *_: None)
    @patch('sync.direct_download.patch_info_json')
    @patch('sync.direct_download.download_one')
    def test_stop_between_videos(self, m_dl, m_patch):
        m_dl.return_value = 'ok'
        job = DirectDownloadJob.objects.create(
            playlists=[{'title': 'A', 'directory': 'a', 'video_ids': [VID_A, VID_B, VID_C]}],
            total=3, status=DirectDownloadJob.Status.RUNNING,
        )

        def stopper(*args, **kwargs):
            DirectDownloadJob.objects.filter(pk=job.pk).update(stop_requested=True)
            return 'ok'

        m_dl.side_effect = stopper
        with override_settings(DOWNLOAD_ROOT=self._tmp()):
            dd.run_job(job)
        job.refresh_from_db()
        self.assertEqual(job.status, DirectDownloadJob.Status.STOPPED)
        self.assertLess(job.completed, 3)

    @patch('sync.direct_download.interruptible_sleep', lambda *_: None)
    @patch('sync.direct_download.time.sleep', lambda *_: None)
    @patch('sync.direct_download.patch_info_json')
    @patch('sync.direct_download.download_one')
    def test_resume_from_cursor(self, m_dl, m_patch):
        m_dl.return_value = 'ok'
        job = DirectDownloadJob.objects.create(
            playlists=[{'title': 'A', 'directory': 'a', 'video_ids': [VID_A, VID_B, VID_C]}],
            total=3, completed=2, cursor_playlist=0, cursor_video=2,
            status=DirectDownloadJob.Status.RUNNING,
        )
        with override_settings(DOWNLOAD_ROOT=self._tmp()):
            dd.run_job(job)
        job.refresh_from_db()
        self.assertEqual(job.status, DirectDownloadJob.Status.DONE)
        self.assertEqual(m_dl.call_count, 1)  # only the last video
        self.assertEqual(job.completed, 3)

    @patch('sync.direct_download.time.sleep', lambda *_: None)
    @patch('sync.direct_download.patch_info_json')
    @patch('sync.direct_download.download_one')
    def test_backoff_on_consecutive_blocks(self, m_dl, m_patch):
        m_dl.side_effect = ['blocked', 'blocked', 'blocked', 'blocked', 'ok']
        pauses = []
        job = DirectDownloadJob.objects.create(
            playlists=[{'title': 'A', 'directory': 'a',
                        'video_ids': [VID_A, VID_B, VID_C, 'ddddddddddd', 'eeeeeeeeeee']}],
            total=5, status=DirectDownloadJob.Status.RUNNING,
        )
        with patch('sync.direct_download.interruptible_sleep', lambda s, j: pauses.append(s)), \
             override_settings(DOWNLOAD_ROOT=self._tmp()):
            dd.run_job(job)
        job.refresh_from_db()
        self.assertEqual(job.status, DirectDownloadJob.Status.DONE)
        self.assertEqual(job.failed, 4)
        self.assertEqual(job.completed, 1)
        self.assertGreaterEqual(max(pauses), 300)   # backoff kicked in

    def test_already_have(self):
        d = Path(self._tmp())
        self.assertFalse(dd.already_have(d, VID_A))
        (d / f'2024-01-01_Chan_Some Title_{VID_A}_h264.mkv').write_text('x')
        (d / f'Uploader - Title [{VID_B}].mp4').write_text('x')
        (d / f'{VID_C}.info.json').write_text('{}')  # sidecar only -> not "have"
        self.assertTrue(dd.already_have(d, VID_A))
        self.assertTrue(dd.already_have(d, VID_B))
        self.assertFalse(dd.already_have(d, VID_C))

    def test_patch_info_json(self):
        d = Path(self._tmp()) / 'video' / 'x'
        d.mkdir(parents=True)
        (d / 'one.info.json').write_text(json.dumps({'id': VID_A, 'title': 'One'}))
        (d / 'two.info.json').write_text(json.dumps({'id': VID_B, 'playlist_id': 'existing'}))
        dd.patch_info_json(d, 'PLZ', 'My Playlist')
        one = json.loads((d / 'one.info.json').read_text())
        two = json.loads((d / 'two.info.json').read_text())
        self.assertEqual(one['playlist_id'], 'PLZ')
        self.assertEqual(one['playlist_title'], 'My Playlist')
        self.assertEqual(two['playlist_id'], 'existing')  # untouched

    def _tmp(self):
        import tempfile
        d = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__('shutil').rmtree(d, ignore_errors=True))
        return d
