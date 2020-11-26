from django.contrib import admin
from .models import Source, Media


@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):

    ordering = ('-created',)
    list_display = ('name',)
    readonly_fields = ('uuid', 'created')
    search_fields = ('uuid', 'key', 'name')


@admin.register(Media)
class MediaAdmin(admin.ModelAdmin):

    ordering = ('-created',)
    list_display = ('key', 'source')
    readonly_fields = ('uuid', 'created')
    search_fields = ('uuid', 'source__key', 'key')
