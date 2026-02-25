import glob
import os
from base64 import b64decode
import pathlib
import sys
from django.conf import settings
from django.http import FileResponse, HttpResponseNotFound, HttpResponseRedirect
from django.views.generic import ListView, DetailView
from django.views.generic.edit import FormView
from django.views.generic.detail import SingleObjectMixin
from django.http import HttpResponse
from django.urls import reverse_lazy
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from common.models import TaskHistory
from common.utils import append_uri_params
from ..models import Source, Media, Metadata
from ..forms import RedownloadMediaForm, SkipMediaForm, EnableMediaForm
from ..utils import delete_file
from ..tasks import (
    get_media_download_task, download_media_image, download_media_file,
    refresh_formats,
)


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
        self.query = None
        self.search_description = False
        self.sp = None
        super().__init__(*args, **kwargs)

    def dispatch(self, request, *args, **kwargs):
        def is_active(arg, /):
            return str(arg).strip().lower() in (
                'enable', 'enabled', 'on', 'true', 'yes', '1',
            )
        def post_or_get(request, /, key, default=None):
            return request.POST.get(key) or request.GET.get(key) or default

        filter_by = post_or_get(request, 'filter', '')
        if filter_by:
            try:
                self.filter_source = Source.objects.get(pk=filter_by)
            except Source.DoesNotExist:
                self.filter_source = None
        show_skipped = post_or_get(request, 'show_skipped', '')
        if is_active(show_skipped):
            self.show_skipped = True
        only_skipped = post_or_get(request, 'only_skipped', '')
        if is_active(only_skipped):
            self.only_skipped = True
        self.query = post_or_get(request, 'query')
        self.search_description = is_active(post_or_get(request, 'search_description'))
        self.sp = post_or_get(request, 'sp')
        if self.sp not in ('combined', 'union', 'or',):
            self.sp = 'or'
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        q = Media.objects.all()
        md_qs = Metadata.objects.all()
        needle = self.query

        if self.filter_source:
            q = q.filter(source=self.filter_source)
        m_q = q
        if needle and 'combined' == self.sp:
            if self.search_description:
                q = q.filter(
                    Q(new_metadata__value__description__icontains=needle) |
                    Q(key__contains=needle) |
                    Q(title__icontains=needle) |
                    Q(new_metadata__value__fulltitle__icontains=needle)
                )
            else:
                q = q.filter(
                    Q(key__contains=needle) |
                    Q(title__icontains=needle) |
                    Q(new_metadata__value__fulltitle__icontains=needle)
                )
        elif needle:
            md_q = md_qs.filter(
                Q(media__in=m_q) &
                (
                    Q(key__contains=needle) |
                    Q(media__title__icontains=needle) |
                    Q(value__fulltitle__icontains=needle)
                )
            ).only('pk')
            if 'union' == self.sp:
                if self.search_description:
                    q = q.union(m_q.filter(new_metadata__value__description__icontains=needle).only('pk'))
                    # We need to be able to filter again, even after using union
                    q = m_q.filter(pk__in=q.only('pk'))
                else:
                    q = m_q.filter(new_metadata__in=md_q)
            else:
                if self.search_description:
                    q = m_q.filter(Q(new_metadata__value__description__icontains=needle) | Q(new_metadata__in=md_q))
                else:
                    q = m_q.filter(new_metadata__in=md_q)
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
        data['query'] = self.query or str()
        data['search_description'] = self.search_description
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
        data['combined_format_dict'] = {'id': str(combined_format)}
        data['audio_format_dict'] = {'id': str(audio_format)}
        data['video_format_dict'] = {'id': str(video_format)}
        context_keys = { k for k in data.keys() if k.endswith('_format_dict') }
        for fmt in self.object.iter_formats():
            for k in context_keys:
                v = data[k]
                if v.get('id') == fmt.get('id'):
                    data[k] = fmt
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
        # Try to download manually, when can_download was true
        media = self.object
        if media.can_download:
            attempted_key = '_refresh_formats_attempted'
            media.save_to_metadata(attempted_key, 1)
            refreshed_key = 'formats_epoch'
            media.save_to_metadata(refreshed_key, 1)
            TaskHistory.schedule(
                refresh_formats,
                str(media.pk),
                priority=90,
                remove_duplicates=False,
                retries=1,
                retry_delay=300,
                vn_fmt=_('Refreshing formats (manually) for "{}"'),
                vn_args=(media.key,),
            )
            TaskHistory.schedule(
                download_media_file,
                str(media.pk),
                override=True,
                priority=90,
                remove_duplicates=True,
                delay=10,
                retries=3,
                retry_delay=600,
                vn_fmt=_('Downloading media (manually) for "{}"'),
                vn_args=(media.name,),
            )
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
