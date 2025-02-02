import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_BASE_DIR = BASE_DIR
DOWNLOADS_BASE_DIR = BASE_DIR


VERSION = '0.13.7'
SECRET_KEY = ''
DEBUG = False
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
    'background_task',
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
TIME_ZONE = os.getenv('TZ', 'UTC')
USE_I18N = True
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


X_FRAME_OPTIONS = 'SAMEORIGIN'


BASICAUTH_DISABLE = True
BASICAUTH_REALM = 'Authenticate to TubeSync'
BASICAUTH_ALWAYS_ALLOW_URIS = ('/healthcheck',)
BASICAUTH_USERS = {}


HEALTHCHECK_FIREWALL = True
HEALTHCHECK_ALLOWED_IPS = ('127.0.0.1',)


MAX_ATTEMPTS = 15                           # Number of times tasks will be retried
MAX_RUN_TIME = 1800                         # Maximum amount of time in seconds a task can run
BACKGROUND_TASK_RUN_ASYNC = True            # Run tasks async in the background
BACKGROUND_TASK_ASYNC_THREADS = 1           # Number of async tasks to run at once
MAX_BACKGROUND_TASK_ASYNC_THREADS = 8       # For sanity reasons
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



# If True source directories are prefixed with their type (either 'video' or 'audio')
# e.g. /downloads/video/SomeSourceName
# If False, sources are placed directly in /downloads
# e.g. /downloads/SomeSourceName
SOURCE_DOWNLOAD_DIRECTORY_PREFIX = True


YOUTUBE_DL_CACHEDIR = None
YOUTUBE_DL_TEMPDIR = None
YOUTUBE_DEFAULTS = {
    'color': 'never',       # Do not use colours in output
    'age_limit': 99,        # 'Age in years' to spoof
    'ignoreerrors': True,   # Skip on errors (such as unavailable videos in playlists)
    'cachedir': False,      # Disable on-disk caching
    'addmetadata': True,    # Embed metadata during postprocessing where available
}
COOKIES_FILE = CONFIG_BASE_DIR / 'cookies.txt'


MEDIA_FORMATSTR_DEFAULT = '{yyyy_mm_dd}_{source}_{title}_{key}_{format}.{ext}'


RENAME_ALL_SOURCES = False
RENAME_SOURCES = None


# WARNING WARNING WARNING
# Below this line, the logic and formulas must remain as they are.
# Changing them is very likely to break the software in weird ways.
# To change anything, you should adjust a variable above or in the
# 'local_settings.py' file instead.
# You have been warned!

try:
    from .local_settings import *
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

DOWNLOAD_MEDIA_DELAY = 60 + (MAX_RUN_TIME / 20)

if BACKGROUND_TASK_ASYNC_THREADS > MAX_BACKGROUND_TASK_ASYNC_THREADS:
    BACKGROUND_TASK_ASYNC_THREADS = MAX_BACKGROUND_TASK_ASYNC_THREADS


from .dbutils import patch_ensure_connection
patch_ensure_connection()
