'''
    Start, stop and manage scheduled tasks. These are generally triggered by Django
    signals (see signals.py).
'''


import os
import json
import random
import requests
import time
import uuid
from collections import deque as queue
from io import BytesIO
from hashlib import sha1
from pathlib import Path
from datetime import timedelta
from shutil import copyfile, rmtree
from django import db
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError
from django.db.transaction import atomic
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from background_task import background
from background_task.exceptions import InvalidTaskError
from background_task.models import Task, CompletedTask
from common.logger import log
from common.errors import ( NoFormatException, NoMediaException,
                            NoThumbnailException,
                            DownloadFailedException, )
from common.utils import (  django_queryset_generator as qs_gen,
                            remove_enclosed, )
from .choices import Val, TaskQueue
from .models import Source, Media, MediaServer, Metadata
from .utils import ( get_remote_image, resize_image_to_height,
                    write_text_file, filter_response, seconds_to_timestr, )
from .youtube import YouTubeError

db_vendor = db.connection.vendor


def get_hash(task_name, pk):
    '''
        Create a background_task compatible hash for a Task or CompletedTask.
    '''
    task_params = json.dumps(((str(pk),), {}), sort_keys=True)
    return sha1(f'{task_name}{task_params}'.encode('utf-8')).hexdigest()


def map_task_to_instance(task):
    '''
        Reverse-maps a scheduled backgrond task to an instance. Requires the task name
        to be a known task function and the first argument to be a UUID. This is used
        because UUID's are incompatible with background_task's "creator" feature.
    '''
    TASK_MAP = {
        'sync.tasks.migrate_to_metadata': Media,
        'sync.tasks.index_source_task': Source,
        'sync.tasks.check_source_directory_exists': Source,
        'sync.tasks.download_media_thumbnail': Media,
        'sync.tasks.download_media': Media,
        'sync.tasks.download_media_metadata': Media,
        'sync.tasks.save_all_media_for_source': Source,
        'sync.tasks.refresh_formats': Media,
        'sync.tasks.rename_media': Media,
        'sync.tasks.rename_all_media_for_source': Source,
        'sync.tasks.wait_for_media_premiere': Media,
        'sync.tasks.delete_all_media_for_source': Source,
    }
    MODEL_URL_MAP = {
        Source: 'sync:source',
        Media: 'sync:media-item',
    }
    # Unpack
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
        Extract an error message from a failed task. This is the last line of the
        last_error field with the method name removed.
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


def update_task_status(task, status):
    if not task:
        return False
    if not hasattr(task, '_verbose_name'):
        task._verbose_name = remove_enclosed(
            task.verbose_name, '[', ']', ' ',
        )
    if status is None:
        task.verbose_name = task._verbose_name
    else:
        task.verbose_name = f'[{status}] {task._verbose_name}'
    try:
        task.save(update_fields={'verbose_name'})
    except DatabaseError as e:
        if 'Save with update_fields did not affect any rows.' == str(e):
            pass
        else:
            raise
    return True


def get_source_completed_tasks(source_id, only_errors=False):
    '''
        Returns a queryset of CompletedTask objects for a source by source ID.
    '''
    q = {'task_params__istartswith': f'[["{source_id}"'}
    if only_errors:
        q['failed_at__isnull'] = False
    return CompletedTask.objects.filter(**q).order_by('-failed_at')


def get_tasks(task_name, id=None, /, instance=None):
    assert not (id is None and instance is None)
    arg = str(id or instance.pk)
    return Task.objects.get_task(str(task_name), args=(arg,),)

def get_first_task(task_name, id=None, /, *, instance=None):
    tqs = get_tasks(task_name, id, instance).order_by('run_at')
    return tqs[0] if tqs.count() else False

def get_media_download_task(media_id):
    return get_first_task('sync.tasks.download_media', media_id)

def get_media_metadata_task(media_id):
    return get_first_task('sync.tasks.download_media_metadata', media_id)

def get_media_premiere_task(media_id):
    return get_first_task('sync.tasks.wait_for_media_premiere', media_id)

def get_source_check_task(source_id):
    return get_first_task('sync.tasks.save_all_media_for_source', source_id)

def get_source_index_task(source_id):
    return get_first_task('sync.tasks.index_source_task', source_id)


