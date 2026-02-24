from django.contrib import admin
from common.utils import django_queryset_generator as qs_gen
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

    # https://docs.djangoproject.com/en/5.2/ref/contrib/admin/actions/
    actions = ['clear_metadata', 'redownload', 'skip', 'unskip']
    ordering = ('-created',)
    list_display = ('uuid', 'key', 'source', 'can_download', 'skip', 'downloaded')
    readonly_fields = ('uuid', 'created')
    search_fields = ('uuid', 'source__key', 'key')

    @admin.action(description='Clear metadata from selected Media instances')
    def clear_metadata(self, request, queryset):
        # clear the metadata
        for media in qs_gen(queryset):
            media.metadata_clear(save=True)

    @admin.action(description='Redownload selected Media instances')
    def redownload(self, request, queryset):
        # unset skip, manual_skip and downloaded
        queryset.update(skip=False, manual_skip=False, downloaded=False)

    @admin.action(description='Skip selected Media instances')
    def skip(self, request, queryset):
        # set skip and manual_skip
        queryset.update(skip=True, manual_skip=True)

    @admin.action(description='Unskip selected Media instances')
    def unskip(self, request, queryset):
        # unset skip and manual_skip
        queryset.update(skip=False, manual_skip=False)


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
