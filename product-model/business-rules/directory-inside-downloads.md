---
appliesTo:
- type: capability
  id: add-source
- type: capability
  id: edit-source
references:
- kind: code
  role: implementation
  target: tubesync/sync/views/sources.py#EditSourceMixin
---

# A source directory stays inside the downloads directory

A directory that would lead outside the downloads directory is refused when a Source is added or edited.
