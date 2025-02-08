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
    if event['status'] not in ProgressHookStatus.valid:
        log.warn(f'[youtube-dl] unknown progress event: {str(event)}')
        return None

    name = key = 'Unknown'
    if 'display_id' in event['info_dict']:
        key = event['info_dict']['display_id']
    elif 'id' in event['info_dict']:
        key = event['info_dict']['id']

    filename = os.path.basename(event.get('filename', '???'))
    if 'error' == event['status']:
        log.error(f'[youtube-dl] error occured downloading: {filename}')
    elif 'downloading' == event['status']:
        # get or create the status for key
        status = progress_hook['status'].get(filename, None)
        if status is None:
            status = ProgressHookStatus()
            progress_hook['status'].update({filename: status})

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
        if percent and (0 < percent) and (0 == percent % 5):
            log.info(f'[youtube-dl] downloading: {filename} - {percent_str} '
                     f'of {total} at {speed}, {eta} remaining')
        status.download_progress = percent or 0
    elif 'finished' == event['status']:
        # update the status for key to the finished value
        status = progress_hook['status'].get(filename, None)
        if status is None:
            status = ProgressHookStatus()
            progress_hook['status'].update({filename: status})
        status.download_progress = 100

        total_size_str = event.get('_total_bytes_str', '?').strip()
        elapsed_str = event.get('_elapsed_str', '?').strip()
        log.info(f'[youtube-dl] finished downloading: {filename} - '
                 f'{total_size_str} in {elapsed_str}')

        # clean up the status for key
        if key in progress_hook['status']:
            del progress_hook['status'][key]

def yt_dlp_postprocessor_hook(event):
    if event['status'] not in PPHookStatus.valid:
        log.warn(f'[youtube-dl] unknown postprocessor event: {str(event)}')
        return None

    name = key = 'Unknown'
    if 'display_id' in event['info_dict']:
        key = event['info_dict']['display_id']
    elif 'id' in event['info_dict']:
        key = event['info_dict']['id']

    postprocessor_hook['status'].update({key: PPHookStatus(*event)})

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
    if 'finished' == event['status'] and key in postprocessor_hook['status']:
        del postprocessor_hook['status'][key]


progress_hook = {
    'class': ProgressHookStatus(),
    'function': yt_dlp_progress_hook,
    'status': dict(),
}

postprocessor_hook = {
    'class': PPHookStatus(),
    'function': yt_dlp_postprocessor_hook,
    'status': dict(),
}

