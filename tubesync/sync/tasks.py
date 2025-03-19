'''
    Start, stop and manage scheduled tasks. These are generally triggered by Django
    signals (see signals.py).
'''


import os
import json
import math
import uuid
from io import BytesIO
from hashlib import sha1
from datetime import datetime, timedelta
from shutil import copyfile
from PIL import Image
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from django.db.transaction import atomic
from django.db.utils import IntegrityError
from django.utils.translation import gettext_lazy as _
from background_task import background
from background_task.models import Task, CompletedTask
from common.logger import log
from common.errors import NoMediaException, NoMetadataException, DownloadFailedException
from common.utils import json_serial
from .models import Source, Media, MediaServer
from .utils import (get_remote_image, resize_image_to_height, delete_file,
                    write_text_file, filter_response)
from .youtube import YouTubeError


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
        'sync.tasks.index_source_task': Source,
        'sync.tasks.check_source_directory_exists': Source,
        'sync.tasks.download_media_thumbnail': Media,
        'sync.tasks.download_media': Media,
        'sync.tasks.download_media_metadata': Media,
        'sync.tasks.save_all_media_for_source': Source,
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


def get_source_completed_tasks(source_id, only_errors=False):
    '''
        Returns a queryset of CompletedTask objects for a source by source ID.
    '''
    q = {'queue': source_id}
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
    return unlocked.filter(task_name=task_name, queue=str(source_id)).delete()


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


def schedule_media_servers_update():
    with atomic():
        # Schedule a task to update media servers
        log.info(f'Scheduling media server updates')
        verbose_name = _('Request media server rescan for "{}"')
        for mediaserver in MediaServer.objects.all():
            rescan_media_server(
                str(mediaserver.pk),
                priority=30,
                verbose_name=verbose_name.format(mediaserver),
                remove_existing_tasks=True,
            )


def cleanup_old_media():
    with atomic():
        for source in Source.objects.filter(delete_old_media=True, days_to_keep__gt=0):
            delta = timezone.now() - timedelta(days=source.days_to_keep)
            for media in source.media_source.filter(downloaded=True, download_date__lt=delta):
                log.info(f'Deleting expired media: {source} / {media} '
                         f'(now older than {source.days_to_keep} days / '
                         f'download_date before {delta})')
                with atomic():
                    # .delete() also triggers a pre_delete/post_delete signals that remove files
                    media.delete()
    schedule_media_servers_update()


def cleanup_removed_media(source, videos):
    if not source.delete_removed_media:
        return
    log.info(f'Cleaning up media no longer in source: {source}')
    media_objects = Media.objects.filter(source=source)
    for media in media_objects:
        matching_source_item = [video['id'] for video in videos if video['id'] == media.key]
        if not matching_source_item:
            log.info(f'{media.name} is no longer in source, removing')
            with atomic():
                media.delete()
    schedule_media_servers_update()


@background(schedule=300, remove_existing_tasks=True)
def index_source_task(source_id):
    '''
        Indexes media available from a Source object.
    '''
    cleanup_completed_tasks()
    # deleting expired media should happen any time an index task is requested
    cleanup_old_media()
    try:
        source = Source.objects.get(pk=source_id)
    except Source.DoesNotExist:
        # Task triggered but the Source has been deleted, delete the task
        return
    # An inactive Source would return an empty list for videos anyway
    if not source.is_active:
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
    num_videos = len(videos)
    log.info(f'Found {num_videos} media items for source: {source}')
    fields = lambda f, m: m.get_metadata_field(f)
    task = get_source_index_task(source_id)
    if task:
        verbose_name = task.verbose_name
        tvn_format = '[{}' + f'/{num_videos}] {verbose_name}'
    for vn, video in enumerate(videos, start=1):
        # Create or update each video as a Media object
        key = video.get(source.key_field, None)
        if not key:
            # Video has no unique key (ID), it can't be indexed
            continue
        try:
            media = Media.objects.get(key=key, source=source)
        except Media.DoesNotExist:
            media = Media(key=key)
        media.source = source
        media.duration = float(video.get(fields('duration', media), None) or 0) or None
        media.title = str(video.get(fields('title', media), ''))[:200]
        timestamp = video.get(fields('timestamp', media), None)
        published_dt = media.metadata_published(timestamp)
        if published_dt is not None:
            media.published = published_dt
        if task:
            task.verbose_name = tvn_format.format(vn)
            with atomic():
                task.save(update_fields={'verbose_name'})
        try:
            media.save()
        except IntegrityError as e:
            log.error(f'Index media failed: {source} / {media} with "{e}"')
        else:
            log.debug(f'Indexed media: {source} / {media}')
            # log the new media instances
            new_media_instance = (
                media.created and
                source.last_crawl and
                media.created >= source.last_crawl
            )
            if new_media_instance:
                log.info(f'Indexed new media: {source} / {media}')
                log.info(f'Scheduling task to download metadata for: {media.url}')
                verbose_name = _('Downloading metadata for "{}"')
                download_media_metadata(
                    str(media.pk),
                    priority=20,
                    verbose_name=verbose_name.format(media.pk),
                )
    if task:
        task.verbose_name = verbose_name
        with atomic():
            task.save(update_fields={'verbose_name'})
    # Cleanup of media no longer available from the source
    cleanup_removed_media(source, videos)


