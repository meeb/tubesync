'''
    Start, stop and manage scheduled tasks. These are generally triggered by Django
    signals (see signals.py).
'''


import json
from io import BytesIO
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from background_task import background
from background_task.models import Task
from .models import Source, Media
from .utils import get_remote_image


def delete_index_source_task(source_id):
    task = None
    try:
        # get_task currently returns a QuerySet, but catch DoesNotExist just in case
        task = Task.objects.get_task('sync.tasks.index_source_task', args=(source_id,))
    except Task.DoesNotExist:
        pass
    if task:
        # A scheduled task exists for this Source, delete it
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
        media.save()


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
    i = get_remote_image(url)
    max_width, max_height = getattr(settings, 'MAX_MEDIA_THUMBNAIL_SIZE', (512, 512))
    if i.width > max_width or i.height > max_height:
        # Image is larger than we want to save, resize it
        i.thumbnail(size=(max_width, max_height))
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
    return True
