import glob
import os
from base64 import b64decode
import pathlib
import sys
from django.conf import settings
from django.http import FileResponse, Http404, HttpResponseNotFound, HttpResponseRedirect
from django.views.generic import TemplateView, ListView, DetailView
from django.views.generic.edit import (FormView, FormMixin, CreateView, UpdateView,
                                       DeleteView)
from django.views.generic.detail import SingleObjectMixin
from django.core.exceptions import SuspiciousFileOperation
from django.http import HttpResponse
from django.urls import reverse_lazy
from django.db import connection, IntegrityError
from django.db.models import F, Q, Count, Sum, When, Case
from django.forms import Form, ValidationError
from django.utils.text import slugify
from django.utils._os import safe_join
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from common.models import TaskHistory
from common.timestamp import timestamp_to_datetime
from common.utils import append_uri_params, mkdir_p, multi_key_sort
from background_task.models import Task
from django_huey import DJANGO_HUEY, get_queue
from common.huey import h_q_reset_tasks
from .models import Source, Media, MediaServer
from .forms import (ValidateSourceForm, ConfirmDeleteSourceForm, RedownloadMediaForm,
                    SkipMediaForm, EnableMediaForm, ResetTasksForm, ScheduleTaskForm,
                    ConfirmDeleteMediaServerForm, SourceForm)
from .utils import delete_file, validate_url
from .tasks import (
    map_task_to_instance, get_error_message, migrate_queues, delete_task_by_media,
    get_running_tasks, get_media_download_task, get_source_completed_tasks,
    check_source_directory_exists, index_source_task, download_media_image,
)
from .choices import (Val, MediaServerType, SourceResolution, IndexSchedule,
                        YouTube_SourceType, youtube_long_source_types,
                        youtube_help, youtube_validation_urls)
from . import signals # noqa
from . import youtube


def get_waiting_tasks():
    background_task_ids = {
        str(t.pk) for t in Task.objects.all()
    }
    huey_queue_names = (DJANGO_HUEY or {}).get('queues', {})
    huey_queues = list(map(get_queue, huey_queue_names))
    huey_task_ids = {
        str(t.id) for q in huey_queues for t in set(
            q.pending()
        ).union(
            q.scheduled()
        )
    }
    return TaskHistory.objects.filter(
        task_id__in=huey_task_ids.union(background_task_ids),
    )


class DashboardView(TemplateView):
    '''
        The dashboard shows non-interactive totals and summaries.
    '''

    template_name = 'sync/dashboard.html'

    def get_context_data(self, *args, **kwargs):
        data = super().get_context_data(*args, **kwargs)
        data['now'] = timezone.now()
        # Sources
        data['num_sources'] = Source.objects.all().count()
        data['num_video_sources'] = Source.objects.filter(
            ~Q(source_resolution=Val(SourceResolution.AUDIO))
        ).count()
        data['num_audio_sources'] = data['num_sources'] - data['num_video_sources']
        data['num_failed_sources'] = Source.objects.filter(has_failed=True).count()
        # Media
        data['num_media'] = Media.objects.all().count()
        data['num_downloaded_media'] = Media.objects.filter(downloaded=True).count()
        # Tasks
        completed_qs = TaskHistory.objects.filter(
            start_at__isnull=False,
            end_at__gt=F('start_at'),
        )
        waiting_qs = get_waiting_tasks()
        data['num_tasks'] = waiting_qs.count()
        data['num_completed_tasks'] = completed_qs.count()
        # Disk usage
        disk_usage = Media.objects.filter(
            downloaded=True, downloaded_filesize__isnull=False
        ).defer('metadata').aggregate(Sum('downloaded_filesize'))
        data['disk_usage_bytes'] = disk_usage['downloaded_filesize__sum']
        if not data['disk_usage_bytes']:
            data['disk_usage_bytes'] = 0
        if data['disk_usage_bytes'] and data['num_downloaded_media']:
            data['average_bytes_per_media'] = round(data['disk_usage_bytes'] /
                                                    data['num_downloaded_media'])
        else:
            data['average_bytes_per_media'] = 0
        # Latest downloads
        data['latest_downloads'] = Media.objects.filter(
            downloaded=True,
            download_date__isnull=False,
            downloaded_filesize__isnull=False,
        ).defer('metadata').order_by('-download_date')[:10]
        # Largest downloads
        data['largest_downloads'] = Media.objects.filter(
            downloaded=True, downloaded_filesize__isnull=False
        ).defer('metadata').order_by('-downloaded_filesize')[:10]
        # UID and GID
        data['uid'] = os.getuid()
        data['gid'] = os.getgid()
        # Config and download locations
        data['config_dir'] = str(settings.CONFIG_BASE_DIR)
        data['downloads_dir'] = str(settings.DOWNLOAD_ROOT)
        data['database_connection'] = settings.DATABASE_CONNECTION_STR
        # Add the database filesize when using db.sqlite3
        data['database_filesize'] = None
        if 'sqlite' == connection.vendor:
            db_name = str(connection.get_connection_params().get('database', ''))
            db_path = pathlib.Path(db_name) if '/' == db_name[0] else None
            if db_path:
                data['database_filesize'] = db_path.stat().st_size
        return data


