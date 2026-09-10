# Implementation spec: Source bulk-import (HTTP API + management command)

**Status:** ready to implement · **Target:** this fork (`masterdot/tubesync`) · **API version:** v1

All source paths below are relative to the Django project dir
`tubesync/` (i.e. `tubesync/sync/...`, `tubesync/common/...`,
`tubesync/tubesync/settings.py`). This document lives at
`docs/source-import-api-spec.md` in the repo root.

---

## 1. Goal & scope

Add a first-class way to **create many `Source` objects at once**, plus list and
delete them, without going through the HTML forms or `manage.py shell`.

Concrete driving use case: importing ~41 YouTube **playlists** (mostly
private/unlisted) as playlist sources in one shot, then letting TubeSync index +
download them normally.

**In scope (v1)**

- `POST /api/sources` — bulk create / upsert-by-key
- `GET /api/sources` — list (for client-side idempotency checks & dashboards)
- `DELETE /api/sources/<uuid>` — remove one source
- `manage.py import-sources` — local bulk import from JSON file / stdin
- A shared core module both entry points call.

**Out of scope (v1)** — do not build:

- Updating fields of an existing source (`PATCH`). List the field but return
  `exists` without touching it.
- Any Media-level endpoint.
- DRF / `rest_framework` — it is **not** in `INSTALLED_APPS` and must not be
  added. Use plain Django views + `JsonResponse`.
- New auth mechanism (see §6).
- New rate-limiting knobs (see §7).

---

## 2. Shared core — new module `sync/source_import.py`

Both the HTTP view and the management command MUST delegate to this module so
behaviour is identical.

### 2.1 `build_source_kwargs(item: dict) -> dict`

Turns one import item into validated `Source(**kwargs)` keyword arguments.
Raises `django.core.exceptions.ValidationError` with a human message on any
problem.

**Key / type resolution**

- If `item` has `url`: resolve it exactly like
  `sync/views/sources.py::ValidateSourceView.__init__` does — loop over
  `YouTube_SourceType.values`, call
  `sync.utils.validate_url(url, sync.choices.youtube_validation_urls[st])`
  inside `try/except ValidationError`, first match wins and yields
  `(key, source_type)`. Reuse `validate_url` and `youtube_validation_urls`
  verbatim; do not re-implement URL parsing.
- Else `item` must have both `key` and `source_type`
  (`source_type` one of `YouTube_SourceType.values` — `'c'`, `'i'`, `'p'`).
- Else → `ValidationError("provide either 'url' or 'key'+'source_type'")`.
- Normalise `key`: strip whitespace. For `source_type='c'` a leading `@` handle
  is fine (same as the form flow). No reachability check — an unreachable key
  surfaces later as `has_failed=True` on the index task, matching today's ORM
  behaviour.

**`name`**

- Use `item['name']` if given, else `item.get('title')` (playlist title from the
  caller), else `key`.
- Trim to `Source._meta.get_field('name').max_length` (100). `name` is
  `unique=True`.

**`directory`**

- Use `item['directory']` if given, else `django.utils.text.slugify(name)`
  (same call `Source.slugname` uses), trimmed to 100. `unique=True`.
- **Security:** validate the resolved path stays inside `settings.DOWNLOAD_ROOT`,
  the same guard `sync/views/sources.py::EditSourceMixin.form_valid` applies via
  `common.utils.mkdir_p`/`safe_join` on `settings.DOWNLOAD_ROOT / directory /
  '.virt'`. The ORM path skips this check, so `build_source_kwargs` MUST add it.
  Reject `..`, absolute paths, symlink escapes → `ValidationError`.

**Other fields — strict whitelist**

- Accept only concrete model fields of `Source`, **except** this deny-list:
  `uuid`, `created`, `last_crawl`, `has_failed`, and **`filter_text`**
  (`filter_text` is overloaded internally as a per-source delete marker holding
  a source PK — see `sync/signals.py::source_pre_delete`; accepting it from
  outside is a footgun). `filter_text_invert`, `filter_seconds`,
  `filter_seconds_min` ARE fine to accept.
- Build the allow-set dynamically:
  `{f.name for f in Source._meta.get_fields() if getattr(f, 'concrete', False)
    and not f.auto_created} - DENY`.
- Unknown keys in `item` (not in allow-set, not `url`/`title`) →
  `ValidationError(f"unknown field '{k}'")`.
