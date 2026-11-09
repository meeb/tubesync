from __future__ import annotations

import contextlib

from pathlib import Path
from typing import ClassVar

from django import db

from common.logger import log
from common.utils import remove_enclosed
from sync.utils import filter_response


progress_hook = {
    'status': dict(),
}

postprocessor_hook = {
    'status': dict(),
}


class BaseStatus:
    status_dict: ClassVar[dict[str, BaseStatus]] = dict()
    valid = frozenset()

    @staticmethod
    def event_key(event: dict) -> str | None:
        expected_structure = (
            isinstance(event, dict) and
            'info_dict' in event and
            isinstance(event['info_dict'], dict)
        )  # fmt: skip
        key = None
        if expected_structure:
            key = event['info_dict'].get('display_id', key)
            if key is None:
                key = event['info_dict'].get('id', key)
        return key

    @classmethod
    def get(cls, key: str) -> BaseStatus | None:
        return cls.status_dict.get(key, None)

    @classmethod
    def valid_status(cls, event: dict) -> bool:
        if not isinstance(event, dict):
            return False
        status: str | None = event.get('status', None)
        return status is not None and status in cls.valid

    def __init__(self, /, hook_status_dict: dict | None = None, *, filename: str | None = None, info_dict: dict | None = None, status: str | None = None):
        self._registered_keys = set()
        self._status_dict = hook_status_dict or self.status_dict
        if info_dict is None:
            info_dict = dict()
        fn = info_dict.get('filename', None)
        resolved_fn = fn if filename is None else filename
        self.filename = resolved_fn
        self.info = info_dict
        self.filepath = None if resolved_fn is None else Path(resolved_fn)
        self.media_key = None
        self.media_uuid = None
        self.task_status = '[Started: 0%]'
        self.task_verbose_name = None

    def register(self, *args):
        additions = {key: self for key in args if key is not None}
        self._registered_keys.update(additions)
        self._status_dict.update(additions)

    def cleanup(self):
        # Discarded alternative: rebuild the dictionary
        # self._status_dict = {
        #     k: v
        #     for k, v in self._status_dict.items()
        #     if k not in self._registered_keys
        # }
        for key in self._registered_keys:
            self._status_dict.pop(key, None)

    def update_task(self):
        if self.media_key is None:
            return

        from .models import Media
        from .tasks import get_media_download_task

        media = task = None
        mqs = Media.objects.all()
        db.close_old_connections()
        if self.media_uuid:
            try:
                media = mqs.get(uuid=self.media_uuid)
                task = get_media_download_task(str(media.pk))
            except Media.DoesNotExist:
                log.exception('Media.uuid not found for "%s": %s', self.media_key, str(self.media_uuid))
                self.media_uuid = None
                db.close_old_connections()
                return self.update_task()
        else:
            mqs = mqs.exclude(
                skip=True,
                manual_skip=True,
                downloaded=True
            ).filter(
                source__download_media=True,
                can_download=True,
                key=self.media_key
            )
            for m in mqs:
                if (t := get_media_download_task(str(m.pk))):
                    media, task = m, t
                    break

        if media and task:
            if self.media_uuid is None:
                self.media_uuid = media.uuid
            if self.task_verbose_name is None:
                # clean up any previously prepended task_status
                # this happened because of duplicated tasks on my test system
                self.task_verbose_name = remove_enclosed(
                    task.verbose_name, '[', ']', ' ',
                )
            task.verbose_name = f'{self.task_status} {self.task_verbose_name}'
            task.save()
        db.close_old_connections()


class ProgressHookStatus(BaseStatus):
    status_dict = progress_hook['status']
    valid = frozenset((
        'downloading',
        'finished',
        'error',
    ))

    def __init__(self, *args, filename=None, info_dict=None, status=None, **kwargs):
        super().__init__(self.status_dict, filename=filename, info_dict=info_dict, status=status)
        self.download_progress = 0

    def next_progress(self):
        if 0 == self.download_progress:
            return 0
        return 1 + self.download_progress


class PPHookStatus(BaseStatus):
    status_dict = postprocessor_hook['status']
    valid = frozenset((
        'started',
        'processing',
        'finished',
    ))

    def __init__(self, *args, postprocessor=None, filename=None, info_dict=None, status=None, **kwargs):
        super().__init__(self.status_dict, filename=filename, info_dict=info_dict, status=status)
        self.media_name = None
        self.name = postprocessor