class SourcesView(ListView):
    '''
        A bare list of the sources which have been created with their states.
    '''

    template_name = 'sync/sources.html'
    context_object_name = 'sources'
    paginate_by = settings.SOURCES_PER_PAGE
    messages = {
        'source-deleted': _('Your selected source has been deleted.'),
        'source-refreshed': _('The source has been scheduled to be synced now.')
    }

    def get(self, *args, **kwargs):
        if args[0].path.startswith("/source-sync-now/"):
            sobj = Source.objects.get(pk=kwargs["pk"])
            if sobj is None:
                return HttpResponseNotFound()

            source = sobj
            verbose_name = _('Index media from source "{}" once')
            index_source_task(
                str(source.pk),
                remove_existing_tasks=False,
                repeat=0,
                schedule=30,
                verbose_name=verbose_name.format(source.name),
            )
            url = reverse_lazy('sync:sources')
            url = append_uri_params(url, {'message': 'source-refreshed'})
            return HttpResponseRedirect(url)
        else:
            return super().get(self, *args, **kwargs)    

    def __init__(self, *args, **kwargs):
        self.message = None
        super().__init__(*args, **kwargs)

    def dispatch(self, request, *args, **kwargs):
        message_key = request.GET.get('message', '')
        self.message = self.messages.get(message_key, '')
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        all_sources = Source.objects.all().order_by('name')
        return all_sources.annotate(
            media_count=Count('media_source'),
            downloaded_count=Count(Case(When(media_source__downloaded=True, then=1)))
        )

    def get_context_data(self, *args, **kwargs):
        data = super().get_context_data(*args, **kwargs)
        data['message'] = self.message
        return data


class ValidateSourceView(FormView):
    '''
        Validate a URL and prepopulate a create source view form with confirmed
        accurate data. The aim here is to streamline onboarding of new sources
        which otherwise may not be entirely obvious to add, such as the "key"
        being just a playlist ID or some other reasonably opaque internals.
    '''

    template_name = 'sync/source-validate.html'
    form_class = ValidateSourceForm
    errors = {
        'invalid_source': _('Invalid type for the source.'),
        'invalid_url': _('Invalid URL, the URL must for a "{item}" must be in '
                         'the format of "{example}". The error was: {error}.'),
    }
    source_types = youtube_long_source_types
    help_item = dict(YouTube_SourceType.choices)
    help_texts = youtube_help.get('texts')
    help_examples = youtube_help.get('examples')
    validation_urls = youtube_validation_urls
    prepopulate_fields = {
        Val(YouTube_SourceType.CHANNEL): ('source_type', 'key', 'name', 'directory'),
        Val(YouTube_SourceType.CHANNEL_ID): ('source_type', 'key'),
        Val(YouTube_SourceType.PLAYLIST): ('source_type', 'key'),
    }

    def __init__(self, *args, **kwargs):
        self.source_type_str = ''
        self.source_type = None
        self.key = ''
        super().__init__(*args, **kwargs)

    def dispatch(self, request, *args, **kwargs):
        self.source_type_str = kwargs.get('source_type', '').strip().lower()
        self.source_type = self.source_types.get(self.source_type_str, None)
        if not self.source_type:
            raise Http404
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        initial = super().get_initial()
        initial['source_type'] = self.source_type
        return initial

    def get_context_data(self, *args, **kwargs):
        data = super().get_context_data(*args, **kwargs)
        data['source_type'] = self.source_type_str
        data['help_item'] = self.help_item.get(self.source_type)
        data['help_text'] = self.help_texts.get(self.source_type)
        data['help_example'] = self.help_examples.get(self.source_type)
        return data

    def form_valid(self, form):
        # Perform extra validation on the URL, we need to extract the channel name or
        # playlist ID and check they are valid
        source_type = form.cleaned_data['source_type']
        if source_type not in YouTube_SourceType.values:
            form.add_error(
                'source_type',
                ValidationError(self.errors['invalid_source'])
            )
        source_url = form.cleaned_data['source_url']
        validation_url = self.validation_urls.get(source_type)
        try:
            self.key = validate_url(source_url, validation_url)
        except ValidationError as e:
            error = self.errors.get('invalid_url')
            item = self.help_item.get(self.source_type)
            form.add_error(
                'source_url',
                ValidationError(error.format(
                    item=item,
                    example=validation_url['example'],
                    error=e.message)
                )
            )
        if form.errors:
            return super().form_invalid(form)
        return super().form_valid(form)

    def get_success_url(self):
        url = reverse_lazy('sync:add-source')
        fields_to_populate = self.prepopulate_fields.get(self.source_type)
        fields = {}
        value = self.key
        use_channel_id = (
            'youtube-channel' == self.source_type_str and
            '@' == self.key[0]
        )
        if use_channel_id:
            old_key = self.key
            old_source_type = self.source_type
            old_source_type_str = self.source_type_str

            self.source_type_str = 'youtube-channel-id'
            self.source_type = self.source_types.get(self.source_type_str, None)
            index_url = Source.create_index_url(self.source_type, self.key, 'videos')
            try:
                self.key = youtube.get_channel_id(
                    index_url.replace('/channel/', '/')
                )
            except youtube.YouTubeError:
                # It did not work, revert to previous behavior
                self.key = old_key
                self.source_type = old_source_type
                self.source_type_str = old_source_type_str

        for field in fields_to_populate:
            if field == 'source_type':
                fields[field] = self.source_type
            elif field == 'key':
                fields[field] = self.key
            elif field in ('name', 'directory'):
                fields[field] = value
        return append_uri_params(url, fields)


