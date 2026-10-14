---
appliesTo:
- type: capability
  id: delete-old-media
- type: capability
  id: index-source
references:
- kind: code
  role: implementation
  target: tubesync/sync/signals.py#media_post_delete
---

# Media removed from TubeSync is remembered as skipped

When TubeSync removes a media item, it keeps a manually skipped record with its key, title and published time, so indexing the Source again never downloads it again.
