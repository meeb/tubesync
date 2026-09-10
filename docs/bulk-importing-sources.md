# Bulk-importing sources

This fork of TubeSync can create many `Source` objects in one operation, list
them, and delete them, without going through the HTML forms or `manage.py
shell`. The typical use case is importing a set of YouTube playlists (or
channels) and then letting TubeSync index and download them normally.

There are two entry points and they share one validation/creation core
(`sync/source_import.py`), so they behave identically:

* the HTTP API — `POST/GET /api/sources`, `DELETE /api/sources/<uuid>`
* the management command — `manage.py import-sources`

Nothing here contacts YouTube. The import only creates rows. Whether a key is
actually reachable is discovered the first time `index_source` runs — an
unreachable key ends up as `has_failed=True` and is retried with exponential
backoff, exactly like a source added through the web UI.

---

## Authentication

The HTTP endpoints sit behind the same optional HTTP basic auth as the rest of
TubeSync. When the container has `HTTP_USER` / `HTTP_PASS` set, send
`Authorization: Basic …`; a missing or wrong header returns `401`. When basic
auth is **not** configured the endpoints are open on the LAN — the same posture
as the TubeSync web UI, which is documented as a LAN-only interface. Do not
expose TubeSync directly to the internet.

The API views are CSRF-exempt (there is no session login on these
machine-to-machine endpoints); everything else in TubeSync keeps CSRF.

---

## Import item schema

Each item is a JSON object. It must identify the source with **either** a `url`
**or** a `key` + `source_type` pair:

```jsonc
{ "url": "https://www.youtube.com/playlist?list=PL..." }
// or
{ "key": "PL...", "source_type": "p" }   // c = channel, i = channel-by-id, p = playlist
```

Two keys are caller helpers and are never stored directly:

| key | meaning |
| --- | --- |
| `url` | resolved to `key` + `source_type` with the same logic the "validate source" form uses |
| `title` | used to derive `name` when `name` is not given |

All other keys map 1:1 onto `Source` model fields. The commonly useful ones
(TubeSync default in parentheses):

| field | default | notes |
| --- | --- | --- |
| `name` | derived from `title`/`key` | unique, ≤ 100 chars |
| `directory` | `slugify(name)` | unique, ≤ 100 chars, must resolve inside the downloads root |
| `source_resolution` | `1080p` | `audio`, `360p` … `4320p` |
| `source_vcodec` | `VP9` | `AV1` / `VP9` / `AVC1` |
| `source_acodec` | `OPUS` | `OPUS` / `MP4A` |
| `audio_track` | `o` | `o` (original) / `d` (publisher default) — which audio track when a video has more than one |
| `index_schedule` | `86400` | seconds; `0` = never (source is inactive) |
| `download_media` | `true` | `false` = index only, do not download |
| `index_videos` | `true` | |
| `index_streams` | `false` | ignored for playlists |
| `download_cap` | `0` | seconds; caps how old media may be |
| `delete_removed_media` | `false` | playlist: delete media no longer on the list |
| `days_to_keep` | `14` | |
| `write_nfo` / `write_json` | `false` | |
| `embed_metadata` / `embed_thumbnail` | `false` | |
| `copy_thumbnails` / `copy_channel_images` | `false` | |
| `write_subtitles` / `auto_subtitles` | `false` | |
| `sub_langs` | `en` | comma-separated, e.g. `en,de` |
| `enable_sponsorblock` | `true` | |
| `sponsorblock_categories` | `all` | list or comma string of SponsorBlock categories, or `all` |
| `media_format` | server default | |

**Rejected** (item is reported as an error): `uuid`, `created`, `last_crawl`,
`has_failed`, `filter_text` (overloaded internally), and any key not on the list
above. Booleans must be real JSON booleans — `"true"` / `1` as strings are
rejected on purpose to keep the contract tight.

---

## `POST /api/sources`

Request body — an object, or a bare array which is treated as `{"sources": […]}`:

```jsonc
{
  "sources": [ { /* import item */ }, … ],   // required, non-empty, ≤ 500
  "activate": true,          // optional: force sources active / inactive
  "defer_indexing": false,   // optional: bulk_create + staggered index tasks (large imports)
  "dry_run": false           // optional: validate + report, roll everything back
}
```

`activate`:

* `true` — schedule indexing and downloads (the model defaults)
* `false` — create the source **inactive** (`index_schedule = 0`,
  `download_media = false`); no index task is scheduled
* omitted — keep whatever each item specified (or the model defaults)

The response is **always `200`**, even when some items failed — check the
per-item `results`. Creation is idempotent on `key`: importing the same key
again returns `exists` and does not touch the existing row.

