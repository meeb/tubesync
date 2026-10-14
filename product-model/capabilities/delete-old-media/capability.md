---
availability:
- {place: web}
domain: media
references:
- kind: code
  role: implementation
  target: tubesync/sync/tasks.py#cleanup_old_media
- kind: code
  role: implementation
  target: tubesync/sync/signals.py#media_post_delete
- kind: code
  role: implementation
  target: tubesync/sync/models/source.py#Source
---

# Delete old media

For Sources that delete old media, TubeSync removes media downloaded longer ago than the days to keep. It runs whenever any Source is indexed.
