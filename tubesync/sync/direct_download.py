'''
    The engine behind DirectDownloadJob: download a prepared list of video IDs
    one at a time with yt-dlp, straight by their watch URL. No playlist is ever
    queried; public videos need no cookies. Ported from
    offtube-takeout-importer/lib/queue.mjs.

    Runs as one long sequential task on the dedicated `direct` huey queue
    (sync/tasks.py::run_direct_download_job). Progress is written onto the
    DirectDownloadJob row after every video so a client can poll it; the
    per-video cursor plus a yt-dlp `--download-archive` file make a restart
    resumable and re-runs cheap.
'''

import json
import os
import random
import re
import time
from pathlib import Path

import yt_dlp
from django.conf import settings
from django.utils.text import slugify

from common.logger import log
from .youtube import get_yt_opts


# Politeness, matching queue.mjs.
MIN_SLEEP_S = 5
MAX_SLEEP_S = 15
PLAYLIST_PAUSE_S = 30
LOG_MAX = 60

# When YouTube starts refusing ("Sign in to confirm you're not a bot"), backing
# off hard is the only thing that helps (archive-playlists.sh: "wait ~24h").
# Ramp the pause on consecutive failures; reset on the next success.
BACKOFF_S = {3: 300, 6: 1800, 10: 3600}
BOT_MARKERS = ("confirm you", "not a bot", "sign in to confirm", "HTTP Error 429")

_ID_RE = re.compile(r'^[A-Za-z0-9_-]{11}$')


def height_for(resolution):
    m = re.search(r'(\d+)', str(resolution or ''))
    return int(m.group(1)) if m else 1080


def safe_directory(name, fallback='playlist'):
    d = slugify(str(name or '').replace('_', '-').replace('&', 'and').replace('+', 'and'))
    return d or fallback


def video_dir(directory):
    prefix = getattr(settings, 'DOWNLOAD_VIDEO_DIR', 'video')
    return Path(settings.DOWNLOAD_ROOT) / prefix / directory


def archive_path():
    p = Path(settings.CONFIG_BASE_DIR) / 'state' / 'direct-download-archive.txt'
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _fmt_speed(bps):
    if not bps:
        return None
    for unit in ('B', 'KiB', 'MiB', 'GiB'):
        if bps < 1024:
            return f'{bps:.1f}{unit}/s'
        bps /= 1024
    return f'{bps:.1f}TiB/s'


def _fmt_eta(secs):
    if secs is None:
        return None
    secs = int(secs)
    return f'{secs // 60:02d}:{secs % 60:02d}'


def _short(err):
    s = str(err).replace('\n', ' ').strip()
    return s[:300]


def interruptible_sleep(secs, job):
    '''Sleep in 3s steps, bail out early if the job was asked to stop.'''
    end = time.monotonic() + secs
    while time.monotonic() < end:
        time.sleep(min(3.0, end - time.monotonic()))
        try:
            job.refresh_from_db(fields=['stop_requested'])
        except Exception:
            return
        if job.stop_requested:
            return


def make_progress_hook(job, playlist_title):
    state = {'last': 0.0}

    def hook(d):
        if d.get('status') != 'downloading':
            return
        now = time.monotonic()
        if now - state['last'] < 1.5:
            return
        state['last'] = now
        total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
        got = d.get('downloaded_bytes') or 0
        if total:
            pct = round(got / total * 100)
        elif d.get('fragment_count'):
            pct = round((d.get('fragment_index') or 0) / d['fragment_count'] * 100)
        else:
            pct = 0
        info = d.get('info_dict') or {}
        title = info.get('title') or (job.current or {}).get('videoTitle')
        job.current = {
            'playlistTitle': playlist_title,
            'videoTitle': title,
            'percent': pct,
            'speed': _fmt_speed(d.get('speed')),
            'eta': _fmt_eta(d.get('eta')),
        }
        try:
            job.save(update_fields=['current', 'updated_at'])
        except Exception:
            pass

    return hook


def already_have(out_dir, video_id):
    # Cross-mechanism dedup: a media file whose name contains this id already
    # sits here (from a TubeSync Source download `..._<id>_...`, the standalone
    # importer `... [<id>].ext`, or an earlier run). --download-archive covers
    # our own repeats; this covers everyone else's.
    d = Path(out_dir)
    if not d.is_dir():
        return False
    for f in d.iterdir():
        if not f.is_file():
            continue
        name = f.name
        if name.endswith(('.info.json', '.jpg', '.webp', '.png', '.nfo', '.part', '.ytdl')):
            continue
        if video_id in name:
            return True
    return False


def download_one(video_id, out_dir, *, resolution, hook, log_line):
    '''
        Download one video by watch URL into out_dir.
        Returns 'ok', 'blocked' (YouTube anti-bot / 429) or 'fail'.
    '''
    h = height_for(resolution)
    url = f'https://www.youtube.com/watch?v={video_id}'
    opts = get_yt_opts()  # base: cookies (if present), cachedir, extractor_args, sleeps
    paths = dict(opts.get('paths') or {})
    paths['home'] = str(out_dir)
    opts.update({
        'format': f'bv*[height<={h}]+ba/b[height<={h}]/b',
        'merge_output_format': 'mkv',
        'final_ext': 'mkv',
        'outtmpl': '%(uploader)s - %(title)s [%(id)s].%(ext)s',
        'paths': paths,
        'writeinfojson': True,
        'writethumbnail': True,
        'addmetadata': True,
        'postprocessors': [
            {'key': 'FFmpegMetadata', 'add_metadata': True, 'add_chapters': True},
        ],
        'download_archive': str(archive_path()),
        'retries': 3,
        'fragment_retries': 3,
        'sleep_interval_requests': 2,
        'ignoreerrors': False,
        'quiet': True,
        'no_warnings': True,
        'noprogress': True,
        'progress_hooks': [hook],
    })
    try:
        with yt_dlp.YoutubeDL(opts) as y:
            rc = y.download([url])
        return 'ok' if rc == 0 else 'fail'
    except yt_dlp.utils.DownloadError as e:
        msg = _short(e)
        log_line(f'! {video_id}: {msg}')
        return 'blocked' if any(m.lower() in msg.lower() for m in BOT_MARKERS) else 'fail'
    except Exception as e:  # noqa: BLE001 - keep the job alive on any single-video failure
        log_line(f'! {video_id}: {e.__class__.__name__}: {_short(e)}')
        return 'fail'