def delete_task_by_source(task_name, source_id):
    now = timezone.now()
    unlocked = Task.objects.unlocked(now)
    qs = unlocked.filter(
        task_name=task_name,
        task_params__istartswith=f'[["{source_id}"',
    )
    return qs.delete()


def delete_task_by_media(task_name, args):
    max_run_time = getattr(settings, 'MAX_RUN_TIME', 3600)
    now = timezone.now()
    expires_at = now - timedelta(seconds=max_run_time)
    task_qs = Task.objects.get_task(task_name, args=args)
    unlocked = task_qs.filter(locked_by=None) | task_qs.filter(locked_at__lt=expires_at)
    return unlocked.delete()


def cleanup_completed_tasks():
    days_to_keep = getattr(settings, 'COMPLETED_TASKS_DAYS_TO_KEEP', 30)
    delta = timezone.now() - timedelta(days=days_to_keep)
    log.info(f'Deleting completed tasks older than {days_to_keep} days '
             f'(run_at before {delta})')
    CompletedTask.objects.filter(run_at__lt=delta).delete()


@atomic(durable=False)
def migrate_queues():
    tqs = Task.objects.all()
    qs = tqs.exclude(queue__in=TaskQueue.values)
    return qs.update(queue=Val(TaskQueue.NET))


def save_model(instance):
    if 'sqlite' != db_vendor:
        with atomic(durable=False):
            instance.save()
        return

    # work around for SQLite and its many
    # "database is locked" errors
    with atomic(durable=False):
        instance.save()
    arg = getattr(settings, 'SQLITE_DELAY_FLOAT', 1.5)
    time.sleep(random.expovariate(arg))


@atomic(durable=False)
def schedule_media_servers_update():
    # Schedule a task to update media servers
    log.info('Scheduling media server updates')
    verbose_name = _('Request media server rescan for "{}"')
    for mediaserver in MediaServer.objects.all():
        rescan_media_server(
            str(mediaserver.pk),
            verbose_name=verbose_name.format(mediaserver),
        )


def wait_for_errors(model, /, *, task_name=None):
    if task_name is None:
        task_name=tuple((
            'sync.tasks.download_media',
            'sync.tasks.download_media_metadata',
        ))
    elif isinstance(task_name, str):
        task_name = tuple((task_name,))
    tasks = list()
    for tn in task_name:
        ft = get_first_task(tn, instance=model)
        if ft:
            tasks.append(ft)
    window = timezone.timedelta(hours=3) + timezone.now()
    tqs = Task.objects.filter(
        task_name__in=task_name,
        attempts__gt=0,
        locked_at__isnull=True,
        run_at__lte=window,
        last_error__contains='HTTPError 429: Too Many Requests',
    )
    for task in tasks:
        update_task_status(task, 'paused (429)')
    
    delay = 10 * tqs.count()
    time_str = seconds_to_timestr(delay)
    log.info(f'waiting for errors: 429 ({time_str}): {model}')
    time.sleep(delay)
    for task in tasks:
        update_task_status(task, None)


def cleanup_old_media():
    with atomic():
        for source in qs_gen(Source.objects.filter(delete_old_media=True, days_to_keep__gt=0)):
            delta = timezone.now() - timedelta(days=source.days_to_keep)
            mqs = source.media_source.defer(
                'metadata',
            ).filter(
                downloaded=True,
                download_date__lt=delta,
            )
            for media in qs_gen(mqs):
                log.info(f'Deleting expired media: {source} / {media} '
                         f'(now older than {source.days_to_keep} days / '
                         f'download_date before {delta})')
                with atomic():
                    # .delete() also triggers a pre_delete/post_delete signals that remove files
                    media.delete()
    schedule_media_servers_update()


def cleanup_removed_media(source, video_keys):
    if not source.delete_removed_media:
        return
    log.info(f'Cleaning up media no longer in source: {source}')
    mqs = Media.objects.defer(
        'metadata',
    ).filter(
        source=source,
    )
    for media in qs_gen(mqs):
        if media.key not in video_keys:
            log.info(f'{media.name} is no longer in source, removing')
            with atomic():
                media.delete()
    schedule_media_servers_update()


