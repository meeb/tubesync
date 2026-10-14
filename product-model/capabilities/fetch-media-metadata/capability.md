---
availability:
- {place: web}
domain: media
references:
- kind: code
  role: implementation
  target: tubesync/sync/tasks.py#download_media_metadata
- kind: code
  role: implementation
  target: tubesync/sync/models/media.py#Media
---

# Fetch media metadata

For each media item waiting for metadata TubeSync fetches its full details and available formats from YouTube, noticing upcoming premieres and media that offers no formats.
