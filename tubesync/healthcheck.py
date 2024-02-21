#!/usr/bin/env python3
'''

    Perform an HTTP request to a URL and exit with an exit code of 1 if the
    request did not return an HTTP/200 status code.

    Usage:
    $ ./healthcheck.py http://some.url.here/healthcheck/resource

'''


import sys
import requests
import os

TIMEOUT = 5  # Seconds

def do_heatlhcheck(url, username, password):
    headers = {'User-Agent': 'healthcheck'}
    if username and password:
        response = requests.get(url, headers=headers, timeout=TIMEOUT, auth=(username, password))
    else:
        response = requests.get(url, headers=headers, timeout=TIMEOUT)
    return response.status_code == 200

def get_http_auth():
    if "HTTP_USER" in os.environ:
        # Attempt to get the value of the environment variable
        username = os.environ["HTTP_USER"]
        password = os.environ["HTTP_PASS"]
    else:
        username = False 
        password = False
    return username, password


if __name__ == '__main__':
    username, password = get_http_auth()
    try:
        url = sys.argv[1]
    except IndexError:
        sys.stderr.write('URL must be supplied\n')
        sys.exit(1)

    if do_heatlhcheck(url, username, password):
        sys.exit(0)
    else:
        sys.exit(1)