- For every choices-backed field, validate the value is in that field's
  `choices` (`source_type`, `index_schedule`, `download_cap`,
  `source_resolution`, `source_vcodec`, `source_acodec`, `audio_track`,
  `fallback`). Invalid → `ValidationError` listing valid values.
- `sponsorblock_categories`: accept a list or comma string; validate against
  `SponsorBlock_Category` values plus `'all'` (the field is a
  `CommaSepChoiceField`, see `sync/fields.py`).
- `sub_langs`: leave the model's `RegexValidator` to do its job (call
  `full_clean` — see below).
- Booleans: accept real JSON booleans only; reject `"true"`/`1` strings with a
  clear message (keeps the contract tight).

**Return** the kwargs dict. Do **not** instantiate or save here.

### 2.2 `import_sources(items, *, activate=None, defer_indexing=False, dry_run=False) -> ImportReport`

```python
@dataclass
class ImportItemResult:
    status: str            # "created" | "exists" | "error"
    key: str | None = None
    uuid: str | None = None
    detail: str | None = None
    input: dict | None = None   # echoed back only on error

@dataclass
class ImportReport:
    created: int
    exists: int
    errors: int
    results: list[ImportItemResult]
    dry_run: bool
```

Algorithm:

1. If `len(items) > MAX_IMPORT_ITEMS` (module constant, `500`) →
   raise `ValidationError` (the HTTP layer turns this into `400`).
2. Wrap the whole thing in `transaction.atomic()`. If `dry_run`, register
   `transaction.set_rollback(True)` at the end (after collecting the report) so
   nothing persists but IntegrityErrors still surface per-item.
3. For each `item`:
   - `try:` `kwargs = build_source_kwargs(item)`
   - Apply `activate`:
     - `activate is False` → force `kwargs["index_schedule"] = 0` and
       `kwargs["download_media"] = False` (source created **inactive**;
       `Source.is_active` is then `False` and `source_post_save` will not
       schedule an index task).
     - `activate is True` → if the item did not set them, default
       `index_schedule` to `IndexSchedule.EVERY_24_HOURS` and
       `download_media=True` (they are already the model defaults, so this is
       mostly a no-op; still set explicitly for clarity).
     - `activate is None` → leave whatever `build_source_kwargs` produced
       (item values or model defaults).
   - Idempotency: `with transaction.atomic():` (savepoint)
     `obj, created = Source.objects.get_or_create(key=kwargs["key"],
       defaults={k: v for k, v in kwargs.items() if k != "key"})`
   - Before `get_or_create` actually saves a new row, run
     `Source(**kwargs).full_clean(exclude=["uuid"])` to trigger model
     validators; on `ValidationError` record `error` and continue.
   - `created` → `ImportItemResult("created", key, str(obj.uuid))`, `created += 1`
   - not `created` → `ImportItemResult("exists", key, str(obj.uuid))`,
     `exists += 1` — **do not modify** the existing row.
   - `except (ValidationError, IntegrityError) as e:` → savepoint rolls back,
     `ImportItemResult("error", detail=str(e), input=item)`, `errors += 1`.
     (`IntegrityError` happens when `name` or `directory` collides with a
     *different* existing source.)
4. Indexing:
   - Default (`defer_indexing=False`): `get_or_create` already called
     `Source.save()`, so `sync/signals.py::source_post_save` fired per new
     source → one `index_source` task (`delay=600`, queue `TaskQueue.LIMIT`,
     single worker → serial) + one `save_all_media_for_source`. Nothing extra to
     do. Fine for tens of sources.
   - `defer_indexing=True`: build the `Source` objects and `Source.objects
     .bulk_create(objs, batch_size=100)` (bypasses signals), then for each new
     pk call `check_source_directory_exists(str(pk))` and
     `TaskHistory.schedule(index_source, str(pk), delay=600 + i*30,
       vn_fmt=_('Index media from source "{}"'), vn_args=(name,))` with a
     staggered delay `i`. Also schedule one `save_all_media_for_source` per
     source. Use this only for very large imports; document the trade-off
     (no per-row `full_clean`, no `check_source_directory_exists` from the
     signal).

`TaskHistory.schedule` signature (from `common/models/tasks.py`):
`TaskHistory.schedule(task_wrapper, /, *args, vn_args=(), vn_fmt=None, **kwargs)`
where `**kwargs` are forwarded (`delay=`, `eta=`, `remove_duplicates=`).