class EditSourceMixin:
    model = Source
    form_class = SourceForm
    errors = {
        'invalid_media_format': _('Invalid media format, the media format contains '
                                  'errors or is empty. Check the table at the end of '
                                  'this page for valid media name variables'),
        'dir_outside_dlroot': _('You cannot specify a directory outside of the '
                                'base directory (%BASEDIR%)')
    }

    def form_valid(self, form: Form):
        # Perform extra validation to make sure the media_format is valid
        obj = form.save(commit=False)
        # temporarily use media_format from the form
        saved_media_format = obj.media_format
        obj.media_format = form.cleaned_data['media_format']
        example_media_file = obj.get_example_media_format()
        obj.media_format = saved_media_format

        if '' == example_media_file:
            form.add_error(
                'media_format',
                ValidationError(self.errors['invalid_media_format'])
            )

        # Check for suspicious file path(s)
        try:
            targetCheck = form.cleaned_data['directory'] + '/.virt'
            safe_join(settings.DOWNLOAD_ROOT, targetCheck)
        except SuspiciousFileOperation:
            form.add_error(
                'directory',
                ValidationError(
                    self.errors['dir_outside_dlroot'].replace(
                        "%BASEDIR%", str(settings.DOWNLOAD_ROOT)
                    )
                ),
            )

        if form.errors:
            return super().form_invalid(form)

        return super().form_valid(form)


class AddSourceView(EditSourceMixin, CreateView):
    '''
        Adds a new source, optionally takes some initial data querystring values to
        prepopulate some of the more unclear values.
    '''

    template_name = 'sync/source-add.html'

    def __init__(self, *args, **kwargs):
        self.prepopulated_data = {}
        super().__init__(*args, **kwargs)

    def dispatch(self, request, *args, **kwargs):
        source_type = request.GET.get('source_type', '')
        if source_type and source_type in YouTube_SourceType.values:
            self.prepopulated_data['source_type'] = source_type
        key = request.GET.get('key', '')
        if key:
            self.prepopulated_data['key'] = key.strip()
        name = request.GET.get('name', '')
        if name:
            self.prepopulated_data['name'] = slugify(name)
        directory = request.GET.get('directory', '')
        if directory:
            self.prepopulated_data['directory'] = slugify(directory)
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        initial = super().get_initial()
        initial['target_schedule'] = timezone.now().replace(
            second=0, microsecond=0,
        )
        for k, v in self.prepopulated_data.items():
            initial[k] = v
        return initial

    def get_success_url(self):
        url = reverse_lazy('sync:source', kwargs={'pk': self.object.pk})
        return append_uri_params(url, {'message': 'source-created'})


class SourceView(DetailView):

    template_name = 'sync/source.html'
    model = Source
    messages = {
        'source-created': _('Your new source has been created. If you have added a '
                            'very large source such as a channel with hundreds of '
                            'videos it can take several minutes or up to an hour '
                            'for media to start to appear.'),
        'source-updated': _('Your source has been updated.'),
    }

    def __init__(self, *args, **kwargs):
        self.message = None
        super().__init__(*args, **kwargs)

    def dispatch(self, request, *args, **kwargs):
        message_key = request.GET.get('message', '')
        self.message = self.messages.get(message_key, '')
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, *args, **kwargs):
        data = super().get_context_data(*args, **kwargs)
        data['message'] = self.message
        data['errors'] = []
        for error in get_source_completed_tasks(self.object.pk, only_errors=True):
            error_message = get_error_message(error)
            setattr(error, 'error_message', error_message)
            data['errors'].append(error)
        data['media'] = Media.objects.filter(source=self.object).order_by('-published').defer('metadata')
        return data


class UpdateSourceView(EditSourceMixin, UpdateView):

    template_name = 'sync/source-update.html'

    def get_initial(self):
        initial = super().get_initial()
        when = getattr(self.object, 'target_schedule') or timezone.now()
        initial['target_schedule'] = when.replace(second=0, microsecond=0)
        return initial

    def get_success_url(self):
        url = reverse_lazy('sync:source', kwargs={'pk': self.object.pk})
        return append_uri_params(url, {'message': 'source-updated'})


class DeleteSourceView(DeleteView, FormMixin):
    '''
        Confirm the deletion of a source with an option to delete all the media
        associated with the source from disk when the source is deleted.
    '''

    template_name = 'sync/source-delete.html'
    model = Source
    form_class = ConfirmDeleteSourceForm
    context_object_name = 'source'

    def post(self, request, *args, **kwargs):
        source = self.get_object()
        media_source = dict(
            uuid=None,
            index_schedule=IndexSchedule.NEVER,
            download_media=False,
            index_videos=False,
            index_streams=False,
            filter_text=str(source.pk),
            target_schedule=source.target_schedule or timezone.now(),
        )
        copy_fields = set(map(lambda f: f.name, source._meta.fields)) - set(media_source.keys())
        for k, v in source.__dict__.items():
            if k in copy_fields:
                media_source[k] = v
        media_source = Source(**media_source)
        delete_media_val = request.POST.get('delete_media', False)
        delete_media = True if delete_media_val is not False else False
        # overload this boolean for our own use
        media_source.delete_removed_media = delete_media
        # adjust the directory and key on the source to be deleted
        source.directory = source.directory + '/deleted'
        source.key = source.key + '/deleted'
        source.name = f'[Deleting] {source.name}'
        source.save(update_fields={'directory', 'key', 'name'})
        source.refresh_from_db()
        # save the new media source now that it is not a duplicate
        media_source.uuid = None
        media_source.save()
        media_source.refresh_from_db()
        # switch the media to the new source instance
        Media.objects.filter(source=source).update(source=media_source)
        if delete_media:
            directory_path = pathlib.Path(media_source.directory_path)
            mkdir_p(directory_path)
            (directory_path / '.to_be_removed').touch(exist_ok=True)
        return super().post(request, *args, **kwargs)

    def get_success_url(self):
        url = reverse_lazy('sync:sources')
        return append_uri_params(url, {'message': 'source-deleted'})


