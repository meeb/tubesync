from pathlib import Path
from tempfile import TemporaryDirectory
from django.conf import settings
from django.db.models.signals import pre_save, post_save, pre_delete, post_delete
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _
from background_task.signals import task_failed
from background_task.models import Task
from common.logger import log
from .models import Source, Media, MediaServer
from .tasks import (delete_task_by_source, delete_task_by_media, index_source_task,
                    download_media_thumbnail, download_media_metadata,
                    map_task_to_instance, check_source_directory_exists,
                    download_media, rescan_media_server, download_source_images,
                    save_all_media_for_source, rename_media,
                    get_media_metadata_task, get_media_download_task)
from .utils import delete_file, glob_quote, mkdir_p
from .filtering import filter_media
from .choices import Val, YouTube_SourceType


@receiver(pre_save, sender=Source)
def source_pre_save(sender, instance, **kwargs):
    # Triggered before a source is saved, if the schedule has been updated recreate
    # its indexing task
    try:
        existing_source = Source.objects.get(pk=instance.pk)
    except Source.DoesNotExist:
        log.debug(f'source_pre_save signal: no existing source: {sender} - {instance}')
        return

    existing_dirpath = existing_source.directory_path.resolve(strict=True)
    new_dirpath = instance.directory_path.resolve(strict=False)
    if existing_dirpath != new_dirpath:
        path_name = lambda p: p.name
        relative_dir = existing_source.directory
        rd_parents = Path(relative_dir).parents
        rd_parents_set = set(map(path_name, rd_parents))
        ad_parents = existing_dirpath.parents
        ad_parents_set = set(map(path_name, ad_parents))
        # the names in the relative path are also in the absolute path
        parents_count = len(ad_parents_set.intersection(rd_parents_set))
        work_directory = existing_dirpath
        for _count in range(parents_count, 0, -1):
            work_directory = work_directory.parent
        if Path(existing_dirpath.root).resolve(strict=True) == Path(work_directory).resolve(strict=True):
            work_directory = Path('/downloads')
        with TemporaryDirectory(suffix=('.'+new_dirpath.name), prefix='.tmp.', dir=work_directory) as tmp_dir:
            tmp_dirpath = Path(tmp_dir)
            existed = None
            previous = existing_dirpath.rename(tmp_dirpath / 'previous')
            try:
                if new_dirpath.exists():
                    existed = new_dirpath.rename(tmp_dirpath / 'existed')
                mkdir_p(new_dirpath.parent)
                previous.rename(new_dirpath)
            except Exception:
                # try to preserve the directory, if anything went wrong
                previous.rename(existing_dirpath)
                raise
            else:
                existing_dirpath = previous = None
            if existed and existed.is_dir():
                existed = existed.rename(new_dirpath / '.existed')
                for entry_path in existed.iterdir():
                    try:
                        target = new_dirpath / entry_path.name
                        if not target.exists():
                            entry_path = entry_path.rename(target)
                    except Exception as e:
                        log.exception(e)
                try:
                    existed.rmdir()
                except Exception as e:
                    log.exception(e)
            elif existed:
                try:
                    existed = existed.rename(new_dirpath / ('.existed-' + new_dirpath.name))
                except Exception as e:
                    log.exception(e)

    recreate_index_source_task = (
        existing_source.name != instance.name or
        existing_source.index_schedule != instance.index_schedule
    )
    if recreate_index_source_task:
        # Indexing schedule has changed, recreate the indexing task
        delete_task_by_source('sync.tasks.index_source_task', instance.pk)
        verbose_name = _('Index media from source "{}"')
        index_source_task(
            str(instance.pk),
            schedule=instance.index_schedule,
            repeat=instance.index_schedule,
            queue=str(instance.pk),
            priority=10,
            verbose_name=verbose_name.format(instance.name),
            remove_existing_tasks=True
        )


@receiver(post_save, sender=Source)
def source_post_save(sender, instance, created, **kwargs):
    # Check directory exists and create an indexing task for newly created sources
    if created:
        verbose_name = _('Check download directory exists for source "{}"')
        check_source_directory_exists(
            str(instance.pk),
            priority=0,
            verbose_name=verbose_name.format(instance.name)
        )
        if instance.source_type != Val(YouTube_SourceType.PLAYLIST) and instance.copy_channel_images:
            download_source_images(
                str(instance.pk),
                priority=5,
                verbose_name=verbose_name.format(instance.name)
            )
        if instance.index_schedule > 0:
            delete_task_by_source('sync.tasks.index_source_task', instance.pk)
            log.info(f'Scheduling first media indexing for source: {instance.name}')
            verbose_name = _('Index media from source "{}"')
            index_source_task(
                str(instance.pk),
                schedule=600,
                repeat=instance.index_schedule,
                queue=str(instance.pk),
                priority=10,
                verbose_name=verbose_name.format(instance.name),
                remove_existing_tasks=True
            )

    verbose_name = _('Checking all media for source "{}"')
    save_all_media_for_source(
        str(instance.pk),
        priority=25,
        verbose_name=verbose_name.format(instance.name),
        remove_existing_tasks=True
    )