---

## 3. HTTP API

New file `sync/views/api.py`, exported from `sync/views/__init__.py`, wired in
`sync/urls.py` (which has `app_name = 'sync'`, included at project root in
`tubesync/urls.py` with no prefix — so the paths below are literally
`/api/sources`).

```python
# sync/urls.py additions
path('api/sources', api.SourceListCreateAPIView.as_view(), name='api-sources'),
path('api/sources/<uuid:pk>', api.SourceDetailAPIView.as_view(), name='api-source'),
```

Both view classes:

```python
@method_decorator(csrf_exempt, name='dispatch')
class ...APIView(View):
    ...
```

`csrf_exempt` is required: `django.middleware.csrf.CsrfViewMiddleware` is active
(`tubesync/settings.py` `MIDDLEWARE`) and there is no session login on these
machine endpoints. Auth is handled globally by
`common.middleware.BasicAuthMiddleware` (see §6) — the views themselves do no
auth.

Responses: `django.http.JsonResponse(data, encoder=common.json_encoder.JSONEncoder,
status=...)`. For lists, `JsonResponse({...})` (not `safe=False` bare arrays).

### 3.1 `POST /api/sources`

Request body (JSON):

```jsonc
{
  "sources": [ { /* import item, see §5 */ }, ... ],   // required, non-empty
  "activate": true,          // optional bool; see import_sources() activate
  "defer_indexing": false,   // optional bool
  "dry_run": false           // optional bool
}
```

- Body may also be a bare JSON array → treat as `{"sources": <array>}`.
- Parse errors / `sources` missing or not a list / empty / `len > MAX_IMPORT_ITEMS`
  → `400 {"error": "..."}`.
- Request body larger than `DATA_UPLOAD_MAX_MEMORY_SIZE` → Django raises; return
  `413 {"error": "payload too large, split into multiple requests"}`.

Success — **always `200`**, even with per-item errors:

```jsonc
{
  "created": 39,
  "exists": 1,
  "errors": 1,
  "dry_run": false,
  "results": [
    {"status": "created", "key": "PL3hFtw-djaEbjYRb-GYJhXfNgpUiIpVBG",
     "uuid": "0c2e...-..."},
    {"status": "exists",  "key": "PL3hFtw-djaEbEeA1yezzNDDszlRetNNVe",
     "uuid": "7a11...-..."},
    {"status": "error",   "detail": "directory 'garten' already used by another source",
     "input": {"url": "https://www.youtube.com/playlist?list=PL...", "name": "Garten"}}
  ]
}
```

### 3.2 `GET /api/sources`

Query params (all optional):

| param | meaning |
|---|---|
| `type` | `c` / `i` / `p` — filter `source_type` |
| `active` | `1`/`0` — filter on `Source.is_active` (compute in Python or replicate its condition in the queryset) |
| `has_failed` | `1`/`0` |
| `key` | exact key lookup (handy for the client to check existence) |
| `limit` | default `100`, hard max `1000` |
| `offset` | default `0` |

Invalid param value → `400 {"error": "..."}`.

Response `200`:

```jsonc
{
  "count": 41,            // total matching, ignoring limit/offset
  "limit": 100,
  "offset": 0,
  "results": [
    {"uuid": "...", "key": "PL...", "name": "Häkelanleitungen",
     "directory": "haekelanleitungen", "source_type": "p",
     "index_schedule": 86400, "download_media": true,
     "is_active": true, "has_failed": false,
     "last_crawl": "2026-09-03T12:00:00Z", "media_count": 123}
  ]
}
```

`media_count` = `source.media_source.count()` or `Media.objects.filter(source=...)`
— use `annotate(media_count=Count('media_source'))` (check the related_name on
`Media.source` in `sync/models/media.py`; adjust accordingly).

### 3.3 `DELETE /api/sources/<uuid>`

- `404 {"error": "no source with that uuid"}` if not found.
- Else `source.delete()` (this fires `sync/signals.py::source_pre_delete` →
  `deactivate()` + schedules `delete_all_media_for_source`; unchanged
  behaviour). Return `200 {"deleted": "<uuid>", "name": "<name>"}`.
- No body, no bulk delete in v1.

---

## 4. Management command — `sync/management/commands/import-sources.py`

