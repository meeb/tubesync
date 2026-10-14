---
availability:
- {place: web}
domain: media
references:
- kind: code
  role: implementation
  target: tubesync/sync/views/media.py#MediaSkipView
- kind: code
  role: implementation
  target: tubesync/sync/templates/sync/media-skip.html
---

# Skip media

The User marks a media item to never be downloaded. For downloaded media this deletes its file and the files saved beside it.
