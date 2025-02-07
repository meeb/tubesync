import os
import yt_dlp

from common.logger import log
from django.conf import settings


progress_hook = {
    'status': dict(),
}

postprocessor_hook = {
    'status': dict(),
}


class BaseStatus:
    status_dict = dict()
    valid = set()

    @classmethod
    def get(cls, key):
        return cls.status_dict.get(key, None)

    @classmethod
    def valid_status(cls, status):
        return status in cls.valid

    def __init__(self, hook_status_dict=None):
        self._status_dict = hook_status_dict or self.status_dict
        self._registered_keys = set()

    def register(self, *args):
        additions = dict()
        for key in args:
            if key is not None:
                self._registered_keys.add(key)
                additions[key] = self
        self._status_dict.update(additions)

    def cleanup(self):
        for key in self._registered_keys:
            if key in self._status_dict:
                del self._status_dict[key]

class ProgressHookStatus(BaseStatus):
    status_dict = progress_hook['status']
    valid = frozenset((
        'downloading',
        'finished',
        'error',
    ))

    def __init__(self, *args, status=None, info_dict={}, filename=None, **kwargs):
        super().__init__(self.status_dict)
        self.filename = filename
        self.info = info_dict
        self.status = status
        self.download_progress = 0

    def next_progress(self):
        if 0 == self.download_progress:
            return 0
        return 5 + self.download_progress

class PPHookStatus(BaseStatus):
    status_dict = postprocessor_hook['status']
    valid = frozenset((
        'started',
        'processing',
        'finished',
    ))

    def __init__(self, *args, status=None, postprocessor=None, info_dict={}, filename=None, **kwargs):
        super().__init__(self.status_dict)
        self.filename = filename
        self.info = info_dict
        self.media_name = None
        self.name = postprocessor
        self.status = status

def yt_dlp_progress_hook(event):
    if not ProgressHookStatus.valid_status(event['status']):
        log.warn(f'[youtube-dl] unknown progress event: {str(event)}')
        return None

    key = 'Unknown'
    if 'display_id' in event['info_dict']:
        key = event['info_dict']['display_id']
    elif 'id' in event['info_dict']:
        key = event['info_dict']['id']

    filename = os.path.basename(event.get('filename', '???'))
    if 'error' == event['status']:
        log.error(f'[youtube-dl] error occured downloading: {filename}')
    elif 'downloading' == event['status']:
        # get or create the status for key
        status = ProgressHookStatus.get(key)
        if status is None:
            status = ProgressHookStatus(**event)
            status.register(key, filename, status.filename)
            log.info(ProgressHookStatus.status_dict)

        downloaded_bytes = event.get('downloaded_bytes', 0) or 0
        total_bytes_estimate = event.get('total_bytes_estimate', 0) or 0
        total_bytes = event.get('total_bytes', 0) or total_bytes_estimate
        eta = event.get('_eta_str', '?').strip()
        percent_str = event.get('_percent_str', '?').strip()
        speed = event.get('_speed_str', '?').strip()
        total = event.get('_total_bytes_str', '?').strip()
        percent = None
        try:
            percent = int(float(percent_str.rstrip('%')))
        except:
            pass
        if downloaded_bytes > 0 and total_bytes > 0:
            percent = round(100 * downloaded_bytes / total_bytes)
        if percent and (status.next_progress() < percent) and (0 == percent % 5):
            status.download_progress = percent
            log.info(f'[youtube-dl] downloading: {filename} - {percent_str} '
                     f'of {total} at {speed}, {eta} remaining')
    elif 'finished' == event['status']:
        # update the status for key to the finished value
        status = ProgressHookStatus.get(key)
        if status is None:
            status = ProgressHookStatus(**event)
            status.register(key, filename, status.filename)
            log.info(ProgressHookStatus.status_dict)
        status.download_progress = 100

        total_size_str = event.get('_total_bytes_str', '?').strip()
        elapsed_str = event.get('_elapsed_str', '?').strip()
        log.info(f'[youtube-dl] finished downloading: {filename} - '
                 f'{total_size_str} in {elapsed_str}')

        status.cleanup()
        log.info(ProgressHookStatus.status_dict)

def yt_dlp_postprocessor_hook(event):
    if not PPHookStatus.valid_status(event['status']):
        log.warn(f'[youtube-dl] unknown postprocessor event: {str(event)}')
        return None

    name = key = 'Unknown'
    filename = os.path.basename(event.get('filename', '???'))
    if 'display_id' in event['info_dict']:
        key = event['info_dict']['display_id']
    elif 'id' in event['info_dict']:
        key = event['info_dict']['id']

    status = PPHookStatus(**event)
    status.register(key, filename, status.filename)

    title = None
    if 'fulltitle' in event['info_dict']:
        title = event['info_dict']['fulltitle']
    elif 'title' in event['info_dict']:
        title = event['info_dict']['title']

    if title:
        name = f'{key}: {title}'

    status.media_name = name

    if 'started' == event['status']:
        if 'formats' in event['info_dict']:
            del event['info_dict']['formats']
        if 'automatic_captions' in event['info_dict']:
            del event['info_dict']['automatic_captions']
        log.debug(repr(event['info_dict']))

    log.info(f'[{event["postprocessor"]}] {event["status"]} for: {name}')
    if 'finished' == event['status']:
        status.cleanup()


progress_hook.update({
    'class': ProgressHookStatus(),
    'function': yt_dlp_progress_hook,
})

postprocessor_hook.update({
    'class': PPHookStatus(),
    'function': yt_dlp_postprocessor_hook,
})

