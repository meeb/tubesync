#!/usr/bin/python3

"""
Perform an HTTP request to a URL and exit with an exit code of 1 if the request
did not return an HTTP/200 status code.

Usage:
$ ./healthcheck.py http://some.url.here/healthcheck/resource
"""

import os
import sys
import requests

# Timeout in seconds for HTTP requests
TIMEOUT: int = 5

# HTTP authentication credentials from environment variables
HTTP_USER: str = os.getenv("HTTP_USER")
HTTP_PASS: str = os.getenv("HTTP_PASS")

# Disable proxy for healthcheck requests
os.environ["no_proxy"] = "*"


def do_healthcheck(url: str) -> bool:
    """
    Perform a GET request to the specified URL and return True if the response
    status code is 200, False otherwise.

    :param url: URL to perform the healthcheck on
    :return: True if the healthcheck was successful, False otherwise
    """
    headers = {"User-Agent": "healthcheck"}
    auth = None
    if HTTP_USER and HTTP_PASS:
        auth = (HTTP_USER, HTTP_PASS)
    try:
        response = requests.get(url, headers=headers, auth=auth, timeout=TIMEOUT)
        response.raise_for_status()  # Raise an exception for bad status codes
        return True
    except requests.RequestException as e:
        print(f"Error performing healthcheck: {e}", file=sys.stderr)
        return False


if __name__ == "__main__":
    # If the service is intentionally down, exit immediately
    if os.path.exists("/run/service/gunicorn/down"):
        sys.exit(0)

    # Check if a URL was provided as a command-line argument
    if len(sys.argv) != 2:
        print("URL must be supplied", file=sys.stderr)
        sys.exit(1)

    url = sys.argv[1]
    if do_healthcheck(url):
        sys.exit(0)
    else:
        sys.exit(1)