```jsonc
{
  "created": 39,
  "exists": 1,
  "errors": 1,
  "dry_run": false,
  "results": [
    {"status": "created", "key": "PL3hFtw-djaEbjYRb-GYJhXfNgpUiIpVBG", "uuid": "0c2e…"},
    {"status": "exists",  "key": "PL3hFtw-djaEbEeA1yezzNDDszlRetNNVe", "uuid": "7a11…"},
    {"status": "error",   "detail": "directory: Source with this Directory already exists.",
     "input": {"url": "https://www.youtube.com/playlist?list=PL…", "name": "Garten"}}
  ]
}
```

Other status codes: `400` for a malformed envelope (bad JSON, missing/empty
`sources`, more than 500 items, bad `activate`), `413` for a body larger than
Django's `DATA_UPLOAD_MAX_MEMORY_SIZE` (split into several requests).

### curl example

```bash
curl -sS -u "$HTTP_USER:$HTTP_PASS" \
  -H 'Content-Type: application/json' \
  http://tubesync.lan:4848/api/sources \
  -d '{
    "activate": true,
    "sources": [
      {"url": "https://www.youtube.com/playlist?list=PL3hFtw-djaEbjYRb-GYJhXfNgpUiIpVBG",
       "name": "Häkelanleitungen", "directory": "haekelanleitungen",
       "write_json": true, "write_nfo": true, "enable_sponsorblock": false},
      {"key": "PL3hFtw-djaEbEeA1yezzNDDszlRetNNVe", "source_type": "p",
       "name": "Watch later", "download_media": true}
    ]
  }'
```

---

## `GET /api/sources`

Query params (all optional): `type` (`c`/`i`/`p`), `active` (`1`/`0`, evaluated
with `Source.is_active`), `has_failed` (`1`/`0`), `key` (exact match — handy for
a client existence check), `limit` (default `100`, max `1000`), `offset`
(default `0`). An invalid value returns `400`.

```jsonc
{
  "count": 41,            // total matching, ignoring limit/offset
  "limit": 100,
  "offset": 0,
  "results": [
    {"uuid": "…", "key": "PL…", "name": "Häkelanleitungen",
     "directory": "haekelanleitungen", "source_type": "p",
     "index_schedule": 86400, "download_media": true,
     "is_active": true, "has_failed": false,
     "last_crawl": "2026-09-03T12:00:00Z", "media_count": 123}
  ]
}
```

---

## `DELETE /api/sources/<uuid>`

`404` if no source has that uuid, otherwise `200 {"deleted": "<uuid>", "name":
"<name>"}`. This runs the normal delete path (deactivate the source, schedule
removal of its media). There is no bulk delete.

---

## `manage.py import-sources`

```
docker exec -it tubesync python3 /app/manage.py import-sources <FILE|-> [options]
```

* positional: a path to a file, or `-` for stdin
* `--format {json,lines}` — inferred from the extension / first character if omitted
  * **json**: a bare array of items, or `{"sources": […], "activate": …}`.
    Top-level `activate` / `defer_indexing` / `dry_run` in the file are used
    unless a flag overrides them.
  * **lines**: one URL or bare playlist id per line; `#` comments and blank
    lines are ignored.
* `--activate` / `--no-activate` (alias `--inactive`) — absent means "leave item values"
* `--dry-run` — validate and report, persist nothing (exit `0`)
* `--defer-indexing` — `bulk_create` + staggered index tasks; large imports only
* `--default-resolution 1080p`, `--default-index-schedule 86400` — applied to
  items that do not set that field

It prints one line per result and a `created=.. exists=.. errors=..` summary,
and exits non-zero only when `errors > 0` and `--dry-run` was not used.

```bash
printf '%s\n' \
  '# my playlists' \
  'https://www.youtube.com/playlist?list=PL3hFtw-djaEbjYRb-GYJhXfNgpUiIpVBG' \
  'PL3hFtw-djaEbEeA1yezzNDDszlRetNNVe' \
| docker exec -i tubesync python3 /app/manage.py import-sources - --format lines --no-activate --dry-run
```

---

## Notes

* **Cookies are unchanged.** yt-dlp still reads the single global
  `/config/cookies.txt`. Private/unlisted playlists index only if that cookie
  account can see them.
* **Politeness is unchanged.** `index_source` runs on a single-worker queue, so
  sources are indexed one at a time; yt-dlp's own sleep settings apply. The
  import does not add throttling and does not parallelise.
* **Giant playlists** (a big "Watch later", thousands of items) will download
  for a long time. Import those with `download_media: false` or a
  `download_cap` first, then flip them on.
* The embedded PostgreSQL that this fork runs by default removed the SQLite
  "database is locked" contention that made bulk source creation risky before.

---

## Tests

The feature is covered by `sync/tests/test_source_import.py`,
`sync/tests/test_api.py` and `sync/tests/test_import_command.py`. They run as
part of the normal suite (`cd tubesync && python3 manage.py test`, and the CI
"Run Django tests" job) and never touch the network — task scheduling is
asserted via `TaskHistory` rows rather than by running the queue.
