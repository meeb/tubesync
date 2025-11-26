from django import VERSION as DJANGO_VERSION
from pathlib import Path
from common.huey import sqlite_tasks
from common.utils import getenv
from sync.choices import TaskQueue


BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_BASE_DIR = BASE_DIR
DOWNLOADS_BASE_DIR = BASE_DIR


VERSION = '0.15.12'
SECRET_KEY = ''
DEBUG = 'true' == getenv('TUBESYNC_DEBUG').strip().lower()
ALLOWED_HOSTS = []


INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'sass_processor',
    'django_huey',
    'common',
    'sync',
]


MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'common.middleware.MaterializeDefaultFieldsMiddleware',
    'common.middleware.BasicAuthMiddleware',
]


ROOT_URLCONF = 'tubesync.urls'
FORCE_SCRIPT_NAME = None


DJANGO_HUEY = {
    'default': TaskQueue.LIMIT.value,
    'queues': dict(),
    'verbose': None if DEBUG else False,
}
for queue_name in TaskQueue.values:
    queues = DJANGO_HUEY['queues']
    if TaskQueue.LIMIT.value == queue_name:
        queues[queue_name] = sqlite_tasks(queue_name, prefix='net')
    elif TaskQueue.NET.value == queue_name:
        queues[queue_name] = sqlite_tasks(queue_name, thread=True, workers=0)
    else:
        queues[queue_name] = sqlite_tasks(queue_name, thread=True)
for django_huey_queue in DJANGO_HUEY['queues'].values():
    connection = django_huey_queue.get('connection')
    if connection:
        filepath = Path('/.' + connection.get('filename') or '').resolve(strict=False)
        filepath.parent.mkdir(exist_ok=True, parents=True)
    consumer = django_huey_queue.get('consumer')
    if consumer:
        consumer['verbose'] = DJANGO_HUEY.get('verbose', False)


TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'common.context_processors.app_details',
            ],
        },
    },
]


STATICFILES_FINDERS = [
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
    'sass_processor.finders.CssFinder',
]


WSGI_APPLICATION = 'tubesync.wsgi.application'


DATABASES = {}


DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'


AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


LANGUAGE_CODE = 'en-us'
TIME_ZONE = getenv('TZ', 'UTC')
USE_I18N = True
# Removed in Django 5.0, set to True by default in Django 4.0
# https://docs.djangoproject.com/en/4.1/releases/4.0/#localization
if DJANGO_VERSION[0:3] < (4, 0, 0):
    USE_L10N = True
USE_TZ = True


STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'static'
#MEDIA_URL = '/media/'
MEDIA_ROOT = CONFIG_BASE_DIR / 'media'
DOWNLOAD_ROOT = DOWNLOADS_BASE_DIR / 'downloads'
DOWNLOAD_VIDEO_DIR = 'video'
DOWNLOAD_AUDIO_DIR = 'audio'
SASS_PROCESSOR_ROOT = STATIC_ROOT


ROBOTS = '''
User-agent: *
Disallow: /
'''.strip()


USE_X_FORWARDED_HOST = True
USE_X_FORWARDED_PORT = True
X_FRAME_OPTIONS = 'SAMEORIGIN'


BASICAUTH_DISABLE = True
BASICAUTH_REALM = 'Authenticate to TubeSync'
BASICAUTH_ALWAYS_ALLOW_URIS = ('/healthcheck',)
BASICAUTH_USERS = {}


HEALTHCHECK_FIREWALL = True
HEALTHCHECK_ALLOWED_IPS = ('127.0.0.1',)


MAX_ATTEMPTS = 15                           # Number of times tasks will be retried
MAX_RUN_TIME = 12*(60*60)                   # Maximum amount of time in seconds a task can run
BACKGROUND_TASK_PRIORITY_ORDERING = 'ASC'   # Use 'niceness' task priority ordering
COMPLETED_TASKS_DAYS_TO_KEEP = 7            # Number of days to keep completed tasks
MAX_ENTRIES_PROCESSING = 0                  # Number of videos to process on source refresh (0 for no limit)

