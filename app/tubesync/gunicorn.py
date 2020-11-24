import os
import multiprocessing


def get_num_workers():
    cpu_workers = multiprocessing.cpu_count() * 2 + 1
    try:
        num_workers = int(os.getenv('GUNICORN_WORKERS', 1))
    except ValueError:
        num_workers = cpu_workers
    if 0 > num_workers > cpu_workers:
        num_workers = cpu_workers
    return num_workers


def get_bind():
    host = os.getenv('LISTEN_HOST', '0.0.0.0')
    port = os.getenv('LISTEN_PORT', '8080')
    return '{}:{}'.format(host, port)


workers = get_num_workers()
timeout = 30
chdir = '/app'
daemon = False
pidfile = '/run/www/gunicorn.pid'
user = 'www'
group = 'www'
loglevel = 'info'
errorlog = '-'
accesslog = '-'
django_settings = 'django.settings'
bind = get_bind()