def save_db_batch(qs, objs, fields, /):
    assert hasattr(qs, 'bulk_update')
    assert callable(qs.bulk_update)
    assert hasattr(objs, '__len__')
    assert callable(objs.__len__)
    assert isinstance(fields, (tuple, list, set, frozenset))

    num_updated = 0
    num_objs = len(objs)
    with atomic(durable=False):
        num_updated = qs.bulk_update(objs=objs, fields=fields)
    if num_objs == num_updated:
        # this covers at least: list, set, deque
        if hasattr(objs, 'clear') and callable(objs.clear):
            objs.clear()
    return num_updated


@background(schedule=dict(priority=20, run_at=60), queue=Val(TaskQueue.DB), remove_existing_tasks=True)
def migrate_to_metadata(media_id):
    try:
        media = Media.objects.get(pk=media_id)
    except Media.DoesNotExist as e:
        # Task triggered but the media no longer exists, do nothing
        log.error(f'Task migrate_to_metadata(pk={media_id}) called but no '
                  f'media exists with ID: {media_id}')
        raise InvalidTaskError(_('no such media')) from e

    try:
        data = Metadata.objects.get(
            media__isnull=True,
            source=media.source,
            key=media.key,
        )
    except Metadata.DoesNotExist as e:
        raise InvalidTaskError(_('no indexed data to migrate to metadata')) from e

    video = data.value
    fields = lambda f, m: m.get_metadata_field(f)
    timestamp = video.get(fields('timestamp', media), None)
    for key in ('epoch', 'availability', 'extractor_key',):
        field = fields(key, media)
        value = video.get(field)
        existing_value = media.get_metadata_first_value(key)
        if value is None:
            if 'epoch' == key:
                value = timestamp
            elif 'extractor_key' == key:
                value = data.site
        if value is not None:
            if existing_value and ('epoch' == key or value == existing_value):
                continue
            media.save_to_metadata(field, value)


@background(schedule=dict(priority=0, run_at=0), queue=Val(TaskQueue.NET), remove_existing_tasks=False)
def wait_for_database_queue():
    while Task.objects.unlocked(timezone.now()).filter(queue=Val(TaskQueue.DB)).count() > 0:
        time.sleep(5)


