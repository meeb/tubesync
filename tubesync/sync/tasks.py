'''
    Start, stop and manage scheduled tasks. These are generally triggered by Django
    signals (see signals.py).
'''


import os
import random
import requests
import time
import uuid
from collections import deque as queue
from io import BytesIO
from pathlib import Path
from datetime import timedelta
from shutil import copyfile, rmtree
from django import db
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django_huey import lock_task as huey_lock_task, task as huey_task # noqa
from django_huey import db_periodic_task, db_task, signal as huey_signal
from huey import crontab as huey_crontab, signals as huey_signals
from huey.exceptions import TaskLockedException
from common.huey import CancelExecution, dynamic_retry, register_huey_signals
from common.logger import log
from common.models import TaskHistory
from common.errors import (
    HueyConsumerError,
    DownloadFailedException, FormatUnavailableError,
    NoFormatException, NoMediaException, NoThumbnailException,
)
from common.utils import (  django_queryset_generator as qs_gen,
                            remove_enclosed, seconds_to_timestr, )
from .choices import Val, IndexSchedule, TaskQueue
from .models import Source, Media, MediaServer, Metadata
from .utils import get_remote_image, resize_image_to_height, filter_response
from .youtube import YouTubeError

atomic = db.transaction.atomic
db_vendor = db.connection.vendor
register_huey_signals()


def map_task_to_instance(task):
    '''
        Reverse-maps a scheduled backgrond task to an instance. Requires the task name
        to be a known task function and the first argument to be a UUID. This is used
        because UUID's are incompatible with background_task's "creator" feature.
    '''
    TASK_MAP = {
        'sync.tasks.index_source': Source,
        'sync.tasks.download_media_image': Media,
        'sync.tasks.download_media_file': Media,
        'sync.tasks.download_media_metadata': Media,
        'sync.tasks.save_all_media_for_source': Source,
        'sync.tasks.rename_all_media_for_source': Source,
    }
    MODEL_URL_MAP = {
        Source: 'sync:source',
        Media: 'sync:media-item',
    }
    # Unpack
    task_func = task.name
    model = TASK_MAP.get(task_func, None)
    if not model:
        return None, None
    url = MODEL_URL_MAP.get(model, None)
    if not url:
        return None, None
    task_args = task.task_params
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
    except db.DatabaseError as e:
        if 'Save with update_fields did not affect any rows.' == str(e):
            pass
        else:
            raise
    return True


def get_source_completed_tasks(source_id, only_errors=False):
    '''
        Returns a queryset of TaskHistory objects for a source by source ID.
    '''
    qs = get_model_tasks(source_id)
    if only_errors:
        qs = qs.filter(failed_at__isnull=False)
    return qs.order_by('-failed_at')


def get_model_tasks(model_pk, /, name=None, qs=None):
    if qs is None:
        qs = TaskHistory.objects.all()
    if name is not None:
        qs = qs.filter(name__endswith=name)
    #return qs.filter(task_params__0__0=model_pk)
    return qs.filter(task_params__istartswith=f'[["{model_pk}"')

def get_running_tasks(arg_dt=None, /):
    max_run_time = getattr(settings, 'MAX_RUN_TIME', 3600)
    return TaskHistory.objects.running(
        now=arg_dt,
        within=timezone.timedelta(seconds=max_run_time),
    )

def get_running_tasks_by_name(arg_str, instance_id, /):
    name = arg_str
    if '.' not in name:
        name = f'sync.tasks.{name}'
    tqs = get_model_tasks(instance_id, qs=get_running_tasks())
    return tqs.filter(name=name)

def get_media_download_task(media_id):
    tqs = get_running_tasks_by_name('download_media_file', media_id)
    return tqs[0] if tqs.count() else False
    
def get_media_thumbnail_task(media_id):
    tqs = get_running_tasks_by_name('download_media_image', media_id)
    return tqs[0] if tqs.count() else False

def get_source_index_task(source_id):
    tqs = get_running_tasks_by_name('index_source', source_id)
    return tqs[0] if tqs.count() else False


def get_tasks(task_name, id=None, /, instance=None):
    assert not (id is None and instance is None)
    arg = str(id or instance.pk)
    return get_running_tasks_by_name(str(task_name), arg)