@background(schedule=0)
def check_source_directory_exists(source_id):
    '''
        Checks the output directory for a source exists and is writable, if it does
        not attempt to create it. This is a task so if there are permission errors
        they are logged as failed tasks.
    '''
    try:
        source = Source.objects.get(pk=source_id)
    except Source.DoesNotExist:
        # Task triggered but the Source has been deleted, delete the task
        return
    # Check the source output directory exists
    if not source.directory_exists():
        # Try and create it
        log.info(f'Creating directory: {source.directory_path}')
        source.make_directory()


@background(schedule=0)
def download_source_images(source_id):
    '''
        Downloads an image and save it as a local thumbnail attached to a
        Source instance.
    '''
    try:
        source = Source.objects.get(pk=source_id)
    except Source.DoesNotExist:
        # Task triggered but the source no longer exists, do nothing
        log.error(f'Task download_source_images(pk={source_id}) called but no '
                  f'source exists with ID: {source_id}')
        return
    avatar, banner = source.get_image_url
    log.info(f'Thumbnail URL for source with ID: {source_id} / {source} '
        f'Avatar: {avatar} '
        f'Banner: {banner}')
    if banner != None:
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

    if avatar != None:
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

    log.info(f'Thumbnail downloaded for source with ID: {source_id} / {source}')


@background(schedule=60, remove_existing_tasks=True)
def download_media_metadata(media_id):
    '''
        Downloads the metadata for a media item.
    '''
    try:
        media = Media.objects.get(pk=media_id)
    except Media.DoesNotExist:
        # Task triggered but the media no longer exists, do nothing
        log.error(f'Task download_media_metadata(pk={media_id}) called but no '
                  f'media exists with ID: {media_id}')
        return
    if media.manual_skip:
        log.info(f'Task for ID: {media_id} / {media} skipped, due to task being manually skipped.')
        return
    source = media.source
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
                    priority=0,
                    queue=str(media.pk),
                    repeat=Task.HOURLY,
                    repeat_until = published_datetime + timedelta(hours=1),
                    verbose_name=verbose_name.format(media.key, published_datetime.isoformat(' ', 'seconds')),
                    remove_existing_tasks=True,
                )
                raise_exception = False
        if raise_exception:
            raise
        log.debug(str(e))
        return
    response = metadata
    if getattr(settings, 'SHRINK_NEW_MEDIA_METADATA', False):
        response = filter_response(metadata, True)
    media.metadata = json.dumps(response, separators=(',', ':'), default=json_serial)
    upload_date = media.upload_date
    # Media must have a valid upload date
    if upload_date:
        media.published = timezone.make_aware(upload_date)
    published = media.metadata_published()
    if published:
        media.published = published

    # Store title in DB so it's fast to access
    if media.metadata_title:
        media.title = media.metadata_title[:200]

    # Store duration in DB so it's fast to access
    if media.metadata_duration:
        media.duration = media.metadata_duration

    # Don't filter media here, the post_save signal will handle that
    media.save()
    log.info(f'Saved {len(media.metadata)} bytes of metadata for: '
             f'{source} / {media}: {media_id}')


@background(schedule=60, remove_existing_tasks=True)
def download_media_thumbnail(media_id, url):
    '''
        Downloads an image from a URL and save it as a local thumbnail attached to a
        Media instance.
    '''
    try:
        media = Media.objects.get(pk=media_id)
    except Media.DoesNotExist:
        # Task triggered but the media no longer exists, do nothing
        return
    if not media.has_metadata:
        raise NoMetadataException('Metadata is not yet available.')
    if media.skip:
        # Media was toggled to be skipped after the task was scheduled
        log.warn(f'Download task triggered for media: {media} (UUID: {media.pk}) but '
                 f'it is now marked to be skipped, not downloading thumbnail')
        return
    width = getattr(settings, 'MEDIA_THUMBNAIL_WIDTH', 430)
    height = getattr(settings, 'MEDIA_THUMBNAIL_HEIGHT', 240)
    i = get_remote_image(url)
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
    log.info(f'Saved thumbnail for: {media} from: {url}')
    return True