@receiver(pre_delete, sender=Source)
def source_pre_delete(sender, instance, **kwargs):
    # Triggered before a source is deleted, delete all media objects to trigger
    # the Media models post_delete signal
    for media in Media.objects.filter(source=instance):
        log.info(f'Deleting media for source: {instance.name} item: {media.name}')
        media.delete()


@receiver(post_delete, sender=Source)
def source_post_delete(sender, instance, **kwargs):
    # Triggered after a source is deleted
    log.info(f'Deleting tasks for source: {instance.name}')
    delete_task_by_source('sync.tasks.index_source_task', instance.pk)


@receiver(task_failed, sender=Task)
def task_task_failed(sender, task_id, completed_task, **kwargs):
    # Triggered after a task fails by reaching its max retry attempts
    obj, url = map_task_to_instance(completed_task)
    if isinstance(obj, Source):
        log.error(f'Permanent failure for source: {obj} task: {completed_task}')
        obj.has_failed = True
        obj.save()

    if isinstance(obj, Media) and completed_task.task_name == "sync.tasks.download_media_metadata":
        log.error(f'Permanent failure for media: {obj} task: {completed_task}')
        obj.skip = True
        obj.save()

@receiver(post_save, sender=Media)
def media_post_save(sender, instance, created, **kwargs):
    media = instance
    # If the media is skipped manually, bail.
    if instance.manual_skip:
        return
    # Triggered after media is saved
    skip_changed = False
    can_download_changed = False
    # Reset the skip flag if the download cap has changed if the media has not
    # already been downloaded
    downloaded = instance.downloaded
    existing_media_metadata_task = get_media_metadata_task(str(instance.pk))
    existing_media_download_task = get_media_download_task(str(instance.pk))
    if not downloaded:
        # the decision to download was already made if a download task exists
        if not existing_media_download_task:
            # Recalculate the "can_download" flag, this may
            # need to change if the source specifications have been changed
            if instance.metadata:
                if instance.get_format_str():
                    if not instance.can_download:
                        instance.can_download = True
                        can_download_changed = True
                    else:
                        if instance.can_download:
                            instance.can_download = False
                            can_download_changed = True
            # Recalculate the "skip_changed" flag
            skip_changed = filter_media(instance)
    else:
        # Downloaded media might need to be renamed
        # Check settings before any rename tasks are scheduled
        rename_sources_setting = settings.RENAME_SOURCES or list()
        create_rename_task = (
            (
                media.source.directory and
                media.source.directory in rename_sources_setting
            ) or
            settings.RENAME_ALL_SOURCES
        )
        if create_rename_task:
            verbose_name = _('Renaming media for: {}: "{}"')
            rename_media(
                str(media.pk),
                queue=str(media.pk),
                priority=20,
                verbose_name=verbose_name.format(media.key, media.name),
                remove_existing_tasks=True
            )

    # If the media is missing metadata schedule it to be downloaded
    if not (instance.skip or instance.metadata or existing_media_metadata_task):
        log.info(f'Scheduling task to download metadata for: {instance.url}')
        verbose_name = _('Downloading metadata for "{}"')
        download_media_metadata(
            str(instance.pk),
            priority=10,
            verbose_name=verbose_name.format(instance.pk),
            remove_existing_tasks=True
        )
    # If the media is missing a thumbnail schedule it to be downloaded (unless we are skipping this media)
    if not instance.thumb_file_exists:
        instance.thumb = None
    if not instance.thumb and not instance.skip:
        thumbnail_url = instance.thumbnail
        if thumbnail_url:
            log.info(f'Scheduling task to download thumbnail for: {instance.name} '
                     f'from: {thumbnail_url}')
            verbose_name = _('Downloading thumbnail for "{}"')
            download_media_thumbnail(
                str(instance.pk),
                thumbnail_url,
                queue=str(instance.source.pk),
                priority=15,
                verbose_name=verbose_name.format(instance.name),
                remove_existing_tasks=True
            )
    # If the media has not yet been downloaded schedule it to be downloaded
    if not (instance.media_file_exists or instance.filepath.exists() or existing_media_download_task):
        # The file was deleted after it was downloaded, skip this media.
        if instance.can_download and instance.downloaded:
            skip_changed = True != instance.skip
            instance.skip = True
        downloaded = False
    if (instance.source.download_media and instance.can_download) and not (
        instance.skip or downloaded or existing_media_download_task):
        verbose_name = _('Downloading media for "{}"')
        download_media(
            str(instance.pk),
            queue=str(instance.source.pk),
            priority=15,
            verbose_name=verbose_name.format(instance.name),
            remove_existing_tasks=True
        )
    # Save the instance if any changes were required
    if skip_changed or can_download_changed:
        post_save.disconnect(media_post_save, sender=Media)
        instance.save()
        post_save.connect(media_post_save, sender=Media)


