import base64
import json
import logging
import tempfile
from pathlib import Path

from django.test import Client, TestCase, override_settings
from django_huey import DJANGO_HUEY, get_queue

from sync.models import Source

NETSCAPE = (
    '# Netscape HTTP Cookie File\n'
    '.youtube.com\tTRUE\t/\tFALSE\t0\tPREF\tabc\n'
)


def _b64(user, password):
    raw = f'{user}:{password}'.encode('utf-8')
    return 'Basic ' + base64.b64encode(raw).decode('ascii')


class SourceAPITestCase(TestCase):

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

    def _post(self, payload, **extra):
        return self.client.post(
            '/api/sources',
            data=json.dumps(payload),
            content_type='application/json',
            **extra,
        )

    # -- auth ---------------------------------------------------------

    @override_settings(BASICAUTH_DISABLE=False,
                       BASICAUTH_USERS={'apiuser': 'apipass'})
    def test_requires_basic_auth_when_enabled(self):
        resp = self.client.get('/api/sources')
        self.assertEqual(resp.status_code, 401)

        resp = self.client.get('/api/sources',
                               HTTP_AUTHORIZATION=_b64('apiuser', 'apipass'))
        self.assertEqual(resp.status_code, 200)

    # -- POST -------------------------------------------------------

    def test_post_happy_path(self):
        resp = self._post({
            'activate': False,
            'sources': [
                {'url': 'https://www.youtube.com/playlist?list=PLhappy1', 'name': 'One'},
                {'key': 'PLhappy2', 'source_type': 'p', 'name': 'Two'},
            ],
        })
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body['created'], 2)
        self.assertEqual(body['errors'], 0)
        self.assertEqual(Source.objects.filter(key__in=('PLhappy1', 'PLhappy2')).count(), 2)

    def test_post_partial_success_still_200(self):
        Source.objects.create(key='PLtaken', name='Occupied', directory='occupied')
        resp = self._post({'sources': [
            {'key': 'PLok', 'source_type': 'p', 'name': 'Fine'},
            {'key': 'PLclash', 'source_type': 'p', 'name': 'Occupied'},
        ]})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body['created'], 1)
        self.assertEqual(body['errors'], 1)
        statuses = sorted(r['status'] for r in body['results'])
        self.assertEqual(statuses, ['created', 'error'])

    def test_post_bare_array_body(self):
        resp = self._post([
            {'key': 'PLbare', 'source_type': 'p', 'name': 'Bare'},
        ])
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['created'], 1)

    def test_post_malformed_json(self):
        resp = self.client.post('/api/sources', data='{not json',
                                content_type='application/json')
        self.assertEqual(resp.status_code, 400)

    def test_post_missing_sources(self):
        resp = self._post({'activate': True})
        self.assertEqual(resp.status_code, 400)

    def test_post_empty_sources(self):
        resp = self._post({'sources': []})
        self.assertEqual(resp.status_code, 400)

    def test_post_too_many(self):
        resp = self._post({'sources': [
            {'key': f'PL{n:04d}', 'source_type': 'p', 'name': f'S{n}'}
            for n in range(501)
        ]})
        self.assertEqual(resp.status_code, 400)

    @override_settings(DATA_UPLOAD_MAX_MEMORY_SIZE=16)
    def test_post_payload_too_large(self):
        resp = self._post({'sources': [
            {'key': 'PLbig', 'source_type': 'p', 'name': 'A rather long name here'},
        ]})
        self.assertEqual(resp.status_code, 413)

    def test_post_dry_run(self):
        resp = self._post({'dry_run': True, 'sources': [
            {'key': 'PLdry', 'source_type': 'p', 'name': 'Dry'},
        ]})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['dry_run'])
        self.assertFalse(Source.objects.filter(key='PLdry').exists())

    # -- GET ------------------------------------------------------

    def _seed(self):
        Source.objects.create(key='PLp1', name='P1', directory='p1',
                              source_type='p', index_schedule=86400,
                              download_media=True)
        Source.objects.create(key='PLp2', name='P2', directory='p2',
                              source_type='p', index_schedule=0,
                              download_media=False, index_videos=False)
        Source.objects.create(key='c1', name='C1', directory='c1',
                              source_type='c', has_failed=True)

    def test_get_list_and_filters(self):
        self._seed()
        body = self.client.get('/api/sources').json()
        self.assertEqual(body['count'], 3)

        body = self.client.get('/api/sources?type=p').json()
        self.assertEqual(body['count'], 2)

        body = self.client.get('/api/sources?type=c').json()
        self.assertEqual(body['count'], 1)
        self.assertTrue(body['results'][0]['has_failed'])

        body = self.client.get('/api/sources?active=1').json()
        keys = {r['key'] for r in body['results']}
        self.assertIn('PLp1', keys)
        self.assertNotIn('PLp2', keys)

        body = self.client.get('/api/sources?key=PLp2').json()
        self.assertEqual(body['count'], 1)
        self.assertEqual(body['results'][0]['key'], 'PLp2')

    def test_get_paging_count_is_unpaged(self):
        self._seed()
        body = self.client.get('/api/sources?limit=1&offset=1').json()
        self.assertEqual(body['count'], 3)
        self.assertEqual(len(body['results']), 1)
        self.assertEqual(body['limit'], 1)
        self.assertEqual(body['offset'], 1)

    def test_get_invalid_param(self):
        self.assertEqual(self.client.get('/api/sources?type=zzz').status_code, 400)
        self.assertEqual(self.client.get('/api/sources?limit=0').status_code, 400)
        self.assertEqual(self.client.get('/api/sources?active=maybe').status_code, 400)

    # -- DELETE --------------------------------------------------

    def test_delete_unknown_uuid(self):
        resp = self.client.delete('/api/sources/00000000-0000-0000-0000-000000000000')
        self.assertEqual(resp.status_code, 404)

    def test_delete_known_uuid(self):
        source = Source.objects.create(key='PLdel', name='Del', directory='del')
        resp = self.client.delete(f'/api/sources/{source.uuid}')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['deleted'], str(source.uuid))
        self.assertFalse(Source.objects.filter(pk=source.uuid).exists())


