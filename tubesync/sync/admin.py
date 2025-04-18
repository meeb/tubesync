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


@admin.register(Metadata)
class MetadataAdmin(admin.ModelAdmin):

    ordering = ('-created',)
    list_display = ('uuid', 'media', 'site', 'key', 'created', 'retrieved', 'uploaded', 'published')
    readonly_fields = ('uuid', 'created')
    search_fields = ('uuid', 'site', 'key')


@admin.register(MetadataFormat)
class MetadataFormatAdmin(admin.ModelAdmin):

    ordering = ('site', 'key', 'number')
    list_display = ('uuid', 'metadata', 'site', 'key', 'code')
    readonly_fields = ('uuid', 'metadata')
    search_fields = ('uuid', 'site', 'key', 'code')


@admin.register(MediaServer)
class MediaServerAdmin(admin.ModelAdmin):

    ordering = ('host', 'port')
    list_display = ('pk', 'server_type', 'host', 'port', 'use_https', 'verify_https')
    search_fields = ('host',)