Model it on `sync/management/commands/youtube-add-subscriptions.py` and
`list-sources.py`.

```
python3 manage.py import-sources <FILE|->  [options]
```

- Positional `source`: path to a file, or `-` for stdin.
- `--format {json,lines}` — default: infer (`.json` ext or leading `{`/`[` →
  json; otherwise lines).
  - **json**: either a bare array of items, or `{"sources": [...], "activate": ...}`.
    Top-level `activate`/`defer_indexing`/`dry_run` in the file are used unless
    overridden by flags.
  - **lines**: one `url` or `key` per line; `#` comments and blank lines
    ignored. Each becomes `{"url": line}` (or `{"key": line, "source_type": "p"}`
    if it looks like a bare `PL.../LL.../OLAK...` id — otherwise error asking for
    a URL).
- `--activate` / `--no-activate` (maps to `activate=True/False`);
  `--inactive` is an alias for `--no-activate`. Absent → `activate=None`.
- `--defer-indexing`, `--dry-run`.
- `--default-resolution 1080p`, `--default-index-schedule 86400` — applied to
  items that don't set the field (the command injects them before calling the
  core).
- Calls `import_sources(...)`. Prints one line per result
  (`+ created  <name>  [<key>]`, `= exists  <name>`, `! error  <detail>`), then
  `created=.. exists=.. errors=..`.
- `raise CommandError` (exit ≠ 0) only if `report.errors > 0 and not dry_run`.

---

## 5. Import item schema

**Required:** `url` **OR** (`key` + `source_type`).

**Caller-only helper keys:** `url`, `title` (used to derive `name`; never stored
directly).

**Optional accepted fields** (→ map 1:1 to `Source` fields; TubeSync default in
parens, from `sync/models/source.py` / `sync/choices.py`):

| field | default | notes |
|---|---|---|
| `name` | derived | unique, ≤100 |
| `directory` | `slugify(name)` | unique, ≤100, must stay in `DOWNLOAD_ROOT` |
| `source_resolution` | `1080p` | `SourceResolution` values incl. `audio` |
| `source_vcodec` | `VP9` | `AV1`/`VP9`/`AVC1` |
| `source_acodec` | `OPUS` | `OPUS`/`MP4A` |
| `index_schedule` | `86400` | `IndexSchedule` values; `0` = never |
| `download_media` | `true` | `false` = index-only |
| `index_videos` | `true` | |
| `index_streams` | `false` | ignored for playlists |
| `download_cap` | `0` | `CapChoices` seconds |
| `delete_old_media` | `false` | |
| `days_to_keep` | `14` | |
| `delete_removed_media` | `false` | playlist: delete media no longer in list |
| `delete_files_on_disk` | `false` | |
| `filter_text_invert` | `false` | (`filter_text` itself is **rejected**) |
| `filter_seconds` | `null` | |
| `filter_seconds_min` | `true` | |
| `prefer_60fps` | `true` | |
| `prefer_hdr` | `false` | |
| `audio_track` | `o` | `o` (original) / `d` (publisher default); which audio track when a video has more than one |
| `fallback` | `h` | `Fallback` values |
| `copy_channel_images` | `false` | |
| `copy_thumbnails` | `false` | |
| `write_nfo` | `false` | |
| `write_json` | `false` | |
| `embed_metadata` | `false` | |
| `embed_thumbnail` | `false` | |
| `write_subtitles` | `false` | |
| `auto_subtitles` | `false` | |
| `sub_langs` | `en` | model `RegexValidator` |
| `enable_sponsorblock` | `true` | |
| `sponsorblock_categories` | `all` | list or comma string |
| `media_format` | `settings.MEDIA_FORMATSTR_DEFAULT` | |

**Rejected:** `uuid`, `created`, `last_crawl`, `has_failed`, `filter_text`, and
any key not in the list above → item `error` (HTTP) / `400` (whole request if
malformed at the envelope level).

### Real example — the OffTube use case (2 of 41 playlists)

