'''
    DirectDownloadJob - a one-shot, sequential "download this prepared list of
    video IDs" job.

    This is deliberately NOT wired into the Source/Media model. The caller (the
    OffTube backend) already has the individual video IDs from a Google Takeout
    export; we download each video directly by its watch URL. The playlist is
    never queried, so private/unlisted source playlists are irrelevant and no
    cookies are required for public videos.

    Ported from offtube-takeout-importer/lib/queue.mjs. Progress is written back
    onto the row so a client can poll it; a yt-dlp `--download-archive` file
    makes re-runs cheap and the row's cursors make a restart resumable.
'''

import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _


class DirectDownloadJob(models.Model):

    class Status(models.TextChoices):
        RUNNING = 'running', _('Running')
        DONE = 'done', _('Done')
        STOPPED = 'stopped', _('Stopped')
        ERROR = 'error', _('Error')

    uuid = models.UUIDField(
        _('uuid'), primary_key=True, default=uuid.uuid4, editable=False,
    )
    created_at = models.DateTimeField(_('created at'), auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(_('updated at'), auto_now=True)
    status = models.CharField(
        _('status'), max_length=10, choices=Status.choices,
        default=Status.RUNNING, db_index=True,
    )
    # [{title, playlist_id, directory, video_ids: [...]}]
    playlists = models.JSONField(_('playlists'), default=list)
    resolution = models.CharField(_('resolution'), max_length=8, default='1080p')
    # audio=True -> download the best audio track only (no video), extract to
    # acodec ('opus' -> .opus, 'mp4a' -> .m4a), embed cover + metadata, and land
    # in settings.DOWNLOAD_AUDIO_DIR instead of DOWNLOAD_VIDEO_DIR.
    audio = models.BooleanField(_('audio only'), default=False)
    acodec = models.CharField(_('audio codec'), max_length=8, default='opus')

    cursor_playlist = models.PositiveIntegerField(_('cursor playlist'), default=0)
    cursor_video = models.PositiveIntegerField(_('cursor video'), default=0)

    total = models.PositiveIntegerField(_('total'), default=0)
    completed = models.PositiveIntegerField(_('completed'), default=0)
    failed = models.PositiveIntegerField(_('failed'), default=0)
    playlists_done = models.PositiveIntegerField(_('playlists done'), default=0)

    # {playlistTitle, videoTitle, percent, speed, eta}
    current = models.JSONField(_('current'), null=True, blank=True, default=None)
    log = models.JSONField(_('log'), default=list)
    stop_requested = models.BooleanField(_('stop requested'), default=False)

    class Meta:
        verbose_name = _('Direct Download Job')
        verbose_name_plural = _('Direct Download Jobs')
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.uuid} ({self.status}, {self.completed}/{self.total})'

    @property
    def phase(self):
        # Mirrors the standalone importer's GET /api/status vocabulary.
        return {
            self.Status.RUNNING: 'running',
            self.Status.DONE: 'done',
            self.Status.STOPPED: 'stopped',
            self.Status.ERROR: 'error',
        }.get(self.status, self.status)

    def as_status_dict(self):
        return {
            'id': str(self.uuid),
            'status': self.status,
            'phase': self.phase,
            'resolution': self.resolution,
            'audio': self.audio,
            'acodec': self.acodec,
            'overall': {
                'completed': self.completed,
                'failed': self.failed,
                'total': self.total,
                'playlistsDone': self.playlists_done,
                'playlistsTotal': len(self.playlists or []),
            },
            'current': self.current,
            'log': list(self.log or []),
            'createdAt': self.created_at.isoformat() if self.created_at else None,
            'updatedAt': self.updated_at.isoformat() if self.updated_at else None,
        }
