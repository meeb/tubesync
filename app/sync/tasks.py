'''
    Start, stop and manage scheduled tasks. These are generally triggered by Django
    signals (see signals.py).
'''


import json
import math
from io import BytesIO
from PIL import Image
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from django.db.utils import IntegrityError
from background_task import background
from background_task.models import Task
from common.logger import log
from .models import Source, Media
from .utils import get_remote_image, resize_image_to_height


def delete_index_source_task(source_id):
    task = None
    try:
        # get_task currently returns a QuerySet, but catch DoesNotExist just in case
        task = Task.objects.get_task('sync.tasks.index_source_task', args=(source_id,))
    except Task.DoesNotExist:
        pass
    if task:
        # A scheduled task exists for this Source, delete it
        log.info(f'Deleting Source index task: {task}')
        task.delete()


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
    videos = source.index_media()
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