@background(schedule=60, remove_existing_tasks=True)
def download_media(media_id):
    '''
        Downloads the media to disk and attaches it to the Media instance.
    '''
    try:
        media = Media.objects.get(pk=media_id)
    except Media.DoesNotExist:
        # Task triggered but the media no longer exists, do nothing
        return
    if not media.has_metadata:
        raise NoMetadataException('Metadata is not yet available.')
    if media.skip:
        # Media was toggled to be skipped after the task was scheduled
        log.warn(f'Download task triggered for media: {media} (UUID: {media.pk}) but '
                 f'it is now marked to be skipped, not downloading')
        return
    downloaded_file_exists = (
        media.media_file_exists or
        media.filepath.exists()
    )
    if media.downloaded and downloaded_file_exists:
        # Media has been marked as downloaded before the download_media task was fired,
        # skip it
        log.warn(f'Download task triggered for media: {media} (UUID: {media.pk}) but '
                 f'it has already been marked as downloaded, not downloading again')
        return
    if not media.source.download_media:
        log.warn(f'Download task triggered for media: {media} (UUID: {media.pk}) but '
                 f'the source {media.source} has since been marked to not download, '
                 f'not downloading')
        return
    max_cap_age = media.source.download_cap_date
    published = media.published
    if max_cap_age and published:
        if published <= max_cap_age:
            log.warn(f'Download task triggered media: {media} (UUID: {media.pk}) but '
                     f'the source has a download cap and the media is now too old, '
                     f'not downloading')
            return
    filepath = media.filepath
    log.info(f'Downloading media: {media} (UUID: {media.pk}) to: "{filepath}"')
    format_str, container = media.download_media()
    if os.path.exists(filepath):
        # Media has been downloaded successfully
        log.info(f'Successfully downloaded media: {media} (UUID: {media.pk}) to: '
                 f'"{filepath}"')
        # Link the media file to the object and update info about the download
        media.media_file.name = str(media.source.type_directory_path / media.filename)
        media.downloaded = True
        media.download_date = timezone.now()
        media.downloaded_filesize = os.path.getsize(filepath)
        media.downloaded_container = container
        if '+' in format_str:
            # Seperate audio and video streams
            vformat_code, aformat_code = format_str.split('+')
            aformat = media.get_format_by_code(aformat_code)
            vformat = media.get_format_by_code(vformat_code)
            media.downloaded_format = vformat['format']
            media.downloaded_height = vformat['height']
            media.downloaded_width = vformat['width']
            media.downloaded_audio_codec = aformat['acodec']
            media.downloaded_video_codec = vformat['vcodec']
            media.downloaded_container = container
            media.downloaded_fps = vformat['fps']
            media.downloaded_hdr = vformat['is_hdr']
        else:
            # Combined stream or audio-only stream
            cformat_code = format_str
            cformat = media.get_format_by_code(cformat_code)
            media.downloaded_audio_codec = cformat['acodec']
            if cformat['vcodec']:
                # Combined
                media.downloaded_format = cformat['format']
                media.downloaded_height = cformat['height']
                media.downloaded_width = cformat['width']
                media.downloaded_video_codec = cformat['vcodec']
                media.downloaded_fps = cformat['fps']
                media.downloaded_hdr = cformat['is_hdr']
            else:
                media.downloaded_format = 'audio'
        media.save()
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
        for mediaserver in MediaServer.objects.all():
            log.info(f'Scheduling media server updates')
            verbose_name = _('Request media server rescan for "{}"')
            rescan_media_server(
                str(mediaserver.pk),
                queue=str(media.source.pk),
                priority=0,
                verbose_name=verbose_name.format(mediaserver),
                remove_existing_tasks=True
            )
    else:
        # Expected file doesn't exist on disk
        err = (f'Failed to download media: {media} (UUID: {media.pk}) to disk, '
               f'expected outfile does not exist: {filepath}')
        log.error(err)
        # Try refreshing formats
        if media.has_metadata:
            media.refresh_formats
        # Raising an error here triggers the task to be re-attempted (or fail)
        raise DownloadFailedException(err)


@background(schedule=300, remove_existing_tasks=True)
def rescan_media_server(mediaserver_id):
    '''
        Attempts to request a media rescan on a remote media server.
    '''
    try:
        mediaserver = MediaServer.objects.get(pk=mediaserver_id)
    except MediaServer.DoesNotExist:
        # Task triggered but the media server no longer exists, do nothing
        return
    # Request an rescan / update
    log.info(f'Updating media server: {mediaserver}')
    mediaserver.update()


