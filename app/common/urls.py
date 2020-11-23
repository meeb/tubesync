from django.conf import settings
from django.urls import path
from django.views.generic.base import RedirectView
from django.views.generic import TemplateView
from django.http import HttpResponse
from .views import error403, error404, error500, HealthCheckView


app_name = 'common'
robots_view = HttpResponse(settings.ROBOTS, content_type='text/plain')
favicon_uri = settings.STATIC_URL + 'images/favicon.ico'
favicon_view = RedirectView.as_view(url=favicon_uri, permanent=False)


urlpatterns = [

    path('error403',
        error403,
        name='error403'),

    path('error404',
        error404,
        name='error404'),

    path('error500',
        error500,
        name='error500'),

    path('robots.txt',
        lambda r: robots_view,
        name='robots'),

    path('favicon.ico',
        favicon_view,
        name='favicon'),

    path('healthcheck',
        HealthCheckView.as_view(),
        name='healthcheck'),

]
