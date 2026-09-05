'''
    Minimal JSON HTTP API for bulk source management.

    Plain Django views + JsonResponse - DRF is deliberately not a dependency.
    Auth is handled globally by common.middleware.BasicAuthMiddleware; these
    views do no auth of their own. CSRF is exempted because there is no session
    login on these machine-to-machine endpoints.
'''

import json
import re

from django.core.exceptions import RequestDataTooBig, ValidationError
from django.db.models import Count
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from common.json_encoder import JSONEncoder
from common.models import TaskHistory

from ..choices import Val, YouTube_SourceType
from ..models import DirectDownloadJob, Source
from ..source_import import ImportReport, import_sources
from .. import direct_download as dd


def _json_response(data, status=200):
    return JsonResponse(data, encoder=JSONEncoder, status=status)


def _error(message, status=400):
    return _json_response({'error': str(message)}, status=status)


def _parse_bool_param(raw):
    v = str(raw).strip().lower()
    if v in ('1', 'true', 'yes', 'on'):
        return True
    if v in ('0', 'false', 'no', 'off'):
        return False
    raise ValueError(f'expected a boolean (1/0), got {raw!r}')


class _BadRequest(Exception):
    pass


class _PayloadTooBig(Exception):
    pass


def _read_json_body(request):
    try:
        body = request.body
    except RequestDataTooBig as e:
        raise _PayloadTooBig() from e
    if not body:
        raise _BadRequest('empty request body')
    try:
        return json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise _BadRequest(f'invalid JSON: {e}') from e


@method_decorator(csrf_exempt, name='dispatch')
class SourceListCreateAPIView(View):

    http_method_names = ['get', 'post', 'head', 'options']

    # ---- GET /api/sources -------------------------------------------------

    def get(self, request):
        qs = Source.objects.all().annotate(media_count=Count('media_source'))

        source_type = request.GET.get('type')
        if source_type is not None:
            if source_type not in YouTube_SourceType.values:
                return _error(
                    f"invalid 'type' {source_type!r}, must be one of "
                    f'{sorted(YouTube_SourceType.values)}'
                )
            qs = qs.filter(source_type=source_type)

        key = request.GET.get('key')
        if key:
            qs = qs.filter(key=key.strip())

        if 'has_failed' in request.GET:
            try:
                qs = qs.filter(has_failed=_parse_bool_param(request.GET['has_failed']))
            except ValueError as e:
                return _error(f"invalid 'has_failed': {e}")

        active_param = None
        if 'active' in request.GET:
            try:
                active_param = _parse_bool_param(request.GET['active'])
            except ValueError as e:
                return _error(f"invalid 'active': {e}")

        try:
            limit = int(request.GET.get('limit', 100))
            offset = int(request.GET.get('offset', 0))
        except (TypeError, ValueError):
            return _error("'limit' and 'offset' must be integers")
        if limit < 1 or limit > 1000:
            return _error("'limit' must be between 1 and 1000")
        if offset < 0:
            return _error("'offset' must be >= 0")

        qs = qs.order_by('name')

        # Source.is_active is a Python property; evaluate it in Python so the
        # exact same rule is used everywhere.
        rows = list(qs)
        if active_param is not None:
            rows = [s for s in rows if bool(s.is_active) == active_param]
        count = len(rows)

        page = rows[offset:offset + limit]
        return _json_response({
            'count': count,
            'limit': limit,
            'offset': offset,
            'results': [self._serialize(s) for s in page],
        })

    @staticmethod
    def _serialize(source):
        return {
            'uuid': str(source.uuid),
            'key': source.key,
            'name': source.name,
            'directory': source.directory,
            'source_type': source.source_type,
            'index_schedule': source.index_schedule,
            'download_media': source.download_media,
            'is_active': bool(source.is_active),
            'has_failed': source.has_failed,
            'last_crawl': source.last_crawl,
            'media_count': getattr(source, 'media_count', None),
        }

    # ---- POST /api/sources ----------------------------------------------

    def post(self, request):
        try:
            payload = _read_json_body(request)
        except _PayloadTooBig:
            return _error('payload too large, split into multiple requests', status=413)
        except _BadRequest as e:
            return _error(e)

        if isinstance(payload, list):
            payload = {'sources': payload}
        if not isinstance(payload, dict):
            return _error('request body must be a JSON object or array')

        sources = payload.get('sources')
        if not isinstance(sources, list) or not sources:
            return _error("'sources' must be a non-empty list")

        activate = payload.get('activate')
        if activate is not None and not isinstance(activate, bool):
            return _error("'activate' must be a boolean")
        defer_indexing = bool(payload.get('defer_indexing', False))
        dry_run = bool(payload.get('dry_run', False))

        try:
            report: ImportReport = import_sources(
                sources,
                activate=activate,
                defer_indexing=defer_indexing,
                dry_run=dry_run,
            )
        except ValidationError as e:
            return _error('; '.join(e.messages))

        return _json_response(report.as_dict(), status=200)


@method_decorator(csrf_exempt, name='dispatch')
class SourceDetailAPIView(View):

    http_method_names = ['delete', 'head', 'options']

    def delete(self, request, pk):
        try:
            source = Source.objects.get(pk=pk)
        except Source.DoesNotExist:
            return _error('no source with that uuid', status=404)
        name = source.name
        source.delete()
        return _json_response({'deleted': str(pk), 'name': name}, status=200)


