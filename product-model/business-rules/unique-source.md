---
appliesTo:
- type: capability
  id: add-source
- type: capability
  id: edit-source
- type: entity
  id: source
  facts:
  - Name
  - Key
  - Directory
references:
- kind: code
  role: implementation
  target: tubesync/sync/models/source.py#Source
---

# No two sources share a name, key or directory

Each Source has its own name, YouTube key and directory.