def yt_dlp_progress_hook(event):
    if not ProgressHookStatus.valid_status(event):
        log.warning(f'[youtube-dl] unknown progress event: {event!r}')
        return

    key = ProgressHookStatus.event_key(event)
    filepath = Path(event.get('filename', '???'))
    filename = filepath.name
    if 'error' == event['status']:
        log.error(f'[youtube-dl] error occured downloading: {filename}')
    elif 'downloading' == event['status']:
        # get or create the status for filepath
        status = ProgressHookStatus.get(str(filepath))
        if status is None:
            status = ProgressHookStatus(**event)
            status.register(key, filename, str(filepath))

        downloaded_bytes = event.get('downloaded_bytes') or 0
        total_bytes_estimate = event.get('total_bytes_estimate') or 0
        total_bytes = event.get('total_bytes') or total_bytes_estimate
        fragment_index = event.get('fragment_index') or 0
        fragment_count = event.get('fragment_count') or 0
        eta = event.get('_eta_str', '?').strip()
        percent_str = event.get('_percent_str', '?').strip()
        speed = event.get('_speed_str', '?').strip()
        total = event.get('_total_bytes_str', '?').strip()
        percent = None
        with contextlib.suppress(Exception):
            percent = int(float(percent_str.rstrip('%')))
        if 0 <= fragment_index and 0 < fragment_count:
            percent = round(100 * fragment_index / fragment_count)
        elif downloaded_bytes >= 0 and total_bytes > 0:
            percent = round(100 * downloaded_bytes / total_bytes)
        if percent and (status.next_progress() < percent) and (0 == percent % 5):
            status.download_progress = percent
            percent_str = f'{percent}%' if '?' == percent_str else percent_str
            if key:
                status.media_key = key
            status.task_status = f'[Downloading: {percent_str}]'
            status.update_task()
            log.info(f'[youtube-dl] downloading: {filename} - {percent_str} '
                     f'of {total} at {speed}, {eta} remaining')
    elif 'finished' == event['status']:
        # update the status for filepath to the finished value
        status = ProgressHookStatus.get(str(filepath))
        if status is None:
            status = ProgressHookStatus(**event)
            status.register(key, filename, str(filepath))
        status.download_progress = 100
        if key:
            status.media_key = key
        status.task_status = f'[Downloaded: {status.download_progress}%]'
        status.update_task()

        total_size_str = event.get('_total_bytes_str', '?').strip()
        elapsed_str = event.get('_elapsed_str', '?').strip()
        log.info(f'[youtube-dl] finished downloading: {filename} - '
                 f'{total_size_str} in {elapsed_str}')

        status.cleanup()


def yt_dlp_postprocessor_hook(event):
    if not PPHookStatus.valid_status(event):
        log.warning(f'[youtube-dl] unknown postprocessor event: {event!r}')
        return

    name = 'Unknown'
    key = PPHookStatus.event_key(event)
    if key is None:
        key = name
    filepath = Path(event.get('filename', '???'))
    filename = filepath.name

    postprocessor = event.get('postprocessor', None)
    title = event['info_dict'].get('fulltitle', None)
    if title is None:
        title = event['info_dict'].get('title', None)
    if title:
        name = f'{key}: {title}'

    combined_key = f'{key}: {postprocessor}: {filepath.parent!s}'
    status = PPHookStatus.get(combined_key)
    if status is None:
        status = PPHookStatus(**event)
        status.register(key, combined_key, postprocessor, filename, str(status.filepath))

    status.media_name = name

    if 'started' == event['status']:
        remove_keys = frozenset({
            'formats',
            'automatic_captions',
        })
        logged_dict = filter_response(event['info_dict'], True)
        found_keys = set(logged_dict.keys()).intersection(remove_keys)
        for found_key in found_keys:
            logged_dict.pop(found_key, None)
        log.debug(repr(logged_dict))

    if 'Unknown' != key:
        status.media_key = key
    status.task_status = f'[{postprocessor}: {event["status"]}]'
    status.update_task()

    log.info(f'[{postprocessor}] {event["status"]} for: {name}')
    if 'started' == event['status'] and 'Merger' == postprocessor:
        files_to_merge = event['info_dict'].get('__files_to_merge') or list()
        log.info(f'[{postprocessor}] Files to merge: {files_to_merge}')
        from .models import Media

        db.close_old_connections()
        try:
            media = Media.objects.get(pk=status.media_uuid)
            media.new_metadata.value['requested_formats'] = event['info_dict'].get('requested_formats')
            media.new_metadata.value['requested_subtitles'] = event['info_dict'].get('requested_subtitles')
            media.new_metadata.save()
        except Media.DoesNotExist:
            pass
        # ruff: ignore[BLE001]
        except Exception:
            log.exception('Failed to update metadata for: %s', str(status.media_uuid))
        finally:
            db.close_old_connections()
    elif 'finished' == event['status']:
        status.cleanup()


progress_hook.update({
    'class': ProgressHookStatus(),
    'function': yt_dlp_progress_hook,
})

postprocessor_hook.update({
    'class': PPHookStatus(),
    'function': yt_dlp_postprocessor_hook,
})