def get_first_task(task_name, id=None, /, *, instance=None):
    tqs = get_tasks(task_name, id, instance).order_by('scheduled_at')
    return tqs[0] if tqs.count() else False

def get_media_metadata_task(media_id):
    return get_first_task('sync.tasks.download_media_metadata', media_id)


def cleanup_completed_tasks():
    days_to_keep = getattr(settings, 'COMPLETED_TASKS_DAYS_TO_KEEP', 30)
    delta = timezone.now() - timedelta(days=days_to_keep)
    log.info(f'Deleting completed tasks older than {days_to_keep} days '
             f'(run_at before {delta})')
    TaskHistory.objects.filter(end_at__lt=delta).delete()


def save_model(instance):
    with atomic(durable=False):
        instance.save()
    if 'sqlite' != db_vendor:
        return

    # work around for SQLite and its many
    # "database is locked" errors
    arg = getattr(settings, 'SQLITE_DELAY_FLOAT', 1.5)
    time.sleep(random.expovariate(arg))


def update_model(instance, **kwargs):
    qs = instance.__class__.objects.all()
    return qs.filter(
        pk=instance.pk,
    ).update(**kwargs)


@db_periodic_task(
    huey_crontab(minute=40, strict=True,),
    priority=100,
    expires=15*60,
    queue=Val(TaskQueue.DB),
)
def upcoming_media():
    qs = Media.objects.filter(
        manual_skip=True,
        published__isnull=False,
        published__gte=(
            # previous hour
            timezone.now() - timezone.timedelta(hours=1, minutes=1)
        ),
    )
    for media in qs_gen(qs):
        valid, hours = media.wait_for_premiere()
        if valid:
            save_model(media)
        log.debug(f'upcoming_media: wait_for_premiere: {media.key}: {valid=} {hours=}')


@db_periodic_task(
    huey_crontab(minute=59, strict=True,),
    priority=100,
    expires=30*60,
    queue=Val(TaskQueue.DB),
)
def schedule_indexing():
    now = timezone.now()
    next_hour = now + timezone.timedelta(hours=1, minutes=1)
    qs = Source.objects.filter(
        index_schedule__gt=Val(IndexSchedule.NEVER),
    )
    for source in qs_gen(qs):
        previous_run = next_hour - timezone.timedelta(
            seconds=source.index_schedule
        )
        skip_source = (
            not source.is_active or
            source.target_schedule >= next_hour or
            (source.last_crawl and source.last_crawl >= previous_run)
        )
        if skip_source:
            continue
        # clear all existing media locks
        media_qs = Media.objects.filter(source=source).only('uuid')
        for media in qs_gen(media_qs):
            huey_lock_task(
                f'media:{media.uuid}',
                queue=Val(TaskQueue.DB),
            ).clear()
        # schedule a new indexing task
        log.info(f'Scheduling an indexing task for source "{source.name}": {source.pk}')
        TaskHistory.schedule(
            index_source,
            str(source.pk),
            delay=300,
            expires=40*60,
            remove_duplicates=True,
            vn_fmt=_('Index media from source "{}"'),
            vn_args=(source.name,),
        )


def schedule_media_servers_update():
    # Schedule a task to update media servers
    log.info('Scheduling media server updates')
    for mediaserver in MediaServer.objects.all():
        rescan_media_server(str(mediaserver.pk))


def contains_http429(q, task_id, /):
    from huey.exceptions import TaskException
    try:
        q.result(preserve=True, id=task_id)
    except TaskException as e:
        return True if 'HTTPError 429: Too Many Requests' in str(e) else False
    return False


