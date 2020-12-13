import os
import multiprocessing


def get_num_workers():
    # Sane max workers to allow to be spawned
    cpu_workers = multiprocessing.cpu_count() * 2 + 1
    # But default to 3
    try:
        num_workers = int(os.getenv('GUNICORN_WORKERS', 3))
    except ValueError:
        num_workers = cpu_workers
    if 0 > num_workers > cpu_workers:
        num_workers = cpu_workers
    return num_workers


def get_bind():
    host = os.getenv('LISTEN_HOST', '127.0.0.1')
    port = os.getenv('LISTEN_PORT', '8080')
    return '{}:{}'.format(host, port)


workers = get_num_workers()
timeout = 30
chdir = '/app'
daemon = False
pidfile = '/run/app/gunicorn.pid'
user = 'app'
group = 'app'
loglevel = 'info'
errorlog = '-'
accesslog = '/dev/null'  # Access logs are printed to stdout from nginx
django_settings = 'django.settings'
bind = get_bind()