class MediaView(ListView):
    '''
        A bare list of media added with their states.
    '''

    template_name = 'sync/media.html'
    context_object_name = 'media'
    paginate_by = settings.MEDIA_PER_PAGE
    messages = {
        'filter': _('Viewing media filtered for source: <strong>{name}</strong>'),
    }

    def __init__(self, *args, **kwargs):
        self.filter_source = None
        self.show_skipped = False
        self.only_skipped = False
        super().__init__(*args, **kwargs)

    def dispatch(self, request, *args, **kwargs):
        filter_by = request.GET.get('filter', '')
        if filter_by:
            try:
                self.filter_source = Source.objects.get(pk=filter_by)
            except Source.DoesNotExist:
                self.filter_source = None
        show_skipped = request.GET.get('show_skipped', '').strip()
        if show_skipped == 'yes':
            self.show_skipped = True
        if not self.show_skipped:
            only_skipped = request.GET.get('only_skipped', '').strip()
            if only_skipped == 'yes':
                self.only_skipped = True
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        q = Media.objects.all()

        if self.filter_source:
            q = q.filter(source=self.filter_source)
        if self.only_skipped:
            q = q.filter(Q(can_download=False) | Q(skip=True) | Q(manual_skip=True))
        elif not self.show_skipped:
            q = q.filter(Q(can_download=True) & Q(skip=False) & Q(manual_skip=False))

        return q.order_by('-published', '-created')

    def get_context_data(self, *args, **kwargs):
        data = super().get_context_data(*args, **kwargs)
        data['message'] = ''
        data['source'] = None
        if self.filter_source:
            message = str(self.messages.get('filter', ''))
            data['message'] = message.format(name=self.filter_source.name)
            data['source'] = self.filter_source
        data['show_skipped'] = self.show_skipped
        data['only_skipped'] = self.only_skipped
        return data


class MediaThumbView(DetailView):
    '''
        Shows a media thumbnail. Whitenoise doesn't support post-start media image
        serving and the images here are pretty small so just serve them manually. This
        isn't fast, but it's not likely to be a serious bottleneck.
    '''

    model = Media

    def get(self, request, *args, **kwargs):
        media = self.get_object()
        # Thumbnail media is never updated so we can ask the browser to cache it
        # for ages, 604800 = 7 days
        max_age = 604800
        if media.thumb_file_exists:
            thumb_path = pathlib.Path(media.thumb.path)
            thumb = thumb_path.read_bytes()
            content_type = 'image/jpeg' 
        else:
            # No thumbnail on disk, return a blank 1x1 gif
            thumb = b64decode('R0lGODlhAQABAIABAP///wAAACH5BAEKAAEALAA'
                              'AAAABAAEAAAICTAEAOw==')
            content_type = 'image/gif'
            max_age = 600
        response = HttpResponse(thumb, content_type=content_type)
        
        response['Cache-Control'] = f'public, max-age={max_age}'
        return response


class MediaItemView(DetailView):
    '''
        A single media item overview page.
    '''

    template_name = 'sync/media-item.html'
    model = Media
    messages = {
        'thumbnail': _('Thumbnail has been scheduled to redownload'),
        'redownloading': _('Media file has been deleted and scheduled to redownload'),
        'skipped': _('Media file has been deleted and marked to never download'),
        'enabled': _('Media has been re-enabled and will be downloaded'),
    }

    def __init__(self, *args, **kwargs):
        self.message = None
        super().__init__(*args, **kwargs)

    def dispatch(self, request, *args, **kwargs):
        message_key = request.GET.get('message', '')
        self.message = self.messages.get(message_key, '')
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, *args, **kwargs):
        data = super().get_context_data(*args, **kwargs)
        data['message'] = self.message
        combined_exact, combined_format = self.object.get_best_combined_format()
        audio_exact, audio_format = self.object.get_best_audio_format()
        video_exact, video_format = self.object.get_best_video_format()
        task = get_media_download_task(self.object.pk)
        data['task'] = task
        data['download_state'] = self.object.get_download_state(task)
        data['download_state_icon'] = self.object.get_download_state_icon(task)
        data['combined_exact'] = combined_exact
        data['combined_format'] = combined_format
        data['audio_exact'] = audio_exact
        data['audio_format'] = audio_format
        data['video_exact'] = video_exact
        data['video_format'] = video_format
        data['youtube_dl_format'] = self.object.get_format_str()
        data['filename_path'] = pathlib.Path(self.object.filename)
        data['media_file_path'] = pathlib.Path(self.object.media_file.path) if self.object.media_file else None
        return data

    def get(self, *args, **kwargs):
        if args[0].path.startswith("/media-thumb-redownload/"):
            media = Media.objects.get(pk=kwargs["pk"])
            if media is None:
                return HttpResponseNotFound()

            TaskHistory.schedule(
                download_media_image,
                str(media.pk),
                media.thumbnail,
                priority=1+download_media_image.settings.get('default_priority', 0),
                vn_fmt=_('Redownload thumbnail for "{}": {}'),
                vn_args=(
                    media.key,
                    media.name,
                ),
            )
            url = reverse_lazy('sync:media-item', kwargs={'pk': media.pk})
            url = append_uri_params(url, {'message': 'thumbnail'})
            return HttpResponseRedirect(url)
        else:
            return super().get(self, *args, **kwargs)


