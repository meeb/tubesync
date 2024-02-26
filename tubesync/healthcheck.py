#!/usr/bin/env python3
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


def do_heatlhcheck(url):
    headers = {'User-Agent': 'healthcheck'}
    auth = None
    if HTTP_USER and HTTP_PASS:
        auth = (HTTP_USER, HTTP_PASS)
    response = requests.get(url, headers=headers, auth=auth, timeout=TIMEOUT)
    return response.status_code == 200


if __name__ == '__main__':
    try:
        url = sys.argv[1]
    except IndexError:
        sys.stderr.write('URL must be supplied\n')
        sys.exit(1)
    if do_heatlhcheck(url):
        sys.exit(0)
    else:
        sys.exit(1)
