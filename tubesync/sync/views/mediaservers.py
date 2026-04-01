from django.http import Http404
from django.views.generic import ListView, DetailView
from django.views.generic.edit import FormView, FormMixin, DeleteView
from django.views.generic.detail import SingleObjectMixin
from django.urls import reverse_lazy
from django.db import IntegrityError
from django.forms import ValidationError
from django.utils.translation import gettext_lazy as _
from common.utils import append_uri_params
from ..models import MediaServer
from django import forms
from ..choices import MediaServerType


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
    form_class = forms.Form
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
