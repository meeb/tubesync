from django.conf import settings
from django.contrib import admin
from common.utils import django_queryset_generator as qs_gen
from .models import (
    Source,
    Media,
    Metadata,
    MetadataFormat,
    MediaServer
)
from .tasks import save_media


@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):

    ordering = ('-created',)
    list_display = ('uuid', 'name', 'source_type', 'last_crawl',
                    'download_media', 'has_failed')
    readonly_fields = ('uuid', 'created')
    search_fields = ('uuid', 'key', 'name')


@admin.register(Media)
class MediaAdmin(admin.ModelAdmin):

    ordering = ('-created',)
    list_display = ('uuid', 'key', 'source', 'can_download', 'skip', 'downloaded')
    readonly_fields = ('uuid', 'created')
    search_fields = ('uuid', 'source__key', 'key')
    list_filter = ('can_download', 'skip', 'downloaded')
    # https://docs.djangoproject.com/en/6.0/ref/contrib/admin/actions/
    actions = (
        'clear_metadata',
        'enable_skip', 'disable_skip',
        'enable_can_download', 'disable_can_download',
        'redownload',
    )

    def _queue_save_media_tasks(self, queryset):
        '''
            Optionally queue a `save_media` task per changed item, so flags
            are re-evaluated without waiting for the next source edit/index.
            Disabled by default: SAVE_MEDIA_AFTER_BULK_ACTION = True enables it.
        '''
        if not getattr(settings, 'SAVE_MEDIA_AFTER_BULK_ACTION', False):
            return
        save_media.map(
            str(media_uuid)
            for media_uuid in queryset.distinct().values_list('uuid', flat=True).iterator()
        )

    @admin.action(description='Set "skip" for the selected media')
    def enable_skip(self, request, queryset):
        updated = queryset.update(skip=True, manual_skip=True)
        self._queue_save_media_tasks(queryset)
        self.message_user(request, f'Set "skip" on {updated} media item(s).')

    @admin.action(description='Unset "skip" for the selected media')
    def disable_skip(self, request, queryset):
        updated = queryset.update(skip=False, manual_skip=False)
        self._queue_save_media_tasks(queryset)
        self.message_user(request, f'Unset "skip" on {updated} media item(s).')

    @admin.action(description='Set "can download" for the selected media')
    def enable_can_download(self, request, queryset):
        updated = queryset.update(can_download=True)
        self._queue_save_media_tasks(queryset)
        self.message_user(
            request, f'Set "can download" on {updated} media item(s).')

    @admin.action(description='Unset "can download" for the selected media')
    def disable_can_download(self, request, queryset):
        updated = queryset.update(can_download=False)
        self._queue_save_media_tasks(queryset)
        self.message_user(
            request, f'Unset "can download" on {updated} media item(s).')

    @admin.action(description='Clear all metadata from the selected Media instances')
    def clear_metadata(self, request, queryset):
        # clear the metadata
        updated = 0
        for media in qs_gen(queryset):
            media.metadata_clear(save=True)
            updated += 1
        self._queue_save_media_tasks(queryset)
        self.message_user(
            request, f'Cleared metadata from {updated} media item(s).')

    @admin.action(description='Unset "downloaded" for the selected media')
    def redownload(self, request, queryset):
        # unset skip, manual_skip and downloaded
        updated = queryset.update(skip=False, manual_skip=False, downloaded=False)
        self._queue_save_media_tasks(queryset)
        self.message_user(
            request, f'Unset "downloaded" on {updated} media item(s).')


@admin.register(Metadata)
class MetadataAdmin(admin.ModelAdmin):

    ordering = ('-retrieved', '-created', '-uploaded')
    list_display = ('uuid', 'key', 'retrieved', 'uploaded', 'created', 'site')
    readonly_fields = ('uuid', 'created', 'retrieved')
    search_fields = ('uuid', 'media__uuid', 'key')


@admin.register(MetadataFormat)
class MetadataFormatAdmin(admin.ModelAdmin):

    ordering = ('site', 'key', 'number')
    list_display = ('uuid', 'key', 'site', 'number', 'metadata')
    readonly_fields = ('uuid', 'metadata', 'site', 'key', 'number')
    search_fields = ('uuid', 'metadata__uuid', 'metadata__media__uuid', 'key')


@admin.register(MediaServer)
class MediaServerAdmin(admin.ModelAdmin):

    ordering = ('host', 'port')
    list_display = ('pk', 'server_type', 'host', 'port', 'use_https', 'verify_https')
    search_fields = ('host',)
