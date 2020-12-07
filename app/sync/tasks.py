'''
    Start, stop and manage scheduled tasks. These are generally triggered by Django
    signals (see signals.py).
'''


import json
import math
import uuid
from io import BytesIO
from hashlib import sha1
from datetime import timedelta
from PIL import Image
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from django.db.utils import IntegrityError
from background_task import background
from background_task.models import Task, CompletedTask
from common.logger import log
from common.errors import NoMediaException
from .models import Source, Media
from .utils import get_remote_image, resize_image_to_height


def get_hash(task_name, pk):
    '''
        Create a background_task compatible hash for a Task or CompletedTask.
    '''
    task_params = json.dumps(((str(pk),), {}), sort_keys=True)
    return sha1(f'{task_name}{task_params}'.encode('utf-8')).hexdigest()


def map_task_to_instance(task):
    '''
        Reverse-maps an scheduled backgrond task to an instance. Requires the task name
        to be a known task function and the first argument to be a UUID. This is used
        because UUID's are incompatible with background_task's "creator" feature.
    '''
    TASK_MAP = {
        'sync.tasks.index_source_task': Source,
        'sync.tasks.download_media_thumbnail': Media,
    }
    MODEL_URL_MAP = {
        Source: 'sync:source',
        Media: 'sync:media-item',
    }
    task_func, task_args_str = task.task_name, task.task_params
    model = TASK_MAP.get(task_func, None)
    if not model:
        return None, None
    url = MODEL_URL_MAP.get(model, None)
    if not url:
        return None, None
    try:
        task_args = json.loads(task_args_str)
    except (TypeError, ValueError, AttributeError):
        return None, None
    if len(task_args) != 2:
        return None, None
    args, kwargs = task_args
    if len(args) == 0:
        return None, None
    instance_uuid_str = args[0]
    try:
        instance_uuid = uuid.UUID(instance_uuid_str)
    except (TypeError, ValueError, AttributeError):
        return None, None
    try:
        instance = model.objects.get(pk=instance_uuid)
        return instance, url
    except model.DoesNotExist:
        return None, None


def get_error_message(task):
    '''
        Extract an error message from a failed task.
    '''
    if not task.has_error():
        return ''
    stacktrace_lines = task.last_error.strip().split('\n')
    if len(stacktrace_lines) == 0:
        return ''
    error_message = stacktrace_lines[-1].strip()
    if ':' not in error_message:
        return ''
    return error_message.split(':', 1)[1].strip()


def get_source_completed_tasks(source_id, only_errors=False):
    '''
        Returns a queryset of CompletedTask objects for a source by source ID.
    '''
    source_hash = get_hash('sync.tasks.index_source_task', source_id)
    q = {'task_hash': source_hash}
    if only_errors:
        q['failed_at__isnull'] = False
    return CompletedTask.objects.filter(**q).order_by('-failed_at')


def delete_index_source_task(source_id):
    Task.objects.drop_task('sync.tasks.index_source_task', args=(source_id,))


def cleanup_completed_tasks():
    days_to_keep = getattr(settings, 'COMPLETED_TASKS_DAYS_TO_KEEP', 30)
    delta = timezone.now() - timedelta(days=days_to_keep)
    log.info(f'Deleting completed tasks older than {days_to_keep} days '
             f'(run_at before {delta})')
    CompletedTask.objects.filter(run_at__lt=delta).delete()


@background(schedule=0)
def index_source_task(source_id):
    '''
        Indexes media available from a Source object.
    '''
    try:
        source = Source.objects.get(pk=source_id)
    except Source.DoesNotExist:
        # Task triggered but the Source has been deleted, delete the task
        delete_index_source_task(source_id)
        return
    # Reset any errors
    source.has_failed = False
    source.save()
    # Index the source
    videos = source.index_media()
    if not videos:
        raise NoMediaException(f'Source "{source}" (ID: {source_id}) returned no '
                               f'media to index, is the source key valid? Check the '
                               f'source configuration is correct and that the source '
                               f'is reachable')
    # Got some media, update the last crawl timestamp
    source.last_crawl = timezone.now()
    source.save()
    log.info(f'Found {len(videos)} media items for source: {source}')
    for video in videos:
        # Create or update each video as a Media object
        key = video.get(source.key_field, None)
        if not key:
            # Video has no unique key (ID), it can't be indexed
            continue
        try:
            media = Media.objects.get(key=key)
        except Media.DoesNotExist:
            media = Media(key=key)
        media.source = source
        media.metadata = json.dumps(video)
        upload_date = media.upload_date
        if upload_date:
            media.published = timezone.make_aware(upload_date)
        try:
            media.save()
            log.info(f'Indexed media: {source} / {media}')
        except IntegrityError as e:
            log.error(f'Index media failed: {source} / {media} with "{e}"')
    # Tack on a cleanup of old completed tasks
    cleanup_completed_tasks()


@background(schedule=0)
def download_media_thumbnail(media_id, url):
    '''
        Downloads an image from a URL and saves it as a local thumbnail attached to a
        Media object.
    '''
    try:
        media = Media.objects.get(pk=media_id)
    except Media.DoesNotExist:
        # Task triggered but the media no longer exists, ignore task
        return
    width = getattr(settings, 'MEDIA_THUMBNAIL_WIDTH', 430)
    height = getattr(settings, 'MEDIA_THUMBNAIL_HEIGHT', 240)
    i = get_remote_image(url)
    log.info(f'Resizing {i.width}x{i.height} thumbnail to '
             f'{width}x{height}: {url}')
    i = resize_image_to_height(i, width, height)
    image_file = BytesIO()
    i.save(image_file, 'JPEG', quality=80, optimize=True, progressive=True)
    image_file.seek(0)
    media.thumb.save(
        'thumb',
        SimpleUploadedFile(
            'thumb',
            image_file.read(),
            'image/jpeg',
        ),
        save=True
    )
    log.info(f'Saved thumbnail for: {media} from: {url}')
    return True
