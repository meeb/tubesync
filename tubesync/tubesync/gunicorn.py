import contextlib
import os
import multiprocessing


def get_bind():
    host = os.getenv('LISTEN_HOST', '127.0.0.1')
    port = os.getenv('LISTEN_PORT', '8080')
    return f'{host}:{port}'

def get_num_workers():
    keys = ('GUNICORN_WORKERS', 'WEB_CONCURRENCY')
    # Sane max workers to allow to be spawned
    cpu_workers = 1 + 2 * multiprocessing.cpu_count()
    # But default to 3
    num_workers = 3
    for key in (k for k in keys if k in os.environ):
        value = os.getenv(key)
        with contextlib.suppress(ValueError):
            num_workers = int(float(value))
            break
    return max(1, min(num_workers, cpu_workers))


### Configuration
wsgi_app = 'tubesync.wsgi:application'

##### Logging
# Access logs are printed to stdout from nginx
##accesslog = None
##errorlog = '-'
loglevel = 'info'
capture_output = True
syslog = True
syslog_addr = 'unix:///dev/log'
syslog_facility = 'local2'

##### Process
proc_name = 'gunicorn'
daemon = False
user = 'app'
group = 'app'
chdir = '/app'
control_socket = '/run/app/gunicorn.ctl'
control_socket_disable = True
pidfile = '/run/app/gunicorn.pid'

##### Server
bind = get_bind()
django_settings = 'django.settings'
graceful_timeout = 120
keepalive = 60
max_requests = 1000
max_requests_jitter = 100
timeout = 90
worker_class = 'sync'
workers = get_num_workers()
