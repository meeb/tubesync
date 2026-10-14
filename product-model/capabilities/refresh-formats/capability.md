---
availability:
- {place: web}
domain: media
references:
- kind: code
  role: implementation
  target: tubesync/sync/tasks.py#refresh_formats
- kind: code
  role: implementation
  target: tubesync/sync/tasks.py#RefreshFormatsBackoff
- kind: code
  role: implementation
  target: tubesync/sync/models/media__tasks.py#refresh_formats
---

# Refresh formats

TubeSync fetches the formats, thumbnails and availability YouTube currently offers for a media item that failed to download or had no matching format, retrying for days with growing delays.
