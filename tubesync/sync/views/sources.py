import pathlib
from django.conf import settings
from django.http import HttpResponseNotFound, HttpResponseRedirect
from django.views import View
from django.views.generic import ListView, DetailView
from django.views.generic.edit import FormView, FormMixin, CreateView, UpdateView, DeleteView
from django.core.exceptions import SuspiciousFileOperation
from django.urls import reverse_lazy
from django.db.models import Count, When, Case
from django.forms import Form, ValidationError
from django.utils.text import slugify
from django.utils._os import safe_join
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from common.models import TaskHistory
from common.utils import append_uri_params, mkdir_p
from ..models import Source, Media
from ..forms import ValidateSourceForm, ConfirmDeleteSourceForm, SourceForm
from ..utils import validate_url
from ..tasks import get_source_completed_tasks, get_error_message, index_source
from ..choices import (Val, IndexSchedule, YouTube_SourceType,
                       youtube_long_source_types, youtube_validation_urls)
from .. import signals # noqa
from .. import youtube


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


class SourceSyncNowView(View):
    '''
        Triggers an immediate index of a source, then redirects back to the
        sources list.
    '''

    def get(self, request, pk):
        try:
            source = Source.objects.get(pk=pk)
        except Source.DoesNotExist:
            return HttpResponseNotFound()
        TaskHistory.schedule(
            index_source,
            str(source.pk),
            delay=30,
            vn_fmt=_('Index media from source "{}" once'),
            vn_args=(source.name,),
        )
        url = reverse_lazy('sync:sources')
        url = append_uri_params(url, {'message': 'source-refreshed'})
        return HttpResponseRedirect(url)


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
        'invalid_url': _('That URL does not match any supported formats.'),
    }
    source_types = youtube_long_source_types
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

    def form_valid(self, form):
        # Perform extra validation on the URL, we need to extract the channel name or
        # playlist ID and check they are valid
        source_url = form.cleaned_data['source_url']
        for source_type in YouTube_SourceType.values:
            validation_url = self.validation_urls.get(source_type)
            try:
                self.key = validate_url(source_url, validation_url)
                self.source_type = source_type
                for long_type_str, st_val in youtube_long_source_types.items():
                    if st_val == source_type:
                        self.source_type_str = long_type_str
                        break
                return super().form_valid(form)
            except ValidationError:
                continue
        # Source type wasn't detected - presumably it's not a valid URL
        form.add_error('source_url', ValidationError(self.errors['invalid_url']))
        return super().form_invalid(form)

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
        # Inject the adjustable media format default
        self.prepopulated_data['media_format'] = getattr(
            settings, 'MEDIA_FORMATSTR', settings.MEDIA_FORMATSTR_DEFAULT
        )
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