@receiver(pre_delete, sender=Media)
def media_pre_delete(sender, instance, **kwargs):
    # Triggered before media is deleted, delete any unlocked scheduled tasks
    log.info(f'Deleting tasks for media: {instance.name}')
    delete_task_by_media('sync.tasks.download_media', (str(instance.pk),))
    delete_task_by_media('sync.tasks.download_media_metadata', (str(instance.pk),))
    delete_task_by_media('sync.tasks.rename_media', (str(instance.pk),))
    delete_task_by_media('sync.tasks.wait_for_media_premiere', (str(instance.pk),))
    thumbnail_url = instance.thumbnail
    if thumbnail_url:
        delete_task_by_media('sync.tasks.download_media_thumbnail',
                             (str(instance.pk), thumbnail_url))
    # Remove thumbnail file for deleted media
    if instance.thumb:
        instance.thumb.delete(save=False)


@receiver(post_delete, sender=Media)
def media_post_delete(sender, instance, **kwargs):
    # Remove the video file, when configured to do so
    if instance.source.delete_files_on_disk and instance.media_file:
        video_path = Path(str(instance.media_file.path)).resolve(strict=False)
        instance.media_file.delete(save=False)
        # the other files we created have these known suffixes
        for suffix in frozenset(('nfo', 'jpg', 'webp', 'info.json',)):
            other_path = video_path.with_suffix(f'.{suffix}').resolve(strict=False)
            if other_path.is_file():
                log.info(f'Deleting file for: {instance} path: {other_path!s}')
                delete_file(other_path)
        # subtitles include language code
        subtitle_files = video_path.parent.glob(f'{glob_quote(video_path.with_suffix("").name)}*.vtt')
        for file in subtitle_files:
            log.info(f'Deleting file for: {instance} path: {file}')
            delete_file(file)
        # Jellyfin creates .trickplay directories and posters
        for suffix in frozenset(('.trickplay', '-poster.jpg', '-poster.webp',)):
            # with_suffix insists on suffix beginning with '.' for no good reason
            other_path = Path(str(video_path.with_suffix('')) + suffix).resolve(strict=False)
            if other_path.is_file():
                log.info(f'Deleting file for: {instance} path: {other_path!s}')
                delete_file(other_path)
            elif other_path.is_dir():
                # Delete the contents of the directory
                paths = list(other_path.rglob('*'))
                attempts = len(paths)
                while paths and attempts > 0:
                    attempts -= 1
                    # delete files first
                    for p in list(filter(lambda x: x.is_file(), paths)):
                        log.info(f'Deleting file for: {instance} path: {p!s}')
                        delete_file(p)
                    # refresh the list
                    paths = list(other_path.rglob('*'))
                    # delete directories
                    # a directory with a subdirectory will fail
                    # we loop to try removing each of them
                    # a/b/c: c then b then a, 3 times around the loop
                    for p in list(filter(lambda x: x.is_dir(), paths)):
                        try:
                            p.rmdir()
                            log.info(f'Deleted directory for: {instance} path: {p!s}')
                        except OSError as e:
                            pass
                # Delete the directory itself
                try:
                    other_path.rmdir()
                    log.info(f'Deleted directory for: {instance} path: {other_path!s}')
                except OSError as e:
                    pass
        # Get all files that start with the bare file path
        all_related_files = video_path.parent.glob(f'{glob_quote(video_path.with_suffix("").name)}*')
        for file in all_related_files:
            log.info(f'Deleting file for: {instance} path: {file}')
            delete_file(file)

    # Schedule a task to update media servers
    for mediaserver in MediaServer.objects.all():
        log.info(f'Scheduling media server updates')
        verbose_name = _('Request media server rescan for "{}"')
        rescan_media_server(
            str(mediaserver.pk),
            schedule=5,
            priority=0,
            verbose_name=verbose_name.format(mediaserver),
            remove_existing_tasks=True
        )

