import os
import pathlib
from django.conf import settings
from django.views.generic import TemplateView
from django.db import connection
from django.db.models import F, Q, Sum
from django.utils import timezone
from common.models import TaskHistory
from .utils import get_waiting_tasks
from ..models import Source, Media
from ..choices import Val, SourceResolution


class DashboardView(TemplateView):
    '''
        The dashboard shows non-interactive totals and summaries.
    '''

    template_name = 'sync/dashboard.html'

    def get_context_data(self, *args, **kwargs):
        data = super().get_context_data(*args, **kwargs)
        data['now'] = timezone.now()
        # Sources
        data['num_sources'] = Source.objects.all().count()
        data['num_video_sources'] = Source.objects.filter(
            ~Q(source_resolution=Val(SourceResolution.AUDIO))
        ).count()
        data['num_audio_sources'] = data['num_sources'] - data['num_video_sources']
        data['num_failed_sources'] = Source.objects.filter(has_failed=True).count()
        # Media
        data['num_media'] = Media.objects.all().count()
        data['num_downloaded_media'] = Media.objects.filter(downloaded=True).count()
        # Tasks
        completed_qs = TaskHistory.objects.filter(
            start_at__isnull=False,
            end_at__gt=F('start_at'),
        )
        waiting_qs = get_waiting_tasks()
        data['num_tasks'] = waiting_qs.count()
        data['num_completed_tasks'] = completed_qs.count()
        # Disk usage
        disk_usage = Media.objects.filter(
            downloaded=True, downloaded_filesize__isnull=False
        ).defer('metadata').aggregate(Sum('downloaded_filesize'))
        data['disk_usage_bytes'] = disk_usage['downloaded_filesize__sum']
        if not data['disk_usage_bytes']:
            data['disk_usage_bytes'] = 0
        if data['disk_usage_bytes'] and data['num_downloaded_media']:
            data['average_bytes_per_media'] = round(data['disk_usage_bytes'] /
                                                    data['num_downloaded_media'])
        else:
            data['average_bytes_per_media'] = 0
        # Latest downloads
        data['latest_downloads'] = Media.objects.filter(
            downloaded=True,
            download_date__isnull=False,
            downloaded_filesize__isnull=False,
        ).defer('metadata').order_by('-download_date')[:10]
        # Largest downloads
        data['largest_downloads'] = Media.objects.filter(
            downloaded=True, downloaded_filesize__isnull=False
        ).defer('metadata').order_by('-downloaded_filesize')[:10]
        # UID and GID
        data['uid'] = os.getuid()
        data['gid'] = os.getgid()
        # Config and download locations
        data['config_dir'] = str(settings.CONFIG_BASE_DIR)
        data['downloads_dir'] = str(settings.DOWNLOAD_ROOT)
        data['database_connection'] = settings.DATABASE_CONNECTION_STR
        # Add the database filesize when using db.sqlite3
        data['database_filesize'] = None
        if 'sqlite' == connection.vendor:
            db_name = str(connection.get_connection_params().get('database', ''))
            db_path = pathlib.Path(db_name) if '/' == db_name[0] else None
            if db_path:
                data['database_filesize'] = db_path.stat().st_size
        return data
