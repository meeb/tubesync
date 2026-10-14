---
availability:
- {place: web}
domain: media
references:
- kind: code
  role: implementation
  target: tubesync/sync/tasks.py#download_media_thumbnails
- kind: code
  role: implementation
  target: tubesync/sync/models/media__tasks.py#download_thumbnails
- kind: code
  role: implementation
  target: tubesync/sync/models/media__tasks.py#copy_thumbnail
---

# Download thumbnails

TubeSync downloads and keeps a thumbnail for each media item, resized for the interface, and copies it next to the media file when the Source asks for thumbnails.
