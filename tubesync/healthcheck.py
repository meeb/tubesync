#!/usr/bin/python3
'''

    Perform an HTTP request to a URL and exit with an exit code of 1 if the
    request did not return an HTTP/200 status code.

    Usage:
    $ ./healthcheck.py http://some.url.here/healthcheck/resource

'''


import os
import sys
import requests


TIMEOUT = 5  # Seconds
HTTP_USER = os.getenv('HTTP_USER')
HTTP_PASS = os.getenv('HTTP_PASS')
# never use proxy for healthcheck requests
os.environ['no_proxy'] = '*'


def do_heatlhcheck(url):
    headers = {'User-Agent': 'healthcheck'}
    auth = None
    if HTTP_USER and HTTP_PASS:
        auth = (HTTP_USER, HTTP_PASS)
    response = requests.get(url, headers=headers, auth=auth, timeout=TIMEOUT)
    return response.status_code == 200


if '__main__' == __name__:
    # if it is marked as intentionally down, nothing else matters
    if os.path.exists('/run/service/gunicorn/down'):
        sys.exit(0)
    try:
        url = sys.argv[1]
    except IndexError:
        try:
            from tubesync.gunicorn import get_bind
            host_port = get_bind()
        except:
            host = os.getenv('LISTEN_HOST', '127.0.0.1')
            port = os.getenv('LISTEN_PORT', '8080')
            host_port = f'{host}:{port}'
        url = f'http://{host_port}/healthcheck'
    if do_heatlhcheck(url):
        sys.exit(0)
    else:
        sys.exit(1)
