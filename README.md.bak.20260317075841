# TubeSync
================

TubeSync is a PVR (personal video recorder) for YouTube. It is designed to synchronize channels and playlists from YouTube to local directories and update your media server once media is downloaded.

## Features
------------

*   Synchronize channels and playlists from YouTube to local directories
*   Update your media server once media is downloaded
*   Support for multiple media servers (currently only Plex and Jellyfin)
*   Gradual retrying of failures with back-off timers for reliable media downloads
*   Basic HTTP authentication for secure access to the web interface
*   Support for multiple architectures (amd64 and arm64)

## Requirements
------------

*   Docker or Podman for containerized installation
*   A media server (currently only Plex and Jellyfin) for media server updating
*   A local directory for media downloads and thumbnails
*   A web browser for accessing the web interface

## Installation
------------

### Containerized Installation

1.  Pull the latest container image: `ghcr.io/meeb/tubesync:latest`
2.  Create a directory for config data and downloads: `mkdir /some/directory/tubesync-config` and `mkdir /some/directory/tubesync-downloads`
3.  Run the container: `docker run -d --name tubesync -e PUID=1000 -e PGID=1000 -e TZ=Europe/London -v /some/directory/tubesync-config:/config -v /some/directory/tubesync-downloads:/downloads -p 4848:4848 --stop-timeout 1800 ghcr.io/meeb/tubesync:latest`

### Manual Installation

1.  Clone or download the repository
2.  Install dependencies with `pipenv install`
3.  Copy `tubesync/tubesync/local_settings.py.example` to `tubesync/tubesync/local_settings.py` and edit it as appropriate
4.  Run migrations with `./manage.py migrate`
5.  Collect static files with `./manage.py collectstatic`
6.  Set up your prefered WSGI server, such as `gunicorn` pointing it to the application in `tubesync/tubesync/wsgi.py`
7.  Set up your proxy server such as `nginx` and forward it to the WSGI server
8.  Check the web interface is working
9.  Run `./manage.py process_tasks` as the background task worker to index and download media

## Configuration
------------

### Environment Variables

*   `DJANGO_SECRET_KEY`: Django's SECRET_KEY
*   `DJANGO_URL_PREFIX`: Run TubeSync in a sub-URL on the web server
*   `TUBESYNC_DEBUG`: Enable debugging
*   `TUBESYNC_HOSTS`: Django's ALLOWED_HOSTS, defaults to `*`
*   `TUBESYNC_RESET_DOWNLOAD_DIR`: Toggle resetting `/downloads` permissions, defaults to True
*   `TUBESYNC_VIDEO_HEIGHT_CUTOFF`: Smallest video height in pixels permitted to download
*   `TUBESYNC_RENAME_SOURCES`: Rename media files from selected sources
*   `TUBESYNC_RENAME_ALL_SOURCES`: Rename media files from all sources
*   `TUBESYNC_DIRECTORY_PREFIX`: Enable `video` and `audio` directory prefixes in `/downloads`
*   `TUBESYNC_SHRINK_NEW`: Filter unneeded information from newly retrieved metadata
*   `TUBESYNC_SHRINK_OLD`: Filter unneeded information from metadata loaded from the database
*   `GUNICORN_WORKERS`: Number of `gunicorn` (web request) workers to spawn
*   `LISTEN_HOST`: IP address for `gunicorn` to listen on
*   `LISTEN_PORT`: Port number for `gunicorn` to listen on
*   `HTTP_USER`: Sets the username for HTTP basic authentication
*   `HTTP_PASS`: Sets the password for HTTP basic authentication
*   `DATABASE_CONNECTION`: Optional external database connection details

## Usage
-----

### Adding Sources

1.  Pick your favourite YouTube channels or playlists
2.  Pop over to the "sources" tab
3.  Click the add button
4.  Enter the URL and validate it
5.  Select the features you want, such as how often you want to index your source and the quality of the media you want to download
6.  Click "add source"

### Waiting

1.  That's about it
2.  All other actions are automatic and performed on timers by scheduled tasks
3.  You can see what your TubeSync instance is doing on the "tasks" tab
4.  As media is indexed and downloaded it will appear in the "media" tab

### Media Server Updating

1.  Currently TubeSync supports Plex and Jellyfin as media servers
2.  You can add your local Jellyfin or Plex server under the "media servers" tab

## Logging and Debugging
-----------------------

1.  TubeSync outputs useful logs, errors and debugging information to the console
2.  You can view these with `docker logs --follow tubesync`
3.  To include logs with an issue report, please extract a file and attach it to the issue
4.  The command below creates the `TubeSync.logs.txt` file with the logs from the `tubesync` container: `docker logs -t tubesync > TubeSync.logs.txt 2>&1`

## Advanced Usage Guides
-------------------------

*   [Using Plex](https://github.com/meeb/tubesync/blob/main/docs/plex-notes.md)
*   [Import existing media into TubeSync](https://github.com/meeb/tubesync/blob/main/docs/import-existing-media.md)
*   [Sync or create missing metadata files](https://github.com/meeb/tubesync/blob/main/docs/create-missing-metadata.md)
*   [Reset tasks from the command line](https://github.com/meeb/tubesync/blob/main/docs/reset-tasks.md)
*   [Using PostgreSQL, MySQL or MariaDB as database backends](https://github.com/meeb/tubesync/blob/main/docs/other-database-backends.md)
*   [YouTube Proof-of-Origin Tokens](https://github.com/meeb/tubesync/blob/main/docs/youtube-pot.md)
*   [Using cookies](https://github.com/meeb/tubesync/blob/main/docs/using-cookies.md)
*   [Reset metadata](https://github.com/meeb/tubesync/blob/main/docs/reset-metadata.md)

## FAQ
----

*   Can I use TubeSync to download single videos?
    *   No, TubeSync is designed to repeatedly scan and download new media from channels or playlists
*   Does TubeSync support any other video platforms?
    *   At the moment, no
*   Is there a progress bar?
    *   No
*   Are there alerts when a download is complete?
    *   No
*   There are errors in my "tasks" tab!
    *   You only really need to worry about these if there is a permanent failure

## Contributing
------------

All properly formatted and sensible pull requests, issues and comments are welcome.