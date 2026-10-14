---
appliesTo:
- type: capability
  id: add-media-server
- type: capability
  id: edit-media-server
references:
- kind: code
  role: implementation
  target: tubesync/sync/models/media_server.py#MediaServer
---

# No two media servers share a host and port

A second media server with the same host and port is refused.