def wait_for_errors(model, /, *, queue_name=None, task_name=None):
    if task_name is None:
        task_name=tuple((
            'sync.tasks.download_media_file',
            'sync.tasks.download_media_metadata',
        ))
    elif isinstance(task_name, str):
        task_name = tuple((task_name,))
    tasks = list()
    for tn in task_name:
        ft = get_first_task(tn, instance=model)
        if ft:
            tasks.append(ft)
    for task in tasks:
        update_task_status(task, 'paused (429)')

    total_count = int()
    if queue_name:
        from django_huey import get_queue
        q = get_queue(queue_name)
        total_count += sum([ 1 if contains_http429(q, k) else 0 for k in q.all_results() ])
    delay = 10 * total_count
    time_str = seconds_to_timestr(delay)
    db_down_path = Path('/run/service/huey-database/down')
    fs_down_path = Path('/run/service/huey-filesystem/down')
    log.info(f'waiting for errors: 429 ({time_str}): {model}')
    while delay > 0:
        # this happenes when the container is shutting down
        # do not prevent that while we are delaying a task
        if db_down_path.exists() and fs_down_path.exists():
            break
        time.sleep(5)
        delay -= 5
    for task in tasks:
        update_task_status(task, None)
    if delay > 0:
        raise HueyConsumerError(_('queue consumer stopped'))


@db_task(priority=90, queue=Val(TaskQueue.FS))
def cleanup_old_media(durable=True):
    with atomic(durable=durable):
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
                with atomic(durable=False):
                    # .delete() also triggers a pre_delete/post_delete signals that remove files
                    media.delete()
    schedule_media_servers_update()


@db_task(priority=90, queue=Val(TaskQueue.FS))
def cleanup_removed_media(source_id, video_keys):
    try:
        source = Source.objects.get(pk=source_id)
    except Source.DoesNotExist as e:
        # Task triggered but the Source has been deleted, delete the task
        raise CancelExecution(_('no such source'), retry=False) from e
    if not source.delete_removed_media:
        return
    log.info(f'Cleaning up media no longer in source: {source}')
    mqs = Media.objects.defer(
        'metadata',
    ).filter(
        source=source,
    )
    with atomic(durable=True):
        for media in qs_gen(mqs):
            if media.key not in video_keys:
                log.info(f'{media.name} is no longer in source, removing')
                with atomic(durable=False):
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


@db_task(delay=60, priority=80, retries=10, retry_delay=60, queue=Val(TaskQueue.DB))
def migrate_to_metadata(media_id):
    try:
        media = Media.objects.get(pk=media_id)
    except Media.DoesNotExist as e:
        # Task triggered but the media no longer exists, do nothing
        log.error(f'Task migrate_to_metadata(pk={media_id}) called but no '
                  f'media exists with ID: {media_id}')
        raise CancelExecution(_('no such media'), retry=False) from e

    migrating_lock = huey_lock_task(
        f'index_media:{media.uuid}',
        queue=Val(TaskQueue.FS),
    )
    try:
        data = Metadata.objects.get(
            media__isnull=True,
            source=media.source,
            key=media.key,
        )
    except Metadata.DoesNotExist as e:
        migrating_lock.acquired = False
        raise CancelExecution(_('no indexed data to migrate to metadata'), retry=False) from e

    with huey_lock_task(
        f'media:{media.uuid}',
        queue=Val(TaskQueue.DB),
    ):
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
    migrating_lock.acquired = False


