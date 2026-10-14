---
appliesTo:
- type: capability
  id: delete-old-media
- type: capability
  id: index-source
- type: entity
  id: source
  facts:
  - Delete files on disk
references:
- kind: code
  role: implementation
  target: tubesync/sync/signals.py#media_post_delete
---

# Files on disk are deleted with their media only when the source deletes files on disk

Removing media from TubeSync by expiry or because it left the channel or playlist deletes its file, subtitles, thumbnails, NFO and JSON files only when the Source has Delete files on disk on.
