# Environment Variables

All environment variables used to configure TubeSync. None of them are required for
a default container installation -- the defaults work out of the box.

## Container

| Name | Description | Default | Example |
|------|-------------|---------|---------|
| `PUID` | User ID the container runs as | `1000` | `1000` |
| `PGID` | Group ID the container runs as | `1000` | `1000` |
| `TZ` | Timezone ([tz database name](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones)) | `UTC` | `Europe/London` |

## Authentication

| Name | Description | Default | Example |
|------|-------------|---------|---------|
| `HTTP_USER` | Username for HTTP basic authentication | *(disabled)* | `some-username` |
| `HTTP_PASS` | Password for HTTP basic authentication | *(disabled)* | `some-secure-password` |

Both `HTTP_USER` and `HTTP_PASS` must be set to enable basic authentication.

## Django

| Name | Description | Default | Example |
|------|-------------|---------|---------|
| `DJANGO_SECRET_KEY` | Django's `SECRET_KEY` for cryptographic signing | *(auto-generated)* | `YJySXnQLB7UVZw2dXKDWxI5lEZaImK6l` |
| `DJANGO_URL_PREFIX` | Run TubeSync under a sub-path on the web server | *(none)* | `/somepath/` |

## Web Server

| Name | Description | Default | Example |
|------|-------------|---------|---------|
| `GUNICORN_WORKERS` | Number of gunicorn (web request) workers to spawn | `2` | `3` |
| `LISTEN_HOST` | IP address for gunicorn to listen on | `0.0.0.0` | `127.0.0.1` |
| `LISTEN_PORT` | Port number for gunicorn to listen on | `4848` | `8080` |
| `TUBESYNC_HOSTS` | Django's `ALLOWED_HOSTS`, comma-separated | `*` | `tubesync.example.com,otherhost.com` |

## Database

| Name | Description | Default | Example |
|------|-------------|---------|---------|
| `DATABASE_CONNECTION` | External database connection string | *(SQLite)* | `postgresql://user:pass@host:port/database` |

See [Using PostgreSQL, MySQL or MariaDB](other-database-backends.md) for details.

## Downloads

| Name | Description | Default | Example |
|------|-------------|---------|---------|
| `TUBESYNC_DIRECTORY_PREFIX` | Enable `video` and `audio` subdirectories in `/downloads` | `True` | `False` |
| `TUBESYNC_RESET_DOWNLOAD_DIR` | Reset `/downloads` directory permissions on startup | `True` | `False` |
| `TUBESYNC_VIDEO_HEIGHT_CUTOFF` | Smallest video height in pixels permitted to download | `240` | `360` |

## Media Renaming

| Name | Description | Default | Example |
|------|-------------|---------|---------|
| `TUBESYNC_RENAME_ALL_SOURCES` | Rename media files from all sources when format changes | `True` | `False` |
| `TUBESYNC_RENAME_SOURCES` | Rename media files only from these source directories (comma-separated) | *(none)* | `Source1_directory,Source2_directory` |

## Metadata

| Name | Description | Default | Example |
|------|-------------|---------|---------|
| `TUBESYNC_SHRINK_NEW` | Filter unneeded information from newly retrieved metadata | `False` | `True` |
| `TUBESYNC_SHRINK_OLD` | Filter unneeded information from metadata loaded from the database | `False` | `True` |

## Debugging

| Name | Description | Default | Example |
|------|-------------|---------|---------|
| `TUBESYNC_DEBUG` | Enable debug logging | `False` | `True` |
