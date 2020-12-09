import logging


log = logging.getLogger('tubesync')
log.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s [%(name)s/%(levelname)s] %(message)s')
ch.setFormatter(formatter)
log.addHandler(ch)
