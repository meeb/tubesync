import os
import yt_dlp

from common.logger import log
from django.conf import settings


class ProgressHookStatus:
    valid = frozenset((
        'downloading',
        'finished',
        'error',
    ))

    def __init__(self):
        self.download_progress = 0

class PPHookStatus:
    valid = frozenset((
        'started',
        'processing',
        'finished',
    ))

    def __init__(self, *args, status=None, postprocessor=None, info_dict={}, **kwargs):
        self.info = info_dict
        self.name = postprocessor
        self.status = status


def yt_dlp_progress_hook(event):
    hook = progress_hook.get('status', None)
    if hook is None:
        log.error('yt_dlp_progress_hook: failed to get hook status object')
        return None

    if event['status'] not in ProgressHookStatus.valid:
        log.warn(f'[youtube-dl] unknown event: {str(event)}')
        return None

    filename = os.path.basename(event.get('filename', '???'))
    if 'error' == event['status']:
        log.error(f'[youtube-dl] error occured downloading: {filename}')
    elif 'downloading' == event['status']:
        downloaded_bytes = event.get('downloaded_bytes', 0) or 0
        total_bytes = event.get('total_bytes', 0) or 0
        eta = event.get('_eta_str', '?').strip()
        percent_done = event.get('_percent_str', '?').strip()
        speed = event.get('_speed_str', '?').strip()
        total = event.get('_total_bytes_str', '?').strip()
        if downloaded_bytes > 0 and total_bytes > 0:
            p = round(100 * downloaded_bytes / total_bytes)
            if (0 == p % 5) and p > hook.download_progress:
                hook.download_progress = p
                log.info(f'[youtube-dl] downloading: {filename} - {percent_done} '
                         f'of {total} at {speed}, {eta} remaining')
        else:
            # No progress to monitor, just spam every 10 download messages instead
            if 0 == hook.download_progress % 10:
                log.info(f'[youtube-dl] downloading: {filename} - {percent_done} '
                         f'of {total} at {speed}, {eta} remaining')
            hook.download_progress += 1
    elif 'finished' == event['status']:
        total_size_str = event.get('_total_bytes_str', '?').strip()
        elapsed_str = event.get('_elapsed_str', '?').strip()
        log.info(f'[youtube-dl] finished downloading: {filename} - '
                 f'{total_size_str} in {elapsed_str}')

def yt_dlp_postprocessor_hook(event):
    if event['status'] not in PPHookStatus.valid:
        log.warn(f'[youtube-dl] unknown event: {str(event)}')
        return None

    postprocessor_hook['status'] = PPHookStatus(*event)

    name = key = 'Unknown'
    if 'display_id' in event['info_dict']:
        key = event['info_dict']['display_id']
    elif 'id' in event['info_dict']:
        key = event['info_dict']['id']

    title = None
    if 'fulltitle' in event['info_dict']:
        title = event['info_dict']['fulltitle']
    elif 'title' in event['info_dict']:
        title = event['info_dict']['title']

    if title:
        name = f'{key}: {title}'

    if 'started' == event['status']:
        if 'formats' in event['info_dict']:
            del event['info_dict']['formats']
        if 'automatic_captions' in event['info_dict']:
            del event['info_dict']['automatic_captions']
        log.debug(repr(event['info_dict']))

    log.info(f'[{event["postprocessor"]}] {event["status"]} for: {name}')


progress_hook = {
    'status': ProgressHookStatus(),
    'function': yt_dlp_progress_hook,
}

postprocessor_hook = {
    'status': PPHookStatus(),
    'function': yt_dlp_postprocessor_hook,
}

