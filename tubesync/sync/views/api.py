'''
    Minimal JSON HTTP API for bulk source management.

    Plain Django views + JsonResponse - DRF is deliberately not a dependency.
    Auth is handled globally by common.middleware.BasicAuthMiddleware; these
    views do no auth of their own. CSRF is exempted because there is no session
    login on these machine-to-machine endpoints.
'''

import json

from django.core.exceptions import RequestDataTooBig, ValidationError
from django.db.models import Count
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from common.json_encoder import JSONEncoder

from ..choices import YouTube_SourceType
from ..models import Source
from ..source_import import ImportReport, import_sources


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
