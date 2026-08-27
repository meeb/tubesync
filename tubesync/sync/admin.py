from django.contrib import admin
from .models import (
    Source,
    Media,
    Metadata,
    MetadataFormat,
    MediaServer
)


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
    actions = (
        'enable_skip', 'disable_skip',
        'enable_can_download', 'disable_can_download',
    )

    @admin.action(description='Set "skip" for the selected media')
    def enable_skip(self, request, queryset):
        updated = queryset.update(skip=True, manual_skip=True)
        self.message_user(request, f'Set "skip" on {updated} media item(s).')

    @admin.action(description='Unset "skip" for the selected media')
    def disable_skip(self, request, queryset):
        updated = queryset.update(skip=False, manual_skip=False)
        self.message_user(request, f'Unset "skip" on {updated} media item(s).')

    @admin.action(description='Set "can download" for the selected media')
    def enable_can_download(self, request, queryset):
        updated = queryset.update(can_download=True)
        self.message_user(
            request, f'Set "can download" on {updated} media item(s).')

    @admin.action(description='Unset "can download" for the selected media')
    def disable_can_download(self, request, queryset):
        updated = queryset.update(can_download=False)
        self.message_user(
            request, f'Unset "can download" on {updated} media item(s).')


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