@background(schedule=dict(priority=20, run_at=30), queue=Val(TaskQueue.NET), remove_existing_tasks=True)
def index_source_task(source_id):
    '''
        Indexes media available from a Source object.
    '''
    db.reset_queries()
    cleanup_completed_tasks()
    # deleting expired media should happen any time an index task is requested
    cleanup_old_media()
    try:
        source = Source.objects.get(pk=source_id)
    except Source.DoesNotExist as e:
        # Task triggered but the Source has been deleted, delete the task
        raise InvalidTaskError(_('no such source')) from e
    # An inactive Source would return an empty list for videos anyway
    if not source.is_active:
        return
    # update the target schedule column
    source.task_run_at_dt
    # Reset any errors
    source.has_failed = False
    # Index the source
    videos = source.index_media()
    if not videos:
        source.has_failed = True
        save_model(source)
        raise NoMediaException(f'Source "{source}" (ID: {source_id}) returned no '
                               f'media to index, is the source key valid? Check the '
                               f'source configuration is correct and that the source '
                               f'is reachable')
    # Got some media, update the last crawl timestamp
    source.last_crawl = timezone.now()
    save_model(source)
    wait_for_database_queue(
        priority=19, # the indexing task uses 20
        verbose_name=_('Waiting for database tasks to complete'),
    )
    wait_for_database_queue(
        priority=29, # the checking task uses 30
        queue=Val(TaskQueue.FS),
        verbose_name=_('Delaying checking all media for database tasks'),
    )
    delete_task_by_source('sync.tasks.save_all_media_for_source', source.pk)
    num_videos = len(videos)
    log.info(f'Found {num_videos} media items for source: {source}')
    tvn_format = '{:,}' + f'/{num_videos:,}'
    db_batch_data = queue(list(), maxlen=50)
    db_fields_data = frozenset((
        'retrieved',
        'site',
        'value',
    ))
    db_batch_media = queue(list(), maxlen=10)
    db_fields_media = frozenset((
        'duration',
        'published',
        'title',
    ))
    fields = lambda f, m: m.get_metadata_field(f)
    task = get_source_index_task(source_id)
    if task:
        task._verbose_name = remove_enclosed(
            task.verbose_name, '[', ']', ' ',
            valid='0123456789/,',
            end=task.verbose_name.find('Index'),
        )
    vn = 0
    video_keys = set()
    while len(videos) > 0:
        vn += 1
        video = videos.popleft()
        # Create or update each video as a Media object
        key = video.get(source.key_field, None)
        if not key:
            # Video has no unique key (ID), it can't be indexed
            continue
        video_keys.add(key)
        if len(db_batch_data) == db_batch_data.maxlen:
            save_db_batch(Metadata.objects, db_batch_data, db_fields_data)
        if len(db_batch_media) == db_batch_media.maxlen:
            save_db_batch(Media.objects, db_batch_media, db_fields_media)
        update_task_status(task, tvn_format.format(vn))
        media_defaults = dict()
        # create a dummy instance to use its functions
        media = Media(source=source, key=key)
        media_defaults['duration'] = float(video.get(fields('duration', media), None) or 0) or None
        media_defaults['title'] = str(video.get(fields('title', media), ''))[:200]
        site = video.get(fields('ie_key', media), None)
        timestamp = video.get(fields('timestamp', media), None)
        try:
            published_dt = media.ts_to_dt(timestamp)
        except AssertionError:
            pass
        else:
            if published_dt:
                media_defaults['published'] = published_dt
        # Retrieve or create the actual media instance
        media, new_media = source.media_source.only(
            'uuid',
            'source',
            'key',
            *db_fields_media,
        ).get_or_create(defaults=media_defaults, source=source, key=key)
        db_batch_media.append(media)
        data, new_data = source.videos.defer('value').filter(
            media__isnull=True,
        ).get_or_create(source=source, key=key)
        if site:
            data.site = site
        data.retrieved = source.last_crawl
        data.value = video
        db_batch_data.append(data)
        vn_fmt = _('Updating metadata from indexing results for: "{}": {}')
        migrate_to_metadata(
            str(media.pk),
            verbose_name=vn_fmt.format(media.key, media.name),
        )
        if not new_media:
            # update the existing media
            for key, value in media_defaults.items():
                setattr(media, key, value)
            log.debug(f'Indexed media: {vn}: {source} / {media}')
        else:
            # log the new media instances
            log.info(f'Indexed new media: {source} / {media}')
            log.info(f'Scheduling tasks to download thumbnail for: {media.key}')
            thumbnail_fmt = 'https://i.ytimg.com/vi/{}/{}default.jpg'
            vn_fmt = _('Downloading {} thumbnail for: "{}": {}')
            for num, prefix in enumerate(('hq', 'sd', 'maxres',)):
                thumbnail_url = thumbnail_fmt.format(
                    media.key,
                    prefix,
                )
                download_media_thumbnail(
                    str(media.pk),
                    thumbnail_url,
                    schedule=dict(run_at=10+(300*num)),
                    verbose_name=vn_fmt.format(prefix, media.key, media.name),
                )
            log.info(f'Scheduling task to download metadata for: {media.url}')
            verbose_name = _('Downloading metadata for: "{}": {}')
            download_media_metadata(
                str(media.pk),
                schedule=dict(priority=35),
                verbose_name=verbose_name.format(media.key, media.name),
            )
    # Reset task.verbose_name to the saved value
    update_task_status(task, None)
    # Update any remaining items in the batches
    save_db_batch(Metadata.objects, db_batch_data, db_fields_data)
    save_db_batch(Media.objects, db_batch_media, db_fields_media)
    # Cleanup of media no longer available from the source
    cleanup_removed_media(source, video_keys)
    # Clear references to indexed data
    videos = video = None
    db_batch_data.clear()
    db_batch_media.clear()
    # Trigger any signals that we skipped with batched updates
    vn_fmt = _('Checking all media for "{}"')
    save_all_media_for_source(
        str(source.pk),
        schedule=dict(run_at=60),
        verbose_name=vn_fmt.format(source.name),
    )


@background(schedule=dict(priority=0, run_at=0), queue=Val(TaskQueue.FS))
def check_source_directory_exists(source_id):
    '''
        Checks the output directory for a source exists and is writable, if it does
        not attempt to create it. This is a task so if there are permission errors
        they are logged as failed tasks.
    '''
    try:
        source = Source.objects.get(pk=source_id)
    except Source.DoesNotExist as e:
        # Task triggered but the Source has been deleted, delete the task
        raise InvalidTaskError(_('no such source')) from e
    # Check the source output directory exists
    if not source.directory_exists():
        # Try to create it
        log.info(f'Creating directory: {source.directory_path}')
        source.make_directory()


