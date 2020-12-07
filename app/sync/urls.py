from django.urls import path
from .views import (DashboardView, SourcesView, ValidateSourceView, AddSourceView,
                    SourceView, UpdateSourceView, DeleteSourceView, MediaView,
                    MediaThumbView, MediaItemView, TasksView, CompletedTasksView)


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

    path('source-delete/<uuid:pk>',
         DeleteSourceView.as_view(),
         name='delete-source'),

    # Media URLs

    path('media',
         MediaView.as_view(),
         name='media'),

    path('media-thumb/<uuid:pk>',
         MediaThumbView.as_view(),
         name='media-thumb'),

    path('media-item/<uuid:pk>',
         MediaItemView.as_view(),
         name='media-item'),

    # Task URLs

    path('tasks',
         TasksView.as_view(),
         name='tasks'),

    path('tasks-completed',
         CompletedTasksView.as_view(),
         name='tasks-completed'),

]
