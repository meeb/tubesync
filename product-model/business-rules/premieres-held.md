---
appliesTo:
- type: capability
  id: fetch-media-metadata
- type: capability
  id: release-premiere
references:
- kind: code
  role: implementation
  target: tubesync/sync/tasks.py#upcoming_media
- kind: code
  role: implementation
  target: tubesync/sync/tasks.py#download_media_metadata
---

# Premieres are not downloaded before they start

Media YouTube reports as an upcoming premiere waits until its start time has passed before its metadata is fetched and it is considered for download.
