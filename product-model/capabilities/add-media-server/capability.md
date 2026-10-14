---
availability:
- {place: web}
domain: media-servers
references:
- kind: code
  role: implementation
  target: tubesync/sync/views/mediaservers.py#AddMediaServerView
- kind: code
  role: implementation
  target: tubesync/sync/mediaservers.py#PlexMediaServer
- kind: code
  role: implementation
  target: tubesync/sync/mediaservers.py#JellyfinMediaServer
- kind: code
  role: implementation
  target: tubesync/sync/forms.py#PlexMediaServerForm
- kind: code
  role: implementation
  target: tubesync/sync/forms.py#JellyfinMediaServerForm
---

# Add media server

The User connects a Plex or Jellyfin server so TubeSync can ask it to refresh its libraries. TubeSync saves the server only after a test connection succeeds and every listed library exists on it.