# ---- Direct-download jobs (sync/direct_download.py) --------------------------

_VIDEO_ID_RE = re.compile(r'^[A-Za-z0-9_-]{11}$')
MAX_DIRECT_VIDEOS = 25_000


def _clean_directory(raw, title, taken):
    d = str(raw).strip() if raw else ''
    if d:
        if d.startswith(('/', '\\')) or '..' in d.replace('\\', '/').split('/') or '/' in d:
            raise ValidationError(_("invalid 'directory' %(d)r") % {'d': d})
        d = dd.safe_directory(d)
    else:
        d = dd.safe_directory(title)
    base, n = d, 2
    while d in taken:
        d = f'{base}-{n}'
        n += 1
    taken.add(d)
    return d


@method_decorator(csrf_exempt, name='dispatch')
class DownloadJobListCreateAPIView(View):

    http_method_names = ['get', 'post', 'head', 'options']

    def get(self, request):
        try:
            limit = int(request.GET.get('limit', 20))
        except (TypeError, ValueError):
            return _error("'limit' must be an integer")
        limit = max(1, min(limit, 200))
        rows = DirectDownloadJob.objects.all()[:limit]
        return _json_response({
            'count': DirectDownloadJob.objects.count(),
            'results': [{
                'id': str(j.uuid),
                'status': j.status,
                'completed': j.completed,
                'failed': j.failed,
                'total': j.total,
                'created_at': j.created_at,
            } for j in rows],
        })

    def post(self, request):
        try:
            payload = _read_json_body(request)
        except _PayloadTooBig:
            return _error('payload too large, split into multiple requests', status=413)
        except _BadRequest as e:
            return _error(e)
        if not isinstance(payload, dict):
            return _error('request body must be a JSON object')

        raw_playlists = payload.get('playlists')
        if not isinstance(raw_playlists, list) or not raw_playlists:
            return _error("'playlists' must be a non-empty list")

        resolution = str(payload.get('resolution') or '1080p')

        taken = set()
        playlists = []
        total = 0
        try:
            for entry in raw_playlists:
                if not isinstance(entry, dict):
                    raise ValidationError(_('each playlist must be a JSON object'))
                title = str(entry.get('title') or '').strip()
                if not title:
                    raise ValidationError(_("each playlist needs a 'title'"))
                ids = [
                    v for v in (entry.get('video_ids') or [])
                    if isinstance(v, str) and _VIDEO_ID_RE.match(v)
                ]
                if not ids:
                    raise ValidationError(
                        _("playlist %(t)r has no valid video_ids") % {'t': title}
                    )
                # de-dupe ids, keep order
                ids = list(dict.fromkeys(ids))
                directory = _clean_directory(entry.get('directory'), title, taken)
                total += len(ids)
                playlists.append({
                    'title': title[:200],
                    'playlist_id': (str(entry['playlist_id'])
                                    if entry.get('playlist_id') else None),
                    'directory': directory,
                    'video_ids': ids,
                })
        except ValidationError as e:
            return _error('; '.join(e.messages))

        if total > MAX_DIRECT_VIDEOS:
            return _error(
                f'too many videos ({total}), the limit is {MAX_DIRECT_VIDEOS}'
            )

        if DirectDownloadJob.objects.filter(
            status=Val(DirectDownloadJob.Status.RUNNING),
        ).exists():
            return _error('a direct-download job is already running', status=409)

        job = DirectDownloadJob.objects.create(
            playlists=playlists,
            resolution=resolution,
            total=total,
            status=Val(DirectDownloadJob.Status.RUNNING),
        )
        from ..tasks import run_direct_download_job
        TaskHistory.schedule(
            run_direct_download_job,
            str(job.uuid),
            delay=1,
            remove_duplicates=True,
            vn_fmt=_('Direct download job {}'),
            vn_args=(str(job.uuid),),
        )
        return _json_response(
            {'id': str(job.uuid), 'total': total, 'playlists': len(playlists)},
            status=201,
        )


@method_decorator(csrf_exempt, name='dispatch')
class DownloadJobDetailAPIView(View):

    http_method_names = ['get', 'post', 'head', 'options']

    def _get(self, pk):
        try:
            return DirectDownloadJob.objects.get(pk=pk)
        except DirectDownloadJob.DoesNotExist:
            return None

    def get(self, request, pk):
        job = self._get(pk)
        if job is None:
            return _error('no download job with that id', status=404)
        return _json_response(job.as_status_dict())

    def post(self, request, pk):
        job = self._get(pk)
        if job is None:
            return _error('no download job with that id', status=404)
        try:
            payload = _read_json_body(request)
        except (_BadRequest, _PayloadTooBig):
            payload = {}
        if isinstance(payload, dict) and payload.get('stop'):
            if job.status == Val(DirectDownloadJob.Status.RUNNING):
                DirectDownloadJob.objects.filter(pk=pk).update(stop_requested=True)
            return _json_response({'stopping': str(pk)})
        return _error("expected {'stop': true}")
