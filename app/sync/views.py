from django.views.generic import TemplateView


class IndexView(TemplateView):

    template_name = 'sync/index.html'

    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)