```json
{
  "activate": true,
  "sources": [
    {
      "url": "https://www.youtube.com/playlist?list=PL3hFtw-djaEbjYRb-GYJhXfNgpUiIpVBG",
      "name": "Häkelanleitungen",
      "directory": "haekelanleitungen",
      "source_resolution": "1080p",
      "download_media": true,
      "write_json": true,
      "write_nfo": true,
      "copy_thumbnails": true,
      "embed_metadata": true,
      "enable_sponsorblock": false,
      "delete_removed_media": false
    },
    {
      "key": "PL3hFtw-djaEbEeA1yezzNDDszlRetNNVe",
      "source_type": "p",
      "name": "Watch later",
      "directory": "watch-later",
      "download_media": true
    }
  ]
}
```

The full 41-item list is generated on the OffTube side from
`playlist-backup/c/index.json` (fields per playlist: `playlistId`, `title`,
`visibility`, `count`). Playlist keys all share the `PL3hFtw-djaE` prefix (this
channel's own playlists, all private/unlisted). "Watch later" is exported by
Google Takeout with a normal `PL…` id — it may or may not be resolvable by
yt-dlp; if not, that one source ends up `has_failed=True` and the rest are
unaffected.

---

## 6. Auth & security

- **No new auth.** These endpoints sit behind the global
  `common.middleware.BasicAuthMiddleware` (django-basicauth). When the container
  sets `HTTP_USER` / `HTTP_PASS` (→ `BASICAUTH_USERS`, `BASICAUTH_DISABLE=False`
  in `local_settings.py.container`), the client must send
  `Authorization: Basic ...`; missing/wrong → middleware returns `401`.
- **Do NOT** add `/api/...` to `settings.BASICAUTH_ALWAYS_ALLOW_URIS` (that list
  is the healthcheck bypass — see `common/middleware.py`).
- When BasicAuth is disabled (no `HTTP_USER`), the endpoints are open — same
  posture as the rest of the TubeSync UI, which is documented as LAN-only. State
  this explicitly in the docs.
- `csrf_exempt` on the API views only (justified above). Everything else keeps
  CSRF.
- Path-traversal guard on `directory` is mandatory (§2.1).
- Keep `MAX_IMPORT_ITEMS` enforcement server-side.

---

## 7. Behaviour notes (put these in the wiki page)

- **Cookies.** yt-dlp reads a single global `settings.COOKIES_FILE` =
  `/config/cookies.txt` (`sync/youtube.py::get_yt_opts`). The bulk import only
  creates rows. Private playlists index only if the cookie account can see them;
  otherwise `has_failed=True` + exponential-backoff retry (existing behaviour).
  The file can be set over HTTP, see §7a.

### 7a. `GET`/`POST /api/cookies` — set the global cookies.txt

`CookiesAPIView` (`sync/views/api.py`), same plain-view + `BasicAuthMiddleware`
auth as the rest of the API. Added so a trusted caller (OffTube's `/backend`
"Musik Download" tab) can set the cookie once instead of copying it into the
container by hand.

- `GET /api/cookies` → `{"has_cookies": bool, "size": <bytes>, "valid_netscape":
  bool}`. **The content is never returned.** `valid_netscape` is false when the
  stored file's first line is not `#( Netscape)? HTTP Cookie File` or it has no
  tab-separated cookie rows.
- `POST /api/cookies` with `{"text": "<netscape cookies.txt>"}` (or the raw body)
  → normalises (CRLF→LF, strip BOM, **prepend the magic header line if missing** —
  `http.cookiejar` checks only the first line and yt-dlp rejects the whole file
  otherwise) and writes `settings.COOKIES_FILE`. Empty/whitespace body → deletes
  the file. A body with no tab-separated `\tTRUE\t`/`\tFALSE\t` cookie row →
  `400`. Oversized body → `413`. Response is the same shape as `GET`.
- No versioning/rotation: a second `POST` replaces the file. yt-dlp picks the new
  file up on the next download (it re-reads `get_yt_opts` per job).

### 7b. `POST /api/downloads` — audio-only (Weg B)

The direct-download job accepts two extra fields:

- `"audio": true` — download the best **audio** track only (no video), extract to
  `.opus` (default) or `.m4a`, embed cover + metadata, land in
  `settings.DOWNLOAD_AUDIO_DIR` instead of `DOWNLOAD_VIDEO_DIR`. yt-dlp is pointed
  at `music.youtube.com/watch?v=…` for clean artist/album/track tags.
- `"acodec": "opus" | "mp4a"` — default `opus`.

Used by OffTube's `/backend` "Musik Download" tab for a YouTube-Music library
export (a flat song-ID list with no playlist URL, so Weg A / `/api/sources` does
not apply).
- **No reachability check at import time** — matches the current ORM/`shell`
  path. A bad `key` fails on the first `index_source` run.
- **Politeness is unchanged and sufficient:** `index_source` runs on
  `TaskQueue.LIMIT` (1 worker → sources indexed serially), yt-dlp sleeps come
  from `settings.YOUTUBE_DEFAULTS` (`sleep_interval_requests=3`, …) and
  `YOUTUBE_INFO_SLEEP_REQUESTS=1`. Do not add new throttling; do not parallelise.
- **Postgres** (embedded, default in this fork) removes the SQLite
  "database is locked" risk that made bulk source creation dangerous before —
  this is *why* the API is safe to add now.
- Disk: a playlist source with thousands of items (e.g. a big "Watch later")
  will download for a long time. Recommend `download_cap` or `download_media:
  false` first for the giants; mention in docs.

---

## 8. Tests

Add to the existing test layout (`sync/tests.py` / `sync/tests/`):

**`import_sources()` / `build_source_kwargs()` unit**
- url → (key, source_type) for channel, channel-id, playlist; bad url → error.
- `key`+`source_type` path; missing both → error.
- created / exists (idempotent re-run) / error (name+directory collision via a
  pre-existing source).
- `dry_run=True` → report populated, `Source.objects.count()` unchanged.
- `activate=False` → created source has `index_schedule == 0`,
  `download_media is False`, `is_active is False`, and **no** `index_source`
  `TaskHistory` row.
- whitelist: unknown field → error; `filter_text` in item → error;
  `uuid`/`has_failed` in item → error.
- choices validation: bad `source_resolution` / `index_schedule` → error listing
  valid values.
- directory escape: `directory: "../../etc"` → error.
- `MAX_IMPORT_ITEMS + 1` items → `ValidationError`.

**HTTP API** (Django test client)
- No `Authorization` header with BasicAuth enabled → `401` (assert middleware
  behaviour with `@override_settings(BASICAUTH_DISABLE=False,
  BASICAUTH_USERS={...})`).
- `POST` happy path → `200`, `created` count, sources exist.
- `POST` with one good + one colliding item → `200`, `created==1`, `errors==1`,
  per-item statuses correct.
- `POST` bare array body accepted.
- `POST` malformed JSON / missing `sources` / too many → `400`.
- `GET` with `type=p`, `active`, `key` filters; `limit`/`offset` paging;
  `count` is the unpaged total.
- `DELETE` unknown uuid → `404`; known uuid → `200` and row gone.

**Command**
- `echo '<json>' | manage.py import-sources -` → creates sources.
- `--dry-run` → nothing persisted, exit `0`.
- errors present without `--dry-run` → `CommandError` / exit `1`.
- `--format lines` with URLs and `#` comments.

Mock or avoid real network: either patch the task functions, or assert on
scheduled `TaskHistory` rows rather than running the queue. Never hit YouTube in
tests.

---

## 9. Docs to update (part of this change)

- `README.md`: add the three endpoints + `manage.py import-sources` to the
  relevant table; note they're behind BasicAuth.
- New `docs/wiki/Bulk-importing-sources.md`: the item schema (§5), a
  `curl` example, the giant-playlist / cookies / politeness notes from §7.

---

## 10. Definition of done

- [ ] `sync/source_import.py` with `build_source_kwargs`, `import_sources`,
      `ImportReport`, `MAX_IMPORT_ITEMS`.
- [ ] `sync/views/api.py` with `SourceListCreateAPIView` (GET+POST) and
      `SourceDetailAPIView` (DELETE), `csrf_exempt`, `JsonResponse`.
- [ ] `sync/urls.py` + `sync/views/__init__.py` wiring.
- [ ] `sync/management/commands/import-sources.py`.
- [ ] Path-traversal guard on `directory`.
- [ ] Whitelist + choices validation; `filter_text` and metadata fields rejected.
- [ ] Idempotent on `key`; per-item transaction; partial success → `200`.
- [ ] `activate=False` creates genuinely inactive sources (no index task).
- [ ] Tests in §8 pass; `make test` / the CI test job green.
- [ ] `README.md` + wiki page updated.
- [ ] No new dependency; DRF not added; no change to auth middleware,
      `BASICAUTH_ALWAYS_ALLOW_URIS`, task queues, or yt-dlp sleep settings.