@db_task(delay=30, priority=80, queue=Val(TaskQueue.LIMIT))
def index_source(source_id):
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
        raise CancelExecution(_('no such source'), retry=False) from e
    # An inactive Source would return an empty list for videos anyway
    if not source.is_active:
        return False
    indexing_lock = huey_lock_task(
        f'source:{source.uuid}',
        queue=Val(TaskQueue.FS),
    )
    # be sure that this is locked
    if not indexing_lock.acquired:
        indexing_lock.acquired = True
    # update the target schedule column
    source.task_run_at_dt
    update_model(source, target_schedule=source.target_schedule)
    # Reset any errors
    source.has_failed = False
    # Index the source
    videos = source.index_media()
    if not videos:
        source.has_failed = True
        update_model(source, has_failed=source.has_failed)
        indexing_lock.acquired = False
        raise NoMediaException(f'Source "{source}" (ID: {source_id}) returned no '
                               f'media to index, is the source key valid? Check the '
                               f'source configuration is correct and that the source '
                               f'is reachable')
    # Got some media, update the last crawl timestamp
    source.last_crawl = timezone.now()
    update_model(
        source,
        has_failed=source.has_failed,
        last_crawl=source.last_crawl,
    )
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
        data.value = { k: v for k,v in video.items() if v is not None }
        db_batch_data.append(data)
        migrating_lock = huey_lock_task(
            f'index_media:{media.uuid}',
            queue=Val(TaskQueue.FS),
        )
        if not migrating_lock.acquired:
            migrating_lock.acquired = True
        migrate_to_metadata(str(media.pk))
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
            for num, prefix in enumerate(reversed(('hq', 'sd', 'maxres',))):
                thumbnail_url = thumbnail_fmt.format(
                    media.key,
                    prefix,
                )
                download_media_image.schedule(
                    (str(media.pk), thumbnail_url,),
                    priority=10+(5*num),
                    delay=65-(30*num),
                )
            priority = download_media_metadata.settings.get('default_priority', 50)
            if source.download_media:
                priority += 5
            else:
                priority -= 5
            log.info(f'Scheduling task to download metadata for: {media.url}')
            TaskHistory.schedule(
                download_media_metadata,
                str(media.pk),
                priority=priority,
                remove_duplicates=True,
                vn_fmt=_('Downloading metadata for: "{}": {}'),
                vn_args=(media.key, media.name,),
            )
    # Reset task.verbose_name to the saved value
    update_task_status(task, None)
    # Update any remaining items in the batches
    save_db_batch(Metadata.objects, db_batch_data, db_fields_data)
    save_db_batch(Media.objects, db_batch_media, db_fields_media)
    # Cleanup of media no longer available from the source
    cleanup_removed_media(str(source.pk), video_keys)
    # Clear references to indexed data
    videos = video = None
    db_batch_data.clear()
    db_batch_media.clear()
    # Let the checking task run
    indexing_lock.acquired = False
    # Create the checking task
    TaskHistory.schedule(
        save_all_media_for_source,
        str(source.pk),
        remove_duplicates=True,
        vn_fmt = _('Checking all media for "{}"'),
        vn_args=(
            source.name,
        ),
    )
    return True


@dynamic_retry(db_task, priority=100, retries=15, queue=Val(TaskQueue.FS))
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
        raise CancelExecution(_('no such source'), retry=False) from e
    # Check the source output directory exists
    if not source.directory_exists():
        # Try to create it
        log.info(f'Creating directory: {source.directory_path}')
        source.make_directory()


@dynamic_retry(db_task, delay=10, priority=90, retries=15, queue=Val(TaskQueue.NET))
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
        raise CancelExecution(_('no such source'), retry=False) from e
    avatar, banner, thumbnail = source.get_image_url
    log.info(f'Thumbnail URL for source with ID: {source_id} / {source} '
        f'Avatar: {avatar} '
        f'Banner: {banner} '
        f'Thumbnail: {thumbnail}')
    if thumbnail is not None:
        url = thumbnail
        i = get_remote_image(url)
        image_file = BytesIO()
        i.save(image_file, 'JPEG', quality=85, optimize=True, progressive=True)

        for file_name in ["thumbnail.jpg",]:
            # Reset file pointer to the beginning for the next save
            image_file.seek(0)
            # Create a Django ContentFile from BytesIO stream
            django_file = ContentFile(image_file.read())
            file_path = source.directory_path / file_name
            with open(file_path, 'wb') as f:
                f.write(django_file.read())
        i = image_file = None

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


@db_task(delay=60, priority=90, retries=5, retry_delay=60, queue=Val(TaskQueue.FS))
@atomic(durable=True)
def delete_media(media_id):
    try:
        media = Media.objects.get(pk=media_id)
    except Media.DoesNotExist as e:
        raise CancelExecution(_('no such media'), retry=False) from e
    else:
        migrating_lock = huey_lock_task(
            f'index_media:{media.uuid}',
            queue=Val(TaskQueue.FS),
        )
        if migrating_lock.acquired:
            raise CancelExecution(_('media indexing in progress'), retry=True)
        with huey_lock_task(
            f'media:{media.uuid}',
            queue=Val(TaskQueue.DB),
        ):
            media.delete()


@db_task(delay=60, priority=70, retries=5, retry_delay=60, queue=Val(TaskQueue.FS))
@atomic(durable=True)
def rename_media(media_id):
    try:
        media = Media.objects.get(pk=media_id)
    except Media.DoesNotExist as e:
        raise CancelExecution(_('no such media'), retry=False) from e
    else:
        migrating_lock = huey_lock_task(
            f'index_media:{media.uuid}',
            queue=Val(TaskQueue.FS),
        )
        if migrating_lock.acquired:
            raise CancelExecution(_('media indexing in progress'), retry=True)
        with huey_lock_task(
            f'media:{media.uuid}',
            queue=Val(TaskQueue.DB),
        ):
            media.rename_files()


