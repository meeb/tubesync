import os
from django.core.asgi import get_asgi_application
from django_simple_task import django_simple_task_middlware


os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tubesync.settings')
application = django_simple_task_middlware(get_asgi_application())
