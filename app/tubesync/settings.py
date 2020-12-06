from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent


VERSION = 0.1
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
]


ROOT_URLCONF = 'tubesync.urls'


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
TIME_ZONE = 'UTC'
USE_I18N = True
USE_L10N = True
USE_TZ = True


STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'static'
#MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
SYNC_VIDEO_ROOT = BASE_DIR / 'downloads' / 'video'
SYNC_AUDIO_ROOT = BASE_DIR / 'downloads' / 'audio'
SASS_PROCESSOR_ROOT = STATIC_ROOT


ROBOTS = '''
User-agent: *
Disallow: /
'''.strip()


HEALTHCHECK_FIREWALL = True
HEALTHCHECK_ALLOWED_IPS = ('127.0.0.1',)


MAX_ATTEMPTS = 10                           # Number of times tasks will be retried
MAX_RUN_TIME = 1800                         # Maximum amount of time in seconds a task can run
BACKGROUND_TASK_RUN_ASYNC = True            # Run tasks async in the background
BACKGROUND_TASK_ASYNC_THREADS = 2           # Number of async tasks to run at once
BACKGROUND_TASK_PRIORITY_ORDERING = 'DESC'  # Process high priority tasks first


SOURCES_PER_PAGE = 25
MEDIA_PER_PAGE = 25


INDEX_SOURCE_EVERY = 21600  # Seconds between indexing sources, 21600 = every 6 hours


MAX_MEDIA_THUMBNAIL_SIZE = (320, 240)       # Max size in pixels for media thumbnails


YOUTUBE_DEFAULTS = {
    'age_limit': 99,        # 'Age in years' to spoof
}


try:
    from .local_settings import *
except ImportError as e:
    import sys
    sys.stderr.write(f'Unable to import local_settings: {e}\n')
    sys.exit(1)