@db_task(delay=60, priority=80, retries=5, retry_delay=60, queue=Val(TaskQueue.FS))
@atomic(durable=True)
def save_media(media_id):
    try:
        media = Media.objects.get(pk=media_id)
    except Media.DoesNotExist as e:
        raise CancelExecution(_('no such media'), retry=False) from e
    else:
        migrating_lock = huey_lock_task(
            f'index_media:{media.uuid}',
            queue=Val(TaskQueue.FS),
        )
        if migrating_lock.acquired:
            raise CancelExecution(_('media indexing in progress'), retry=True)
        with huey_lock_task(
            f'media:{media.uuid}',
            queue=Val(TaskQueue.DB),
        ):
            save_model(media)


@db_task(delay=60, priority=50, retries=6, retry_delay=3600, queue=Val(TaskQueue.LIMIT))
def upgrade_media(media_id):
    try:
        media = Media.objects.get(pk=media_id)
    except Media.DoesNotExist as e:
        # Task triggered but the media no longer exists, do nothing
        raise CancelExecution(_('no such media'), retry=False) from e
    else:
        if not media.downloaded:
            raise CancelExecution(_('media not downloaded'))
        format_str = media.get_format_str()
        downloaded_dict = media.get_display_format(format_str)
        downloaded_height = downloaded_dict.get('height')
        if not downloaded_height:
            if media.source.is_audio:
                raise CancelExecution(_('upgrading audio is unsupported'), retry=False)
            raise CancelExecution(_('media height not available'))
        media.downloaded = False
        new_dict = media.get_display_format(format_str)
        media.downloaded = True
        format_height = new_dict.get('height')
        if not format_height or format_height <= downloaded_height:
            raise CancelExecution(_('downloaded media is better'))
        download_media_file.call_local(str(media.pk), override=True)

@db_task(delay=60, priority=60, retries=3, retry_delay=600, queue=Val(TaskQueue.LIMIT))
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
        raise CancelExecution(_('no such media'), retry=False) from e
    if media.manual_skip:
        log.info(f'Task for ID: {media_id} / {media} skipped, due to task being manually skipped.')
        return
    source = media.source
    wait_for_errors(
        media,
        queue_name=Val(TaskQueue.LIMIT),
        task_name='sync.tasks.download_media_metadata',
    )
    metadata_lock = huey_lock_task(
        f'index_media:{media.uuid}',
        queue=Val(TaskQueue.FS),
    )
    keep_metadata_lock = False
    try:
        metadata_lock.__enter__()
    except TaskLockedException as e:
        raise CancelExecution(_('media indexing in progress'), retry=True) from e
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
                raise_exception = False
        if raise_exception:
            raise
        log.debug(str(e))
    else:
        keep_metadata_lock = True
    finally:
        metadata_lock.acquired = keep_metadata_lock
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
    try:
        media.save()
    except Exception:
        raise
    else:
        log.info(f'Saved {len(media.metadata_dumps())} bytes of metadata for: '
                 f'{source} / {media}: {media_id}')
    finally:
        metadata_lock.acquired = False


@dynamic_retry(db_task, delay=10, priority=90, retries=15, queue=Val(TaskQueue.NET))
def download_media_image(media_id, url):
    '''
        Downloads an image from a URL and save it as a local thumbnail attached to a
        Media instance.
    '''
    try:
        media = Media.objects.get(pk=media_id)
    except Media.DoesNotExist as e:
        # Task triggered but the media no longer exists, do nothing
        raise CancelExecution(_('no such media'), retry=False) from e
    if media.skip or media.manual_skip:
        # Media was toggled to be skipped after the task was scheduled
        log.warn(f'Download task triggered for media: {media} (UUID: {media.pk}) but '
                 f'it is now marked to be skipped, not downloading thumbnail')
        return False
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
        log.exception(str(e.__cause__))
        return False
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

