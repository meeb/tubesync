import os
from celery import Celery


os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tubesync.settings')
REDIS_CONNECTION = os.getenv('REDIS_CONNECTION', 'redis://localhost:6379/0')


app = Celery('tubesync')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
app.conf.broker_url = REDIS_CONNECTION
app.conf.beat_schedule = {
    '10-second-beat': {
        'task': 'sync.tasks.housekeeping_task',
        'schedule': 60.0,
        'args': ()
    },
}
