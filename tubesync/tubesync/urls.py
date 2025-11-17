from django.urls import path, include
from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static


admin.site.site_title = 'TubeSync dashboard admin'
admin.site.site_header = 'TubeSync dashboard admin'
handler404 = 'common.views.error404'
handler500 = 'common.views.error500'


urlpatterns = [

    path('admin/',
         admin.site.urls),

    path('',
         include('common.urls', namespace='common')),

    path('',
         include('sync.urls', namespace='sync')),

]

# WhiteNoise handles static file serving (configured with WHITENOISE_USE_FINDERS=True)