@background(schedule=300, remove_existing_tasks=True)
def save_all_media_for_source(source_id):
    '''
        Iterates all media items linked to a source and saves them to
        trigger the post_save signal for every media item. Used when a
        source has its parameters changed and all media needs to be
        checked to see if its download status has changed.
    '''
    try:
        source = Source.objects.get(pk=source_id)
    except Source.DoesNotExist:
        # Task triggered but the source no longer exists, do nothing
        log.error(f'Task save_all_media_for_source(pk={source_id}) called but no '
                  f'source exists with ID: {source_id}')
        return

    already_saved = set()
    mqs = Media.objects.filter(source=source)
    task = get_source_check_task(source_id)
    refresh_qs = mqs.filter(
        can_download=False,
        skip=False,
        manual_skip=False,
        downloaded=False,
        metadata__isnull=False,
    )
    if task:
        verbose_name = task.verbose_name
        tvn_format = '[{}' + f'/{refresh_qs.count()}] {verbose_name}'
    for mn, media in enumerate(refresh_qs, start=1):
        if task:
            task.verbose_name = tvn_format.format(mn)
            with atomic():
                task.save(update_fields={'verbose_name'})
        try:
            media.refresh_formats
        except YouTubeError as e:
            log.debug(f'Failed to refresh formats for: {source} / {media.key}: {e!s}')
            pass
        else:
            with atomic():
                media.save()
            already_saved.add(media.uuid)

    # Trigger the post_save signal for each media item linked to this source as various
    # flags may need to be recalculated
    if task:
        tvn_format = '[{}' + f'/{mqs.count()}] {verbose_name}'
    for mn, media in enumerate(mqs, start=1):
        if task:
            task.verbose_name = tvn_format.format(mn)
            with atomic():
                task.save(update_fields={'verbose_name'})
            if media.uuid not in already_saved:
                with atomic():
                    media.save()
    if task:
        task.verbose_name = verbose_name
        with atomic():
            task.save(update_fields={'verbose_name'})


@background(schedule=60, remove_existing_tasks=True)
def rename_media(media_id):
    try:
        media = Media.objects.defer('metadata', 'thumb').get(pk=media_id)
    except Media.DoesNotExist:
        return
    media.rename_files()


@background(schedule=300, remove_existing_tasks=True)
@atomic(durable=True)
def rename_all_media_for_source(source_id):
    try:
        source = Source.objects.get(pk=source_id)
    except Source.DoesNotExist:
        # Task triggered but the source no longer exists, do nothing
        log.error(f'Task rename_all_media_for_source(pk={source_id}) called but no '
                  f'source exists with ID: {source_id}')
        return
    # Check that the settings allow renaming
    rename_sources_setting = settings.RENAME_SOURCES or list()
    create_rename_tasks = (
        (
            source.directory and
            source.directory in rename_sources_setting
        ) or
        settings.RENAME_ALL_SOURCES
    )
    if not create_rename_tasks:
        return
    mqs = Media.objects.all().defer(
        'metadata',
        'thumb',
    ).filter(
        source=source,
        downloaded=True,
    )
    for media in mqs:
        with atomic():
            media.rename_files()


@background(schedule=60, remove_existing_tasks=True)
def wait_for_media_premiere(media_id):
    hours = lambda td: 1+int((24*td.days)+(td.seconds/(60*60)))

    try:
        media = Media.objects.get(pk=media_id)
    except Media.DoesNotExist:
        return
    if media.metadata:
        return
    now = timezone.now()
    if media.published < now:
        media.manual_skip = False
        media.skip = False
        # start the download tasks
        media.save()
    else:
        media.manual_skip = True
        media.title = _(f'Premieres in {hours(media.published - now)} hours')
        media.save()

@background(schedule=300, remove_existing_tasks=False)
def delete_all_media_for_source(source_id, source_name):
    source = None
    try:
        source = Source.objects.get(pk=source_id)
    except Source.DoesNotExist:
        # Task triggered but the source no longer exists, do nothing
        log.error(f'Task delete_all_media_for_source(pk={source_id}) called but no '
                  f'source exists with ID: {source_id}')
        pass
    mqs = Media.objects.all().defer(
        'metadata',
    ).filter(
        source=source or source_id,
    )
    for media in mqs:
        log.info(f'Deleting media for source: {source_name} item: {media.name}')
        with atomic():
            media.delete()

