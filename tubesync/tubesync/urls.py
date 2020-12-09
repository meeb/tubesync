from django.urls import path, include
from django.contrib import admin


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