class MediaRedownloadView(FormView, SingleObjectMixin):
    '''
        Confirm that the media file should be deleted and redownloaded.
    '''

    template_name = 'sync/media-redownload.html'
    form_class = RedownloadMediaForm
    model = Media

    def __init__(self, *args, **kwargs):
        self.object = None
        super().__init__(*args, **kwargs)

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        # Delete any active download tasks for the media
        delete_task_by_media('sync.tasks.download_media', (str(self.object.pk),))
        # If the thumbnail file exists on disk, delete it
        if self.object.thumb_file_exists:
            delete_file(self.object.thumb.path)
            self.object.thumb = None
        # If the media file exists on disk, delete it
        if self.object.media_file_exists:
            delete_file(self.object.media_file.path)
            self.object.media_file = None
            # If the media has an associated thumbnail copied, also delete it
            delete_file(self.object.thumbpath)
            # If the media has an associated NFO file with it, also delete it
            delete_file(self.object.nfopath)
        # Reset all download data
        self.object.downloaded = False
        self.object.downloaded_audio_codec = None
        self.object.downloaded_video_codec = None
        self.object.downloaded_container = None
        self.object.downloaded_fps = None
        self.object.downloaded_hdr = False
        self.object.downloaded_filesize = None
        # Mark it as not skipped
        self.object.skip = False
        self.object.manual_skip = False
        # Saving here will trigger the post_create signals to schedule new tasks
        self.object.save()
        return super().form_valid(form)

    def get_success_url(self):
        url = reverse_lazy('sync:media-item', kwargs={'pk': self.object.pk})
        return append_uri_params(url, {'message': 'redownloading'})


class MediaSkipView(FormView, SingleObjectMixin):
    '''
        Confirm that the media file should be deleted and marked to skip.
    '''

    template_name = 'sync/media-skip.html'
    form_class = SkipMediaForm
    model = Media

    def __init__(self, *args, **kwargs):
        self.object = None
        super().__init__(*args, **kwargs)

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        # Delete any active download tasks for the media
        delete_task_by_media('sync.tasks.download_media', (str(self.object.pk),))
        # If the media file exists on disk, delete it
        if self.object.media_file_exists:
            # Delete all files which contains filename
            filepath = self.object.media_file.path
            barefilepath, fileext = os.path.splitext(filepath)
            # Get all files that start with the bare file path
            all_related_files = glob.glob(f'{barefilepath}.*')
            for file in all_related_files:
                delete_file(file)
        # Reset all download data
        self.object.metadata_clear()
        self.object.downloaded = False
        self.object.downloaded_audio_codec = None
        self.object.downloaded_video_codec = None
        self.object.downloaded_container = None
        self.object.downloaded_fps = None
        self.object.downloaded_hdr = False
        self.object.downloaded_filesize = None
        # Mark it to be skipped
        self.object.skip = True
        self.object.manual_skip = True
        self.object.save()
        return super().form_valid(form)

    def get_success_url(self):
        url = reverse_lazy('sync:media-item', kwargs={'pk': self.object.pk})
        return append_uri_params(url, {'message': 'skipped'})


class MediaEnableView(FormView, SingleObjectMixin):
    '''
        Confirm that the media item should be re-enabled (marked as unskipped).
    '''

    template_name = 'sync/media-enable.html'
    form_class = EnableMediaForm
    model = Media

    def __init__(self, *args, **kwargs):
        self.object = None
        super().__init__(*args, **kwargs)

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        # Mark it as not skipped
        self.object.skip = False
        self.object.manual_skip = False
        self.object.save()
        return super().form_valid(form)

    def get_success_url(self):
        url = reverse_lazy('sync:media-item', kwargs={'pk': self.object.pk})
        return append_uri_params(url, {'message': 'enabled'})


class MediaContent(DetailView):
    '''
        Redirect to nginx to download the file
    '''
    model = Media

    def __init__(self, *args, **kwargs):
        self.object = None
        super().__init__(*args, **kwargs)

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        # development direct file stream - DO NOT USE PRODUCTIVLY
        if settings.DEBUG and 'runserver' in sys.argv:
            # get media URL
            pth = self.object.media_file.url
            # remove "/media-data/"
            pth = pth.split("/media-data/",1)[1]
            # remove "/" (incase of absolute path)
            pth = pth.split(str(settings.DOWNLOAD_ROOT).lstrip("/"),1)

            # if we do not have a "/" at the beginning, it is not a absolute path...
            if len(pth) > 1:
                pth = pth[1]
            else:
                pth = pth[0]


            # build final path
            filepth = pathlib.Path(str(settings.DOWNLOAD_ROOT) + pth)

            if filepth.exists():
                # return file
                response = FileResponse(open(filepth,'rb'))
                return response
            else:
                return HttpResponseNotFound()

        else:
            headers = {
                'Content-Type': self.object.content_type,
                'X-Accel-Redirect': self.object.media_file.url,
            }
            return HttpResponse(headers=headers)