@background(schedule=dict(priority=10, run_at=10), queue=Val(TaskQueue.NET))
def download_source_images(source_id):
    '''
        Downloads an image and save it as a local thumbnail attached to a
        Source instance.
    '''
    try:
        source = Source.objects.get(pk=source_id)
    except Source.DoesNotExist as e:
        # Task triggered but the source no longer exists, do nothing
        log.error(f'Task download_source_images(pk={source_id}) called but no '
                  f'source exists with ID: {source_id}')
        raise InvalidTaskError(_('no such source')) from e
    avatar, banner = source.get_image_url
    log.info(f'Thumbnail URL for source with ID: {source_id} / {source} '
        f'Avatar: {avatar} '
        f'Banner: {banner}')
    if banner is not None:
        url = banner
        i = get_remote_image(url)
        image_file = BytesIO()
        i.save(image_file, 'JPEG', quality=85, optimize=True, progressive=True)

        for file_name in ["banner.jpg", "background.jpg"]:
            # Reset file pointer to the beginning for the next save
            image_file.seek(0)
            # Create a Django ContentFile from BytesIO stream
            django_file = ContentFile(image_file.read())
            file_path = source.directory_path / file_name
            with open(file_path, 'wb') as f:
                f.write(django_file.read())
        i = image_file = None

    if avatar is not None:
        url = avatar
        i = get_remote_image(url)
        image_file = BytesIO()
        i.save(image_file, 'JPEG', quality=85, optimize=True, progressive=True)

        for file_name in ["poster.jpg", "season-poster.jpg"]:
            # Reset file pointer to the beginning for the next save
            image_file.seek(0)
            # Create a Django ContentFile from BytesIO stream
            django_file = ContentFile(image_file.read())
            file_path = source.directory_path / file_name
            with open(file_path, 'wb') as f:
                f.write(django_file.read())
        i = image_file = None

    log.info(f'Thumbnail downloaded for source with ID: {source_id} / {source}')


@background(schedule=dict(priority=40, run_at=60), queue=Val(TaskQueue.NET), remove_existing_tasks=True)
def download_media_metadata(media_id):
    '''
        Downloads the metadata for a media item.
    '''
    try:
        media = Media.objects.get(pk=media_id)
    except Media.DoesNotExist as e:
        # Task triggered but the media no longer exists, do nothing
        log.error(f'Task download_media_metadata(pk={media_id}) called but no '
                  f'media exists with ID: {media_id}')
        raise InvalidTaskError(_('no such media')) from e
    if media.manual_skip:
        log.info(f'Task for ID: {media_id} / {media} skipped, due to task being manually skipped.')
        return
    source = media.source
    wait_for_errors(media, task_name='sync.tasks.download_media_metadata')
    try:
        metadata = media.index_metadata()
    except YouTubeError as e:
        e_str = str(e)
        raise_exception = True
        if ': Premieres in ' in e_str:
            now = timezone.now()
            published_datetime = None

            parts = e_str.split(': ', 1)[1].rsplit(' ', 2)
            unit = lambda p: str(p[-1]).lower()
            number = lambda p: int(str(p[-2]), base=10)
            log.debug(parts)
            try:
                if 'days' == unit(parts):
                    published_datetime = now + timedelta(days=number(parts))
                if 'hours' == unit(parts):
                    published_datetime = now + timedelta(hours=number(parts))
                if 'minutes' == unit(parts):
                    published_datetime = now + timedelta(minutes=number(parts))
                log.debug(unit(parts))
                log.debug(number(parts))
            except Exception as ee:
                log.exception(ee)
                pass

            if published_datetime:
                media.published = published_datetime
                media.manual_skip = True
                media.save()
                verbose_name = _('Waiting for the premiere of "{}" at: {}')
                wait_for_media_premiere(
                    str(media.pk),
                    repeat=Task.HOURLY,
                    repeat_until = published_datetime + timedelta(hours=1),
                    verbose_name=verbose_name.format(media.key, published_datetime.isoformat(' ', 'seconds')),
                )
                raise_exception = False
        if raise_exception:
            raise
        log.debug(str(e))
        return
    response = metadata
    if getattr(settings, 'SHRINK_NEW_MEDIA_METADATA', False):
        response = filter_response(metadata, True)
    media.ingest_metadata(response)
    pointer_dict = {'_using_table': True}
    media.metadata = media.metadata_dumps(arg_dict=pointer_dict)
    upload_date = media.upload_date
    # Media must have a valid upload date
    if upload_date:
        media.published = timezone.make_aware(upload_date)
    timestamp = media.get_metadata_first_value(
        ('release_timestamp', 'timestamp',),
        arg_dict=response,
    )
    try:
        published_dt = media.ts_to_dt(timestamp)
    except AssertionError:
        pass
    else:
        if published_dt:
            media.published = published_dt

    # Store title in DB so it's fast to access
    if media.metadata_title:
        media.title = media.metadata_title[:200]

    # Store duration in DB so it's fast to access
    if media.metadata_duration:
        media.duration = media.metadata_duration

    # Don't filter media here, the post_save signal will handle that
    save_model(media)
    log.info(f'Saved {len(media.metadata_dumps())} bytes of metadata for: '
             f'{source} / {media}: {media_id}')