def _patch_one(p, playlist_id, playlist_title):
    try:
        data = json.loads(p.read_text())
    except Exception:
        return
    if data.get('playlist_id'):
        return
    data['playlist_id'] = playlist_id
    data['playlist_title'] = playlist_title
    try:
        p.write_text(json.dumps(data, ensure_ascii=False))
    except Exception:
        pass


def patch_video_info_json(out_dir, video_id, playlist_id, playlist_title):
    '''
        Patch the single just-downloaded video's *.info.json right away, so
        OffTube groups it as a playlist member even if the job is stopped or
        fails before the playlist finishes.
    '''
    d = Path(out_dir)
    if not d.is_dir():
        return
    for p in d.iterdir():
        if p.name.endswith('.info.json') and video_id in p.name:
            _patch_one(p, playlist_id, playlist_title)


def patch_info_json(out_dir, playlist_id, playlist_title):
    '''
        Catch-all pass over every *.info.json in out_dir (idempotent - skips
        ones already carrying playlist_id). Runs when a playlist finishes; the
        per-video patch above does most of the work.
    '''
    for p in Path(out_dir).glob('*.info.json'):
        _patch_one(p, playlist_id, playlist_title)


def run_job(job):
    '''
        Sequential download loop. Resumes from job.cursor_playlist / cursor_video.
        Honours job.stop_requested between videos. Sets the final status.
    '''
    Model = job.__class__
    playlists = job.playlists or []
    job.total = sum(len(p.get('video_ids') or []) for p in playlists)
    job.status = Model.Status.RUNNING
    job.save(update_fields=['total', 'status', 'updated_at'])

    log_lines = list(job.log or [])

    def add_log(line):
        log_lines.append(f'[{time.strftime("%H:%M:%S")}] {line}')
        del log_lines[:-LOG_MAX]
        job.log = log_lines

    consecutive_blocked = 0

    start_pi = job.cursor_playlist
    for pi in range(start_pi, len(playlists)):
        pl = playlists[pi]
        directory = pl.get('directory') or safe_directory(pl.get('title'))
        out_dir = video_dir(directory)
        out_dir.mkdir(parents=True, exist_ok=True)
        vids = pl.get('video_ids') or []
        start_vi = job.cursor_video if pi == start_pi else 0
        add_log(f'Playlist "{pl.get("title")}" ({start_vi}/{len(vids)}) -> {directory}')

        for vi in range(start_vi, len(vids)):
            job.refresh_from_db(fields=['stop_requested'])
            if job.stop_requested:
                add_log('Abgebrochen.')
                job.current = None
                job.status = Model.Status.STOPPED
                job.save()
                return

            video_id = vids[vi]
            job.current = {
                'playlistTitle': pl.get('title'), 'videoTitle': video_id,
                'percent': 0, 'speed': None, 'eta': None,
            }
            job.save(update_fields=['current', 'updated_at'])

            if not _ID_RE.match(str(video_id)):
                add_log(f'! ungueltige ID uebersprungen: {video_id}')
                res = 'fail'
            elif already_have(out_dir, video_id):
                res = 'ok'
            else:
                res = download_one(
                    video_id, out_dir,
                    resolution=job.resolution,
                    hook=make_progress_hook(job, pl.get('title')),
                    log_line=add_log,
                )

            job.cursor_playlist, job.cursor_video = pi, vi + 1
            if res == 'ok':
                job.completed += 1
                consecutive_blocked = 0
                patch_video_info_json(out_dir, video_id, pl.get('playlist_id'), pl.get('title'))
            else:
                job.failed += 1
                if res == 'blocked':
                    consecutive_blocked += 1
            job.save(update_fields=[
                'cursor_playlist', 'cursor_video', 'completed', 'failed',
                'log', 'updated_at',
            ])

            pause = random.uniform(MIN_SLEEP_S, MAX_SLEEP_S)
            for threshold, secs in sorted(BACKOFF_S.items(), reverse=True):
                if consecutive_blocked >= threshold:
                    pause = secs
                    add_log(f'YouTube blockt ({consecutive_blocked}x) - pausiere {secs // 60} min')
                    job.save(update_fields=['log', 'updated_at'])
                    break
            interruptible_sleep(pause, job)

        patch_info_json(out_dir, pl.get('playlist_id'), pl.get('title'))
        job.playlists_done = pi + 1
        job.cursor_playlist, job.cursor_video = pi + 1, 0
        job.current = None
        job.save(update_fields=[
            'playlists_done', 'cursor_playlist', 'cursor_video', 'current',
            'log', 'updated_at',
        ])
        if pi + 1 < len(playlists):
            interruptible_sleep(PLAYLIST_PAUSE_S, job)

    add_log(
        f'Fertig: {job.completed} geladen, {job.failed} fehlgeschlagen '
        f'({len(playlists)} Playlist(en)).'
    )
    job.current = None
    job.status = Model.Status.DONE
    job.save()
    log.info(f'DirectDownloadJob {job.uuid} done: {job.completed}/{job.total}')
