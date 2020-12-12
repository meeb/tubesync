from django.urls import path
from .views import (DashboardView, SourcesView, ValidateSourceView, AddSourceView,
                    SourceView, UpdateSourceView, DeleteSourceView, MediaView,
                    MediaThumbView, MediaItemView, MediaRedownloadView, MediaSkipView,
                    MediaEnableView, TasksView, CompletedTasksView, ResetTasks,
                    MediaServersView, AddMediaServerView, MediaServerView,
                    DeleteMediaServerView, UpdateMediaServerView)


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

    path('media/<uuid:pk>',
         MediaItemView.as_view(),
         name='media-item'),

    path('media-redownload/<uuid:pk>',
         MediaRedownloadView.as_view(),
         name='redownload-media'),

    path('media-skip/<uuid:pk>',
         MediaSkipView.as_view(),
         name='skip-media'),

    path('media-enable/<uuid:pk>',
         MediaEnableView.as_view(),
         name='enable-media'),

    # Task URLs

    path('tasks',
         TasksView.as_view(),
         name='tasks'),

    path('tasks-completed',
         CompletedTasksView.as_view(),
         name='tasks-completed'),

    path('tasks-reset',
         ResetTasks.as_view(),
         name='reset-tasks'),

    # Media Server URLs

    path('mediaservers',
         MediaServersView.as_view(),
         name='mediaservers'),

    path('mediaserver-add/<slug:server_type>',
         AddMediaServerView.as_view(),
         name='add-mediaserver'),

    path('mediaserver/<int:pk>',
         MediaServerView.as_view(),
         name='mediaserver'),

    path('mediaserver-delete/<int:pk>',
         DeleteMediaServerView.as_view(),
         name='delete-mediaserver'),

    path('mediaserver-update/<int:pk>',
         UpdateMediaServerView.as_view(),
         name='update-mediaserver'),

]