class TasksView(ListView):
    '''
        A list of tasks queued to be completed. This is, for example, scraping for new
        media or downloading media.
    '''

    template_name = 'sync/tasks.html'
    context_object_name = 'tasks'
    paginate_by = settings.TASKS_PER_PAGE
    messages = {
        'filter': _('Viewing tasks filtered for source: <strong>{name}</strong>'),
        'reset': _('All tasks have been reset'),
    }

    def __init__(self, *args, **kwargs):
        self.filter_source = None
        self.message = None
        super().__init__(*args, **kwargs)

    def dispatch(self, request, *args, **kwargs):
        message_key = request.GET.get('message', '')
        self.message = self.messages.get(message_key, '')
        filter_by = request.GET.get('filter', '')
        if filter_by:
            try:
                self.filter_source = Source.objects.get(pk=filter_by)
            except Source.DoesNotExist:
                self.filter_source = None
            if not message_key or 'filter' == message_key:
                message = self.messages.get('filter', '')
                self.message = message.format(
                    name=self.filter_source.name
                )

        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        qs = get_waiting_tasks()
        if self.filter_source:
            params_prefix=f'[["{self.filter_source.pk}"'
            qs = qs.filter(task_params__istartswith=params_prefix)
        return qs.order_by(
            '-priority',
            'scheduled_at',
            'end_at',
        )

    def get_context_data(self, *args, **kwargs):
        data = super().get_context_data(*args, **kwargs)
        now_dt = timezone.now()
        scheduled_qs = get_waiting_tasks()
        # Huey removes running tasks,
        # so the waiting tasks will not include them.
        running_qs = get_running_tasks(now_dt)
        errors_qs = scheduled_qs.filter(
            attempts__gt=0
        ).exclude(last_error__exact='')

        # Add to context data from ListView
        data['message'] = self.message
        data['source'] = self.filter_source
        data['running'] = list()
        data['errors'] = list()
        data['total_errors'] = errors_qs.count()
        data['scheduled'] = list()
        data['total_scheduled'] = scheduled_qs.count()
        data['migrated'] = migrate_queues()
        data['wait_for_database_queue'] = False

        def add_to_task(task):
            setattr(task, 'run_now', task.scheduled_at < now_dt)
            obj, url = map_task_to_instance(task)
            if obj:
                setattr(task, 'instance', obj)
                setattr(task, 'url', url)
            if task.has_error():
                error_message = get_error_message(task)
                setattr(task, 'error_message', error_message)
                return 'error'
            return True and obj

        verbose_names = dict()
        for task in Task.objects.filter(locked_by__isnull=False):
            # There was broken logic in `Task.objects.locked()`, work around it.
            # With that broken logic, the tasks never resume properly.
            # This check unlocks the tasks without a running process.
            # `task.locked_by_pid_running()` returns:
            # - `True`: locked and PID exists
            # - `False`: locked and PID does not exist
            # - `None`: not `locked_by`, so there was no PID to check
            locked_by_pid_running = task.locked_by_pid_running()
            if locked_by_pid_running is False:
                task.locked_by = None
                # do not wait for the task to expire
                task.locked_at = None
                task.save()
            task_id = str(task.pk)
            verbose_names[task_id] = task.verbose_name
            try:
                task = TaskHistory.objects.get(task_id=task_id)
            except TaskHistory.DoesNotExist:
                # possibly create a new instance?
                pass
            else:
                if locked_by_pid_running and add_to_task(task):
                    # Use the status if it is available
                    task.verbose_name = verbose_names.get(task_id) or task.verbose_name
                    data['running'].append(task)
                elif locked_by_pid_running and 'wait_for_database_queue' in task.name:
                    data['wait_for_database_queue'] = True
        verbose_names = None

        for task in running_qs:
            if task in data['running']:
                    continue
            add_to_task(task)
            data['running'].append(task)
            
        # show all the errors when they fit on one page
        if (data['total_errors'] + len(data['running'])) < self.paginate_by:
            for task in errors_qs:
                if task in data['running']:
                    continue
                mapped = add_to_task(task)
                if 'error' == mapped:
                    data['errors'].append(task)
                elif mapped:
                    data['scheduled'].append(task)

        for task in data['tasks']:
            already_added = (
                task in data['running'] or
                task in data['errors'] or
                task in data['scheduled']
            )
            if already_added:
                continue
            mapped = add_to_task(task)
            if 'error' == mapped:
                data['errors'].append(task)
            elif mapped or settings.DEBUG:
                data['scheduled'].append(task)

        sort_keys = (
            # key, reverse
            ('scheduled_at', False),
            ('priority', True),
            ('run_now', True),
        )
        data['errors'] = multi_key_sort(data['errors'], sort_keys, attr=True)
        data['scheduled'] = multi_key_sort(data['scheduled'], sort_keys, attr=True)

        return data


