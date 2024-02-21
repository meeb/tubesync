import os
import sys
import requests

def health_check(url):
    # Retrieve HTTP basic auth credentials from environment variables
    user = os.getenv('HTTP_USER')
    password = os.getenv('HTTP_PASS')

    try:
        if user and password:
            response = requests.get(url, auth=(user, password))
        else:
            response = requests.get(url)

        # Check if the response code is 200
        if response.status_code == 200:
            print("Health check passed!")
        else:
            print(f"Health check failed! Received status code: {response.status_code}")
            sys.exit(1)
    except Exception as e:
        print(f"Health check failed! Exception: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python healthcheck.py <URL>")
        sys.exit(1)
    
    url = sys.argv[1]
    health_check(url)
