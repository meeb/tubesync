#!/bin/bash

set -x

# Compile SCSS files
/usr/bin/python3 /app/manage.py compilescss

# Collect the static files
/usr/bin/python3 /app/manage.py collectstatic --no-input --link

# Run migrations
/usr/bin/python3 /app/manage.py migrate

# Run what's in CMD
exec "$@"

# eof
