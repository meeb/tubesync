from django.http import Http404
from django.views.generic import TemplateView
from django.views.generic.edit import FormView
from django.urls import reverse_lazy
from django.forms import ValidationError
from django.utils.translation import gettext_lazy as _
from .models import Source
from .forms import ValidateSourceForm
from .utils import validate_url


class DashboardView(TemplateView):
    '''
        The dashboard shows non-interactive totals and summaries, nothing more.
    '''

    template_name = 'sync/dashboard.html'

    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


class SourcesView(TemplateView):
    '''
        A bare list of the sources which have been created with their states.
    '''

    template_name = 'sync/sources.html'

    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


class ValidateSourceView(FormView):
    '''
        Validate a URL and prepopulate a create source view form with confirmed
        accurate data. The aim here is to streamline onboarding of new sources
        which otherwise may not be entirely obvious to add, such as the "key"
        being just a playlist ID or some other reasonably unobvious internals.
    '''

    template_name = 'sync/source-validate.html'
    form_class = ValidateSourceForm
    errors = {
        'invalid_url': _('Invalid URL, the URL must for a "{item}" must be in '
                         'the format of "{example}". The error was: {error}.'),
    }
    source_types = {
        'youtube-channel': Source.SOURCE_TYPE_YOUTUBE_CHANNEL,
        'youtube-playlist': Source.SOURCE_TYPE_YOUTUBE_PLAYLIST,
    }
    help_item = {
        Source.SOURCE_TYPE_YOUTUBE_CHANNEL: _('YouTube channel'),
        Source.SOURCE_TYPE_YOUTUBE_PLAYLIST: _('YouTube playlist'),
    }
    help_texts = {
        Source.SOURCE_TYPE_YOUTUBE_CHANNEL: _(
            'Enter a YouTube channel URL into the box below. A channel URL will be in '
            'the format of <strong>https://www.youtube.com/CHANNELNAME</strong> '
            'where <strong>CHANNELNAME</strong> is the name of the channel you want '
            'to add.'
        ),
        Source.SOURCE_TYPE_YOUTUBE_PLAYLIST: _(
            'Enter a YouTube playlist URL into the box below. A playlist URL will be '
            'in the format of <strong>https://www.youtube.com/watch?v=AAAAAA&list='
            'BiGLoNgUnIqUeId</strong> where <strong>BiGLoNgUnIqUeId</strong> is the '
            'unique ID of the playlist you want to add.'
        ),
    }
    help_examples = {
        Source.SOURCE_TYPE_YOUTUBE_CHANNEL: 'https://www.youtube.com/google',
        Source.SOURCE_TYPE_YOUTUBE_PLAYLIST: ('https://www.youtube.com/watch?v=DcKEPl'
                                              '-MpLA&list=PL590L5WQmH8dpP0RyH5pCfIaDE'
                                              'dt9nk7r')
    }
    validation_urls = {
        Source.SOURCE_TYPE_YOUTUBE_CHANNEL: {
            'scheme': 'https',
            'domain': 'www.youtube.com',
            'path_regex': '^\/(c\/)?[^\/]+$',
            'qs_args': [],
            'example': 'https://www.youtube.com/SOMECHANNEL'
        },
        Source.SOURCE_TYPE_YOUTUBE_PLAYLIST: {
            'scheme': 'https',
            'domain': 'www.youtube.com',
            'path_regex': '^\/watch$',
            'qs_args': ['v', 'list'],
            'example': 'https://www.youtube.com/watch?v=VIDEOID&list=PLAYLISTID'
        },
    }

    def __init__(self, *args, **kwargs):
        self.source_type_str = ''
        self.source_type = None
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
        if source_type not in self.source_types.values():
            form.add_error(
                'source_type',
                ValidationError(self.errors['invalid_source'])
            )
        source_url = form.cleaned_data['source_url']
        validation_url = self.validation_urls.get(self.source_type)
        try:
            validate_url(source_url, validation_url)
        except ValidationError as e:
            print(e)
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

    def clean(self):
        cleaned_data = super().clean()
        
        print(cleaned_data)
        return cleaned_data

    def get_success_url(self):
        return reverse_lazy('sync:dashboard')


class MediaView(TemplateView):
    '''
        A bare list of media added with their states.
    '''

    template_name = 'sync/media.html'

    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


class TasksView(TemplateView):
    '''
        A list of tasks queued to be completed. Typically, this is scraping for new
        media or downloading media.
    '''

    template_name = 'sync/tasks.html'

    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


class LogsView(TemplateView):
    '''
        The last X days of logs.
    '''

    template_name = 'sync/logs.html'

    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)