class CompletedTasksView(ListView):
    '''
        List of tasks which have been completed with an optional per-source filter.
    '''

    template_name = 'sync/tasks-completed.html'
    context_object_name = 'tasks'
    paginate_by = settings.TASKS_PER_PAGE
    messages = {
        'filter': _('Viewing tasks filtered for source: <strong>{name}</strong>'),
    }

    def __init__(self, *args, **kwargs):
        self.filter_source = None
        super().__init__(*args, **kwargs)

    def dispatch(self, request, *args, **kwargs):
        filter_by = request.GET.get('filter', '')
        if filter_by:
            try:
                self.filter_source = Source.objects.get(pk=filter_by)
            except Source.DoesNotExist:
                self.filter_source = None
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        qs = TaskHistory.objects.filter(
            start_at__isnull=False,
            end_at__gt=F('start_at'),
        )
        if self.filter_source:
            params_prefix=f'[["{self.filter_source.pk}"'
            qs = qs.filter(task_params__istartswith=params_prefix)
        return qs.order_by('-end_at')

    def get_context_data(self, *args, **kwargs):
        data = super().get_context_data(*args, **kwargs)
        for task in data['tasks']:
            if task.has_error():
                error_message = get_error_message(task)
                setattr(task, 'error_message', error_message)
        data['message'] = ''
        data['source'] = self.filter_source
        if self.filter_source:
            message = str(self.messages.get('filter', ''))
            data['message'] = message.format(name=self.filter_source.name)
        return data


class ResetTasks(FormView):
    '''
        Confirm that all tasks should be reset. As all tasks are triggered from
        signals by checking for files existing etc. this can be done by just deleting
        all tasks and then calling every Source objects .save() method.
    '''

    template_name = 'sync/tasks-reset.html'
    form_class = ResetTasksForm

    def form_valid(self, form):
        # Delete all tasks
        Task.objects.all().delete()
        huey_queue_names = (DJANGO_HUEY or {}).get('queues', {})
        for queue_name in huey_queue_names:
            h_q_reset_tasks(queue_name)
        # Iter all tasks
        for source in Source.objects.all():
            check_source_directory_exists(str(source.pk))
            # This also chains down to call each Media objects .save() as well
            source.save()
        return super().form_valid(form)

    def get_success_url(self):
        url = reverse_lazy('sync:tasks')
        return append_uri_params(url, {'message': 'reset'})


class TaskScheduleView(FormView, SingleObjectMixin):
    '''
        Confirm that the task should be re-scheduled.
    '''

    template_name = 'sync/task-schedule.html'
    form_class = ScheduleTaskForm
    model = Task
    errors = dict(
        invalid_when=_('The type ({}) was incorrect.'),
        when_before_now=_('The date and time must be in the future.'),
    )

    def __init__(self, *args, **kwargs):
        self.now = timezone.now()
        self.object = None
        self.timestamp = None
        self.when = None
        super().__init__(*args, **kwargs)

    def dispatch(self, request, *args, **kwargs):
        self.now = timezone.now()
        self.object = self.get_object()
        self.timestamp = kwargs.get('timestamp')
        try:
            self.when = timestamp_to_datetime(self.timestamp)
        except AssertionError:
            self.when = None
        if self.when is None:
            self.when = self.now
        # Use the next minute and zero seconds
        # The web browser does not select seconds by default
        self.when = self.when.replace(second=0) + timezone.timedelta(minutes=1)
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        initial = super().get_initial()
        initial['now'] = self.now
        initial['when'] = self.when
        return initial

    def get_context_data(self, *args, **kwargs):
        data = super().get_context_data(*args, **kwargs)
        data['now'] = self.now
        data['when'] = self.when
        return data

    def get_success_url(self):
        return append_uri_params(
            reverse_lazy('sync:tasks'),
            dict(
                message='scheduled',
                pk=str(self.object.pk),
            ),
        )

    def form_valid(self, form):
        max_attempts = getattr(settings, 'MAX_ATTEMPTS', 15)
        when = form.cleaned_data.get('when')
  
        if not isinstance(when, self.now.__class__):
            form.add_error(
                'when',
                ValidationError(
                    self.errors['invalid_when'].format(
                        type(when),
                    ),
                ),
            )
        if when < self.now:
            form.add_error(
                'when',
                ValidationError(self.errors['when_before_now']),
            )

        if form.errors:
            return super().form_invalid(form)

        self.object.attempts = max_attempts // 2
        self.object.run_at = max(self.now, when)
        self.object.save()

        return super().form_valid(form)


class MediaServersView(ListView):
    '''
        List of media servers which have been added.
    '''

    template_name = 'sync/mediaservers.html'
    context_object_name = 'mediaservers'
    types_object = MediaServerType
    messages = {
        'deleted': _('Your selected media server has been deleted.'),
    }

    def __init__(self, *args, **kwargs):
        self.message = None
        super().__init__(*args, **kwargs)

    def dispatch(self, request, *args, **kwargs):
        message_key = request.GET.get('message', '')
        self.message = self.messages.get(message_key, '')
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return MediaServer.objects.all().order_by('host', 'port')

    def get_context_data(self, *args, **kwargs):
        data = super().get_context_data(*args, **kwargs)
        data['message'] = self.message
        data['media_server_types'] = self.types_object.members_list()
        return data