class CookiesAPITestCase(TestCase):

    def setUp(self):
        logging.disable(logging.CRITICAL)
        self.client = Client()
        self._tmp = tempfile.TemporaryDirectory()
        self.cookie_file = Path(self._tmp.name) / 'cookies.txt'
        self._ctx = override_settings(COOKIES_FILE=self.cookie_file)
        self._ctx.enable()

    def tearDown(self):
        self._ctx.disable()
        self._tmp.cleanup()

    def test_get_when_absent(self):
        body = self.client.get('/api/cookies').json()
        self.assertEqual(body, {'has_cookies': False, 'size': 0})

    def test_post_sets_file_and_never_returns_content(self):
        resp = self.client.post('/api/cookies',
                                data=json.dumps({'text': NETSCAPE}),
                                content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body['has_cookies'])
        self.assertGreater(body['size'], 0)
        self.assertNotIn('text', body)
        self.assertEqual(self.cookie_file.read_text(), NETSCAPE)

    def test_post_raw_body(self):
        resp = self.client.post('/api/cookies', data=NETSCAPE,
                                content_type='text/plain')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(self.cookie_file.is_file())

    def test_post_empty_deletes(self):
        self.cookie_file.write_text(NETSCAPE)
        resp = self.client.post('/api/cookies',
                                data=json.dumps({'text': '  '}),
                                content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(self.cookie_file.exists())
        self.assertFalse(resp.json()['has_cookies'])

    def test_post_garbage_rejected(self):
        resp = self.client.post('/api/cookies',
                                data=json.dumps({'text': 'not a cookie file'}),
                                content_type='application/json')
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(self.cookie_file.exists())
