from django.urls import path
from .views import (DashboardView, SourcesView, ValidateSourceView, AddSourceView,
                    SourceView, MediaView, TasksView, LogsView)


app_name = 'sync'


urlpatterns = [

    path('',
         DashboardView.as_view(),
         name='dashboard'),
        
    path('sources',
         SourcesView.as_view(),
         name='sources'),

    path('source/validate/<slug:source_type>',
         ValidateSourceView.as_view(),
         name='validate-source'),

    path('source/add',
         AddSourceView.as_view(),
         name='add-source'),

    path('source/<uuid:pk>',
         SourceView.as_view(),
         name='source'),

    path('media',
         MediaView.as_view(),
         name='media'),

    path('tasks',
         TasksView.as_view(),
         name='tasks'),

    path('logs',
         LogsView.as_view(),
         name='logs'),

]
