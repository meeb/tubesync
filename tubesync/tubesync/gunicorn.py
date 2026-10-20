import os
import multiprocessing


def get_bind():
    host = os.getenv('LISTEN_HOST', '127.0.0.1')
    port = os.getenv('LISTEN_PORT', '8080')
    return f'{host}:{port}'

def get_num_workers():
    # Sane max workers to allow to be spawned
    cpu_workers = multiprocessing.cpu_count() * 2 + 1
    # But default to 3
    num_workers = 3
    try:
        gunicorn_workers = os.getenv('GUNICORN_WORKERS')
        web_concurrency = os.getenv('WEB_CONCURRENCY')
        if gunicorn_workers is not None:
            try:
                num_workers = int(gunicorn_workers)
            except:
                pass
        elif web_concurrency is not None:
            try:
                num_workers = int(web_concurrency)
            except:
                pass
    except:
        pass
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
