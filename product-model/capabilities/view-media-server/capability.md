---
availability:
- {place: web}
domain: media-servers
references:
- kind: code
  role: implementation
  target: tubesync/sync/views/mediaservers.py#MediaServerView
- kind: code
  role: implementation
  target: tubesync/sync/templates/sync/mediaserver.html
---

# View media server

The User reads a media server type, address, HTTPS options and libraries; its token is shown only in part.
