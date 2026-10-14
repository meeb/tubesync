---
appliesTo:
- type: entity
  id: media-server
  facts:
  - Token
references:
- kind: code
  role: implementation
  target: tubesync/sync/views/mediaservers.py#MediaServerView
---

# A media server token is shown only in part

The media server page shows the first characters of the token and marks it hidden.