@background(schedule=dict(priority=10, run_at=10), queue=Val(TaskQueue.FS), remove_existing_tasks=True)
def download_media_thumbnail(media_id, url):
    '''
        Downloads an image from a URL and save it as a local thumbnail attached to a
        Media instance.
    '''
    try:
        media = Media.objects.get(pk=media_id)
    except Media.DoesNotExist as e:
        # Task triggered but the media no longer exists, do nothing
        raise InvalidTaskError(_('no such media')) from e
    if media.skip or media.manual_skip:
        # Media was toggled to be skipped after the task was scheduled
        log.warn(f'Download task triggered for media: {media} (UUID: {media.pk}) but '
                 f'it is now marked to be skipped, not downloading thumbnail')
        return
    width = getattr(settings, 'MEDIA_THUMBNAIL_WIDTH', 430)
    height = getattr(settings, 'MEDIA_THUMBNAIL_HEIGHT', 240)
    try:
        try:
            i = get_remote_image(url)
        except requests.HTTPError as re:
            if 404 != re.response.status_code:
                raise
            raise NoThumbnailException(re.response.reason) from re
    except NoThumbnailException as e:
        raise InvalidTaskError(str(e.__cause__)) from e
    if (i.width > width) and (i.height > height):
        log.info(f'Resizing {i.width}x{i.height} thumbnail to '
                 f'{width}x{height}: {url}')
        i = resize_image_to_height(i, width, height)
    image_file = BytesIO()
    i.save(image_file, 'JPEG', quality=85, optimize=True, progressive=True)
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
    i = image_file = None
    log.info(f'Saved thumbnail for: {media} from: {url}')
    # After media is downloaded, copy the updated thumbnail.
    copy_thumbnail = (
        media.downloaded and
        media.source.copy_thumbnails and
        media.thumb_file_exists
    )
    if copy_thumbnail:
        log.info(f'Copying media thumbnail from: {media.thumb.path} '
                 f'to: {media.thumbpath}')
        copyfile(media.thumb.path, media.thumbpath)        
    return True


