import logging
from django.conf import settings


logging_level = logging.DEBUG if settings.DEBUG else logging.INFO


log = logging.getLogger('tubesync')
log.setLevel(logging_level)
ch = logging.StreamHandler()
ch.setLevel(logging_level)
formatter = logging.Formatter('%(asctime)s [%(name)s/%(levelname)s] %(message)s')
ch.setFormatter(formatter)
log.addHandler(ch)