@huey_signal(huey_signals.SIGNAL_COMPLETE, queue=Val(TaskQueue.NET))
def on_complete_download_media_image(signal_name, task_obj, exception_obj=None, /, *, huey=None):
    assert huey_signals.SIGNAL_COMPLETE == signal_name
    assert huey is not None
    if 'download_media_image' != task_obj.name:
        return
    result = huey.result(preserve=True, id=task_obj.id)
    # clear False/True from the results storage
    if result is False or result is True:
        huey.result(preserve=False, id=task_obj.id)

@db_task(delay=60, priority=70, queue=Val(TaskQueue.LIMIT))
def download_media_file(media_id, override=False):
    '''
        Downloads the media to disk and attaches it to the Media instance.
    '''
    try:
        media = Media.objects.get(pk=media_id)
    except Media.DoesNotExist as e:
        # Task triggered but the media no longer exists, do nothing
        raise CancelExecution(_('no such media'), retry=False) from e
    else:
        if not media.download_checklist(override):
            # any condition that needs to reschedule the task
            # should raise an exception to avoid this
            return

    wait_for_errors(
        media,
        queue_name=Val(TaskQueue.LIMIT),
    )
    with huey_lock_task(
        f'media:{media.uuid}',
        queue=Val(TaskQueue.DB),
    ):
        filepath = media.filepath
        container = format_str = None
        log.info(f'Downloading media: {media} (UUID: {media.pk}) to: "{filepath}"')
        try:
            format_str, container = media.download_media()
        except FormatUnavailableError as e:
            media.failed_format(e.format, cause=e.exc, exc=e)
            raise CancelExecution(_('format did not work'), retry=True) from e.__cause__
        except NoFormatException:
            # Try refreshing formats
            if media.has_metadata:
                log.debug(f'Scheduling a task to refresh metadata for: {media.key}: "{media.name}"')
                TaskHistory.schedule(
                    refresh_formats,
                    str(media.pk),
                    remove_duplicates=True,
                    vn_fmt = _('Refreshing formats for "{}"'),
                    vn_args=(media.key,),
                )
            raise
        else:
            if not os.path.exists(filepath):
                # Try refreshing formats
                if media.has_metadata:
                    log.debug(f'Scheduling a task to refresh metadata for: {media.key}: "{media.name}"')
                    TaskHistory.schedule(
                        refresh_formats,
                        str(media.pk),
                        remove_duplicates=True,
                        vn_fmt = _('Refreshing formats for "{}"'),
                        vn_args=(media.key,),
                    )
                # Expected file doesn't exist on disk
                err = (
                    f'Failed to download media: {media} (UUID: {media.pk}) to disk, '
                    f'expected outfile does not exist: {filepath}'
                )
                log.error(err)
                # Raising an error here triggers the task to be re-attempted (or fail)
                raise DownloadFailedException(err)

            # Media has been downloaded successfully
            media.download_finished(format_str, container, filepath)
            media.save()
            media.rename_files()
            media.copy_thumbnail()
            media.write_nfo_file()
            # Try to download a better format later, if the settings allow this
            if getattr(settings, 'VIDEO_HEIGHT_UPGRADE', False):
                upgrade_media(str(media.pk))
            # Schedule a task to update media servers
            schedule_media_servers_update()


@db_task(delay=30, expires=210, priority=100, queue=Val(TaskQueue.NET))
def rescan_media_server(mediaserver_id):
    '''
        Attempts to request a media rescan on a remote media server.
    '''
    try:
        mediaserver = MediaServer.objects.get(pk=mediaserver_id)
    except MediaServer.DoesNotExist as e:
        # Task triggered but the media server no longer exists, do nothing
        raise CancelExecution(_('no such server'), retry=False) from e
    # Request an rescan / update
    log.info(f'Updating media server: {mediaserver}')
    mediaserver.update()