@background(schedule=dict(priority=30, run_at=60), queue=Val(TaskQueue.NET), remove_existing_tasks=True)
def download_media(media_id, override=False):
    '''
        Downloads the media to disk and attaches it to the Media instance.
    '''
    try:
        media = Media.objects.get(pk=media_id)
    except Media.DoesNotExist as e:
        # Task triggered but the media no longer exists, do nothing
        raise InvalidTaskError(_('no such media')) from e
    else:
        if not media.download_checklist(override):
            # any condition that needs to reschedule the task
            # should raise an exception to avoid this
            return

    wait_for_errors(media, task_name='sync.tasks.download_media')
    filepath = media.filepath
    container = format_str = None
    log.info(f'Downloading media: {media} (UUID: {media.pk}) to: "{filepath}"')
    try:
        format_str, container = media.download_media()
    except NoFormatException as e:
        # Try refreshing formats
        if media.has_metadata:
            log.debug(f'Scheduling a task to refresh metadata for: {media.key}: "{media.name}"')
            refresh_formats(
                str(media.pk),
                verbose_name=f'Refreshing metadata formats for: {media.key}: "{media.name}"',
            )
        log.exception(str(e))
        raise
    else:
        if not os.path.exists(filepath):
            # Try refreshing formats
            if media.has_metadata:
                log.debug(f'Scheduling a task to refresh metadata for: {media.key}: "{media.name}"')
                refresh_formats(
                    str(media.pk),
                    verbose_name=f'Refreshing metadata formats for: {media.key}: "{media.name}"',
                )
            # Expected file doesn't exist on disk
            err = (f'Failed to download media: {media} (UUID: {media.pk}) to disk, '
                   f'expected outfile does not exist: {filepath}')
            log.error(err)
            # Raising an error here triggers the task to be re-attempted (or fail)
            raise DownloadFailedException(err)

        # Media has been downloaded successfully
        media.download_finished(format_str, container, filepath)
        save_model(media)
        # If selected, copy the thumbnail over as well
        if media.source.copy_thumbnails:
            if not media.thumb_file_exists:
                thumbnail_url = media.thumbnail
                if thumbnail_url:
                    args = ( str(media.pk), thumbnail_url, )
                    delete_task_by_media('sync.tasks.download_media_thumbnail', args)
                    if download_media_thumbnail.now(*args):
                        media.refresh_from_db()
            if media.thumb_file_exists:
                log.info(f'Copying media thumbnail from: {media.thumb.path} '
                         f'to: {media.thumbpath}')
                copyfile(media.thumb.path, media.thumbpath)
        # If selected, write an NFO file
        if media.source.write_nfo:
            log.info(f'Writing media NFO file to: {media.nfopath}')
            try:
                write_text_file(media.nfopath, media.nfoxml)
            except PermissionError as e:
                log.warn(f'A permissions problem occured when writing the new media NFO file: {e.msg}')
                pass
        # Schedule a task to update media servers
        schedule_media_servers_update()


@background(schedule=dict(priority=0, run_at=30), queue=Val(TaskQueue.NET), remove_existing_tasks=True)
def rescan_media_server(mediaserver_id):
    '''
        Attempts to request a media rescan on a remote media server.
    '''
    try:
        mediaserver = MediaServer.objects.get(pk=mediaserver_id)
    except MediaServer.DoesNotExist as e:
        # Task triggered but the media server no longer exists, do nothing
        raise InvalidTaskError(_('no such server')) from e
    # Request an rescan / update
    log.info(f'Updating media server: {mediaserver}')
    mediaserver.update()


@background(schedule=dict(priority=30, run_at=600), queue=Val(TaskQueue.FS), remove_existing_tasks=True)
def save_all_media_for_source(source_id):
    '''
        Iterates all media items linked to a source and saves them to
        trigger the post_save signal for every media item. Used when a
        source has its parameters changed and all media needs to be
        checked to see if its download status has changed.
    '''
    db.reset_queries()
    try:
        source = Source.objects.get(pk=source_id)
    except Source.DoesNotExist as e:
        # Task triggered but the source no longer exists, do nothing
        log.error(f'Task save_all_media_for_source(pk={source_id}) called but no '
                  f'source exists with ID: {source_id}')
        raise InvalidTaskError(_('no such source')) from e

    refresh_qs = Media.objects.all().only(
        'pk',
        'uuid',
        'key',
        'title', # for name property
    ).filter(
        source=source,
        can_download=False,
        skip=False,
        manual_skip=False,
        downloaded=False,
        metadata__isnull=False,
    )
    save_qs = Media.objects.all().only(
        'pk',
        'uuid',
    ).filter(
        source=source,
    )
    saved_later = set()
    task = get_source_check_task(source_id)
    if task:
        task._verbose_name = remove_enclosed(
            task.verbose_name, '[', ']', ' ',
            valid='0123456789/,',
            end=task.verbose_name.find('Check'),
        )
    tvn_format = '1/{:,}' + f'/{refresh_qs.count():,}'
    for mn, media in enumerate(qs_gen(refresh_qs), start=1):
        update_task_status(task, tvn_format.format(mn))
        refresh_formats(
            str(media.pk),
            verbose_name=f'Refreshing metadata formats for: {media.key}: "{media.name}"',
        )
        saved_later.add(media.uuid)

    # Keep out of the way of the index task!
    # SQLite will be locked for a while if we start
    # a large source, which reschedules a more costly task.
    if 'sqlite' == db_vendor:
        index_task = get_source_index_task(source_id)
        if index_task and index_task.locked_by_pid_running():
            raise Exception(_('Indexing not completed'))

    # Trigger the post_save signal for each media item linked to this source as various
    # flags may need to be recalculated
    tvn_format = '2/{:,}' + f'/{save_qs.count():,}'
    for mn, media in enumerate(qs_gen(save_qs), start=1):
        if media.uuid not in saved_later:
            update_task_status(task, tvn_format.format(mn))
            save_model(media)
    # Reset task.verbose_name to the saved value
    update_task_status(task, None)


