---
id: tubesync
summary: 'A personal video recorder for YouTube: keep channels and playlists synced to local folders in the quality you choose, and have your media server refresh when new media arrives.'
category: media-management
tags:
- youtube
- pvr
- downloads
- media-server
- self-hosted
authors:
- name: meeb and the TubeSync contributors
  url: https://github.com/meeb/tubesync
license: AGPL-3.0-only
languages:
- en
limitations:
- Sources are YouTube channels and YouTube playlists only.
- TubeSync only reads from YouTube and downloads; it never changes anything on YouTube.
- There are no user accounts or roles; one person administers TubeSync through its web interface, optionally behind a single HTTP username and password set in the deployment.
- Media servers are Plex or Jellyfin, and TubeSync only asks them to refresh their libraries.
- Installation-wide behavior such as renaming, upgrades and directory prefixes is set when the container starts, not in the web interface.
references:
- kind: doc
  role: intent
  target: README.md
- kind: code
  role: context
  target: tubesync/tubesync/local_settings.py.container
---

# TubeSync

TubeSync keeps YouTube channels and playlists synchronized to local directories. The User adds
each channel or playlist as a Source and chooses how often it is indexed, which of its media is
downloaded, in what resolution and codecs with what fallback, how files are named, and which
companion files (thumbnails, NFO, JSON, subtitles, channel images) are written beside them.

From then on everything runs on scheduled tasks: indexing finds new media, metadata and
thumbnails are fetched, each media item is matched against its Source format and filters,
downloads run and are retried with growing delays when they fail, files are renamed when the
media format changes, old or removed media is cleaned up, and Plex or Jellyfin servers are asked
to refresh their libraries. The web interface shows the dashboard, Sources, media, tasks,
services and media servers, and lets the User skip, unskip, redownload, play or save individual
media and steer the task queue.

## Intent

The README calls TubeSync "a PVR (personal video recorder) for YouTube" with "a built-in
download client", designed "to synchronize channels and playlists from YouTube to local
directories and update your media server once media is downloaded", for people who "want to
watch YouTube videos in particular quality or settings from your local media server". It aims
"to be as hands-free as possible", with "gradual retrying of failures with back-off timers" so
that media which fails to download is retried for an extended period. It asks its users to be
polite to YouTube, indexing as rarely and downloading as few at once as their needs allow.
