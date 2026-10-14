---
appliesTo:
- type: capability
  id: add-media-server
- type: capability
  id: edit-media-server
references:
- kind: code
  role: implementation
  target: tubesync/sync/mediaservers.py#PlexMediaServer
- kind: code
  role: implementation
  target: tubesync/sync/mediaservers.py#JellyfinMediaServer
---

# A media server is saved only after a test connection finds every listed library

Adding or editing a media server connects to it, checks the answer, and refuses library IDs the server does not have, listing the libraries it does have.
