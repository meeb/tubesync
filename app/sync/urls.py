from django.urls import path
from .views import (DashboardView, SourcesView, ValidateSourceView, AddSourceView,
                    SourceView, UpdateSourceView, MediaView, TasksView, LogsView)


app_name = 'sync'


urlpatterns = [

    # Dashboard URLs

    path('',
         DashboardView.as_view(),
         name='dashboard'),
    
    # Source URLs

    path('sources',
         SourcesView.as_view(),
         name='sources'),

    path('source-validate/<slug:source_type>',
         ValidateSourceView.as_view(),
         name='validate-source'),

    path('source-add',
         AddSourceView.as_view(),
         name='add-source'),

    path('source/<uuid:pk>',
         SourceView.as_view(),
         name='source'),

    path('source-update/<uuid:pk>',
         UpdateSourceView.as_view(),
         name='update-source'),

    # Media URLs

    path('media',
         MediaView.as_view(),
         name='media'),

    # Task URLs

    path('tasks',
         TasksView.as_view(),
         name='tasks'),

    # Log URLs

    path('logs',
         LogsView.as_view(),
         name='logs'),

]
