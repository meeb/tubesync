---
availability:
- {place: web}
domain: media
references:
- kind: code
  role: implementation
  target: tubesync/sync/signals.py#media_post_save
- kind: code
  role: implementation
  target: tubesync/sync/filtering.py#filter_media
- kind: code
  role: implementation
  target: tubesync/sync/models/media.py#Media
- kind: code
  role: implementation
  target: tubesync/sync/matching.py#get_best_video_format
---

# Check media against its source

Whenever a media item changes, TubeSync decides again whether a format matches its Source and whether the Source filters skip it, and schedules its download, metadata or thumbnail as needed.
