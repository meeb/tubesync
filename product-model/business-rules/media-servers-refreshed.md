---
appliesTo:
- type: capability
  id: refresh-media-servers
- type: capability
  id: download-media
- type: capability
  id: delete-old-media
references:
- kind: code
  role: implementation
  target: tubesync/sync/tasks.py#schedule_media_servers_update
---

# Media servers refresh their libraries after media is downloaded or removed

Every completed download and every removal of expired or missing media asks each media server to refresh its listed libraries.