@background(schedule=dict(priority=50, run_at=0), queue=Val(TaskQueue.NET), remove_existing_tasks=True)
def refresh_formats(media_id):
    try:
        media = Media.objects.get(pk=media_id)
    except Media.DoesNotExist as e:
        raise InvalidTaskError(_('no such media')) from e
    try:
        media.refresh_formats
    except YouTubeError as e:
        log.debug(f'Failed to refresh formats for: {media.source} / {media.key}: {e!s}')
        pass
    else:
        save_model(media)


@background(schedule=dict(priority=20, run_at=60), queue=Val(TaskQueue.FS), remove_existing_tasks=True)
def rename_media(media_id):
    try:
        media = Media.objects.get(pk=media_id)
    except Media.DoesNotExist as e:
        raise InvalidTaskError(_('no such media')) from e
    else:
        with atomic():
            media.rename_files()


@background(schedule=dict(priority=20, run_at=300), queue=Val(TaskQueue.FS), remove_existing_tasks=True)
@atomic(durable=True)
def rename_all_media_for_source(source_id):
    try:
        source = Source.objects.get(pk=source_id)
    except Source.DoesNotExist as e:
        # Task triggered but the source no longer exists, do nothing
        log.error(f'Task rename_all_media_for_source(pk={source_id}) called but no '
                  f'source exists with ID: {source_id}')
        raise InvalidTaskError(_('no such source')) from e
    # Check that the settings allow renaming
    rename_sources_setting = getattr(settings, 'RENAME_SOURCES') or list()
    create_rename_tasks = (
        (
            source.directory and
            source.directory in rename_sources_setting
        ) or
        getattr(settings, 'RENAME_ALL_SOURCES', False)
    )
    if not create_rename_tasks:
        return
    mqs = Media.objects.all().filter(
        source=source,
        downloaded=True,
    )
    for media in qs_gen(mqs):
        with atomic():
            media.rename_files()


@background(schedule=dict(priority=0, run_at=60), queue=Val(TaskQueue.DB), remove_existing_tasks=True)
def wait_for_media_premiere(media_id):
    try:
        media = Media.objects.get(pk=media_id)
    except Media.DoesNotExist as e:
        raise InvalidTaskError(_('no such media')) from e
    else:
        valid, hours = media.wait_for_premiere()
        if not valid:
            return
        
        if hours:
            task = get_media_premiere_task(media_id)
            update_task_status(task, f'available in {hours} hours')
        save_model(media)


@background(schedule=dict(priority=1, run_at=90), queue=Val(TaskQueue.FS), remove_existing_tasks=False)
def delete_all_media_for_source(source_id, source_name, source_directory):
    source = None
    assert source_id
    assert source_name
    assert source_directory
    try:
        source = Source.objects.get(pk=source_id)
    except Source.DoesNotExist:
        # Task triggered but the source no longer exists, do nothing
        log.warn(f'Task delete_all_media_for_source(pk={source_id}) called but no '
                  f'source exists with ID: {source_id}')
        #raise InvalidTaskError(_('no such source')) from e
        pass # this task can run after a source was deleted
    mqs = Media.objects.all().defer(
        'metadata',
    ).filter(
        source=source or source_id,
    )
    with atomic(durable=True):
        for media in qs_gen(mqs):
            log.info(f'Deleting media for source: {source_name} item: {media.name}')
            with atomic():
                #media.downloaded = False
                media.skip = True
                media.manual_skip = True
                media.save()
                media.delete()
    # Remove the directory, if the user requested that
    directory_path = Path(source_directory)
    remove = (
        (source and source.delete_removed_media) or
        (directory_path / '.to_be_removed').is_file()
    )
    if source:
        with atomic(durable=True):
            source.delete()
    if remove:
        log.info(f'Deleting directory for: {source_name}: {directory_path}')
        rmtree(directory_path, True)