SOURCES_PER_PAGE = 100
MEDIA_PER_PAGE = 144
TASKS_PER_PAGE = 100


MEDIA_THUMBNAIL_WIDTH = 430                 # Width in pixels to resize thumbnails to
MEDIA_THUMBNAIL_HEIGHT = 240                # Height in pixels to resize thumbnails to


VIDEO_HEIGHT_CUTOFF = 240                   # Smallest resolution in pixels permitted to download
VIDEO_HEIGHT_IS_HD = 500                    # Height in pixels to count as 'HD'
VIDEO_HEIGHT_UPGRADE = True                 # Download again when a format with more pixels is available



# If True source directories are prefixed with their type (either 'video' or 'audio')
# e.g. /downloads/video/SomeSourceName
# If False, sources are placed directly in /downloads
# e.g. /downloads/SomeSourceName
SOURCE_DOWNLOAD_DIRECTORY_PREFIX = True


YOUTUBE_DL_CACHEDIR = None
YOUTUBE_DL_TEMPDIR = None
YOUTUBE_DL_SKIP_UNAVAILABLE_FORMAT = False
YOUTUBE_DEFAULTS = {
    'color': 'never',       # Do not use colours in output
    'age_limit': 99,        # 'Age in years' to spoof
    'ignoreerrors': False,  # When true, yt-dlp does not raise descriptive exceptions
    'cachedir': False,      # Disable on-disk caching
    'addmetadata': True,    # Embed metadata during postprocessing where available
    'updatetime': True,     # Set mtime in recent versions
    'update_self': False,   # Updates are handled by pip
    'geo_verification_proxy': getenv('geo_verification_proxy').strip() or None,
    'sleep_interval_requests': 3,
    'sleep_interval_subtitles': (60)*2,
    'max_sleep_interval': (60)*5,
    'sleep_interval': 0.25,
    'extractor_args': {
        'youtubepot-bgutilhttp': {
            'base_url': ['http://127.0.0.1:4416'],
        },
    },
    'postprocessor_args': {
        'videoremuxer+ffmpeg': ['-bsf:v', 'setts=pts=DTS'],
    },
    'js_runtimes': {
        'deno': {'path': None,},
        'quickjs': {'path': None,},
    },
}
COOKIES_FILE = CONFIG_BASE_DIR / 'cookies.txt'
YOUTUBE_INFO_SLEEP_REQUESTS = 1


MEDIA_FORMATSTR_DEFAULT = '{yyyy_mm_dd}_{source}_{title}_{key}_{format}.{ext}'


RENAME_ALL_SOURCES = True
RENAME_SOURCES = list()


# WARNING WARNING WARNING
# Below this line, the logic and formulas must remain as they are.
# Changing them is very likely to break the software in weird ways.
# To change anything, you should adjust a variable above or in the
# 'local_settings.py' file instead.
# You have been warned!

try:
    from .local_settings import * # noqa
except ImportError as e:
    import sys
    sys.stderr.write(f'Unable to import local_settings: {e}\n')
    sys.exit(1)


try:
    MAX_RUN_TIME = int(str(MAX_RUN_TIME), base=10)
except:
    # fall back to the default value from:
    # https://github.com/django-background-tasks/django-background-tasks/blob/12c8f328e4ba704bd7d91534bb6569e70197b949/background_task/settings.py#L28
    MAX_RUN_TIME = 3600

# Tasks scheduled with `background_task` need a chance to finish
if MAX_RUN_TIME < 600:
    MAX_RUN_TIME = 600

DOWNLOAD_MEDIA_DELAY = 1 + round(MAX_RUN_TIME / 100)

BACKGROUND_TASK_RUN_ASYNC = False
BACKGROUND_TASK_ASYNC_THREADS = 1
# MAX_BACKGROUND_TASK_ASYNC_THREADS = 1


from .dbutils import patch_ensure_connection # noqa
patch_ensure_connection()