class AddMediaServerView(FormView):
    '''
        Adds a new media server. The form is switched out to whatever matches the
        server type.
    '''

    template_name = 'sync/mediaserver-add.html'
    server_types = MediaServerType.long_types()
    server_type_names = dict(MediaServerType.choices)
    forms = MediaServerType.forms_dict()

    def __init__(self, *args, **kwargs):
        self.server_type = None
        self.model_class = None
        self.object = None
        super().__init__(*args, **kwargs)

    def dispatch(self, request, *args, **kwargs):
        server_type_str = kwargs.get('server_type', '')
        self.server_type = self.server_types.get(server_type_str)
        if not self.server_type:
            raise Http404
        self.form_class = self.forms.get(self.server_type)
        if not self.form_class:
            raise Http404
        self.model_class = MediaServer(server_type=self.server_type)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        # Assign mandatory fields, bundle other fields into options
        mediaserver = MediaServer(server_type=self.server_type)
        options = dict()
        model_fields = [field.name for field in MediaServer._meta.fields]
        for field_name, field_value in form.cleaned_data.items():
            if field_name in model_fields:
                setattr(mediaserver, field_name, field_value)
            else:
                options[field_name] = field_value
        mediaserver.options = options
        # Test the media server details are valid
        try:
            mediaserver.validate()
        except ValidationError as e:
            form.add_error(None, e)
        # Check if validation detected any errors
        if form.errors:
            return super().form_invalid(form)
        # All good, try to save and return
        try:
            mediaserver.save()
        except IntegrityError:
            form.add_error(
                None,
                (f'A media server already exists with the host and port '
                 f'{mediaserver.host}:{mediaserver.port}')
            )
        # Check if saving caused any errors
        if form.errors:
            return super().form_invalid(form)
        # All good!
        self.object = mediaserver
        return super().form_valid(form)

    def get_context_data(self, *args, **kwargs):
        data = super().get_context_data(*args, **kwargs)
        data['server_type'] = self.server_type
        data['server_type_long'] = self.server_types.get(self.server_type)
        data['server_type_name'] = self.server_type_names.get(self.server_type)
        data['server_help'] = self.model_class.get_help_html()
        return data

    def get_success_url(self):
        url = reverse_lazy('sync:mediaserver', kwargs={'pk': self.object.pk})
        return append_uri_params(url, {'message': 'created'})


class MediaServerView(DetailView):
    '''
        A single media server overview page.
    '''

    template_name = 'sync/mediaserver.html'
    model = MediaServer
    private_options = ('token',)
    messages = {
        'created': _('Your media server has been successfully added'),
    }

    def __init__(self, *args, **kwargs):
        self.message = None
        super().__init__(*args, **kwargs)

    def dispatch(self, request, *args, **kwargs):
        message_key = request.GET.get('message', '')
        self.message = self.messages.get(message_key, '')
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, *args, **kwargs):
        data = super().get_context_data(*args, **kwargs)
        data['message'] = self.message
        data['private_options'] = self.private_options
        return data


class DeleteMediaServerView(DeleteView, FormMixin):
    '''
        Confirms deletion and then deletes a media server.
    '''

    template_name = 'sync/mediaserver-delete.html'
    model = MediaServer
    form_class = ConfirmDeleteMediaServerForm
    context_object_name = 'mediaserver'

    def get_success_url(self):
        url = reverse_lazy('sync:mediaservers')
        return append_uri_params(url, {'message': 'deleted'})


class UpdateMediaServerView(FormView, SingleObjectMixin):
    '''
        Adds a new media server. The form is switched out to whatever matches the
        server type.
    '''

    template_name = 'sync/mediaserver-update.html'
    model = MediaServer
    forms = MediaServerType.forms_dict()

    def __init__(self, *args, **kwargs):
        self.object = None
        super().__init__(*args, **kwargs)

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.form_class = self.forms.get(self.object.server_type, None)
        if not self.form_class:
            raise Http404
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        initial = super().get_initial()
        for field in self.object._meta.fields:
            if field.name in self.form_class.declared_fields:
                initial[field.name] = getattr(self.object, field.name)
        for option_key, option_val in self.object.options.items():
            if option_key in self.form_class.declared_fields:
                initial[option_key] = option_val
        return initial

    def form_valid(self, form):
        # Assign mandatory fields, bundle other fields into options
        options = dict()
        model_fields = [field.name for field in MediaServer._meta.fields]
        for field_name, field_value in form.cleaned_data.items():
            if field_name in model_fields:
                setattr(self.object, field_name, field_value)
            else:
                options[field_name] = field_value
        self.object.options = options
        # Test the media server details are valid
        try:
            self.object.validate()
        except ValidationError as e:
            form.add_error(None, e)
        # Check if validation detected any errors
        if form.errors:
            return super().form_invalid(form)
        # All good, try to save and return
        try:
            self.object.save()
        except IntegrityError:
            form.add_error(
                None,
                (f'A media server already exists with the host and port '
                 f'{self.object.host}:{self.object.port}')
            )
        # Check if saving caused any errors
        if form.errors:
            return super().form_invalid(form)
        # All good!
        return super().form_valid(form)

    def get_context_data(self, *args, **kwargs):
        data = super().get_context_data(*args, **kwargs)
        data['server_help'] = self.object.get_help_html
        return data

    def get_success_url(self):
        url = reverse_lazy('sync:mediaserver', kwargs={'pk': self.object.pk})
        return append_uri_params(url, {'message': 'updated'})
