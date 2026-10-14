---
availability:
- {place: web}
domain: media-servers
references:
- kind: code
  role: implementation
  target: tubesync/sync/tasks.py#schedule_media_servers_update
- kind: code
  role: implementation
  target: tubesync/sync/tasks.py#rescan_media_server
- kind: code
  role: implementation
  target: tubesync/sync/mediaservers.py#PlexMediaServer
- kind: code
  role: implementation
  target: tubesync/sync/mediaservers.py#JellyfinMediaServer
---

# Refresh media servers

When media is downloaded or removed, TubeSync asks each media server to rescan the libraries listed for it.