@dynamic_retry(db_task, backoff_func=lambda n: (n*3600)+600, priority=50, retries=15, queue=Val(TaskQueue.LIMIT))
def refresh_formats(media_id):
    try:
        media = Media.objects.get(pk=media_id)
    except Media.DoesNotExist as e:
        raise CancelExecution(_('no such media'), retry=False) from e
    else:
        wait_for_errors(
            media,
            queue_name=Val(TaskQueue.LIMIT),
        )
        save, retry, msg = media.refresh_formats()
        if save is not True:
            log.warning(f'Refreshing formats for "{media.key}" failed: {msg}')
            exc = CancelExecution(
                _('failed to refresh formats for:'),
                f'{media.key} / {media.uuid}:',
                msg,
                retry=retry,
            )
            # combine the strings
            exc.args = (' '.join(map(str, exc.args)),)
            # store instance details
            exc.instance = dict(
                key=media.key,
                model='Media',
                uuid=str(media.pk),
            )
            # store the function results
            exc.reason = msg
            exc.save = save
            raise exc
        # the metadata has already been saved, trigger the post_save signal
        log.info(f'Saving refreshed formats for "{media.key}": {msg}')
        media.save()


@db_task(delay=300, priority=80, retries=5, retry_delay=600, queue=Val(TaskQueue.FS))
@atomic(durable=True)
def rename_all_media_for_source(source_id):
    try:
        source = Source.objects.get(pk=source_id)
    except Source.DoesNotExist as e:
        # Task triggered but the source no longer exists, do nothing
        log.error(f'Task rename_all_media_for_source(pk={source_id}) called but no '
                  f'source exists with ID: {source_id}')
        raise CancelExecution(_('no such source'), retry=False) from e
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
    mqs = Media.objects.filter(
        source=source,
        downloaded=True,
    )
    for media in qs_gen(mqs):
        migrating_lock = huey_lock_task(
            f'index_media:{media.uuid}',
            queue=Val(TaskQueue.FS),
        )
        if migrating_lock.acquired:
            # good luck to you in the queue!
            rename_media(str(media.pk))
        try:
            with huey_lock_task(
                f'media:{media.uuid}',
                queue=Val(TaskQueue.DB),
            ):
                with atomic(durable=False):
                    media.rename_files()
        except TaskLockedException:
            rename_media(str(media.pk))


@dynamic_retry(db_task, delay=600, priority=70, retries=15, queue=Val(TaskQueue.FS))
@huey_lock_task('sync.tasks.save_all_media_for_source', queue=Val(TaskQueue.FS))
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
        raise CancelExecution(_('no such source'), retry=False) from e

    # Keep out of the way of the index task!
    # SQLite will be locked for a while if we start
    # a large source, which reschedules a more costly task.
    indexing_lock = huey_lock_task(
        f'source:{source.uuid}',
        queue=Val(TaskQueue.FS),
    )
    if indexing_lock.acquired:
        raise CancelExecution(_('source indexing in progress'))

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
    for media in qs_gen(refresh_qs):
        if media.has_metadata:
            saved_later.add(str(media.pk))
            TaskHistory.schedule(
                refresh_formats,
                str(media.pk),
                remove_duplicates=True,
                vn_fmt = _('Refreshing formats for "{}"'),
                vn_args=(media.key,),
            )

    # Trigger the post_save signal for each media item linked to this source as various
    # flags may need to be recalculated
    saved_now = {
        str(media.pk)
        for media in qs_gen(save_qs)
        if str(media.pk) not in saved_later
    }
    save_media.map(saved_now)

    TaskHistory.schedule(
        rename_all_media_for_source,
        str(source.pk),
        remove_duplicates=True,
        vn_fmt = _('Renaming downloaded media from source "{}"'),
        vn_args=(source.name,),
    )


@dynamic_retry(db_task, delay=90, priority=99, queue=Val(TaskQueue.FS))
def delete_all_media_for_source(source_id, source_name, source_directory):
    source = None
    assert source_id
    assert source_name
    assert source_directory
    try:
        source = Source.objects.get(pk=source_id)
    except Source.DoesNotExist:
        # Task triggered but the source no longer exists, do nothing
        log.warning(f'Task delete_all_media_for_source(pk={source_id}) called but no '
                  f'source exists with ID: {source_id}')
        #raise CancelExecution(_('no such source'), retry=False) from e
        pass # this task can run after a source was deleted
    mqs = Media.objects.all().defer(
        'metadata',
    ).filter(
        source=source or source_id,
    )
    delete_media.map({
        str(media.pk)
        for media in qs_gen(mqs)
    })
    with atomic(durable=True):
        mqs.update(manual_skip=True, skip=True)
        log.info(f'Deleting media for source: {source_name}')
        mqs.delete()
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


