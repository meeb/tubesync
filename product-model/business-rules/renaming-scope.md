---
appliesTo:
- type: capability
  id: rename-media-files
- type: capability
  id: check-source-media
references:
- kind: code
  role: implementation
  target: tubesync/sync/tasks.py#rename_all_media_for_source
---

# Downloaded files are renamed only for sources the deployment renames

Files follow a changed media format only when the deployment renames all Sources, which it does by default, or lists the Source directory among the Sources to rename.
