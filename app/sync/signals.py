from django.conf import settings
from django.db.models.signals import pre_save, post_save, pre_delete, post_delete
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _
from background_task.signals import task_failed
from background_task.models import Task
from common.logger import log
from .models import Source, Media
from .tasks import (delete_index_source_task, index_source_task,
                    download_media_thumbnail, map_task_to_instance)
from .utils import delete_file


@receiver(pre_save, sender=Source)
def source_pre_save(sender, instance, **kwargs):
    # Triggered before a source is saved, if the schedule has been updated recreate
    # its indexing task
    try:
        existing_source = Source.objects.get(pk=instance.pk)
    except Source.DoesNotExist:
        # Probably not possible?
        return
    if existing_source.index_schedule != instance.index_schedule:
        # Indexing schedule has changed, recreate the indexing task
        delete_index_source_task(str(instance.pk))
        verbose_name = _('Index media from source "{}"')
        index_source_task(
            str(instance.pk),
            repeat=instance.index_schedule,
            queue=str(instance.pk),
            verbose_name=verbose_name.format(instance.name)
        )


@receiver(post_save, sender=Source)
def source_post_save(sender, instance, created, **kwargs):
    # Triggered after a source is saved
    if created:
        # Create a new indexing task for newly created sources
        delete_index_source_task(str(instance.pk))
        log.info(f'Scheduling media indexing for source: {instance.name}')
        verbose_name = _('Index media from source "{}"')
        index_source_task(
            str(instance.pk),
            repeat=instance.index_schedule,
            queue=str(instance.pk),
            verbose_name=verbose_name.format(instance.name)
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
    delete_index_source_task(str(instance.pk))


@receiver(task_failed, sender=Task)
def task_task_failed(sender, task_id, completed_task, **kwargs):
    # Triggered after a task fails by reaching its max retry attempts
    obj, url = map_task_to_instance(completed_task)
    if isinstance(obj, Source):
        log.error(f'Permanent failure for source: {obj} task: {completed_task}')
        obj.has_failed = True
        obj.save()


@receiver(post_save, sender=Media)
def media_post_save(sender, instance, created, **kwargs):
    # Triggered after media is saved
    if created:
        # If the media is newly created start a task to download its thumbnail
        metadata = instance.loaded_metadata
        thumbnail_url = metadata.get('thumbnail', '')
        if thumbnail_url:
            log.info(f'Scheduling task to download thumbnail for: {instance.name} '
                     f'from: {thumbnail_url}')
            verbose_name = _('Downloading media thumbnail for "{}"')
            download_media_thumbnail(
                str(instance.pk),
                thumbnail_url,
                queue=str(instance.source.pk),
                verbose_name=verbose_name.format(instance.name)
            )


@receiver(post_delete, sender=Media)
def media_post_delete(sender, instance, **kwargs):
    # Triggered after media is deleted, delete media thumbnail
    if instance.thumb:
        log.info(f'Deleting thumbnail for: {instance} path: {instance.thumb.path}')
        delete_file(instance.thumb.path)
