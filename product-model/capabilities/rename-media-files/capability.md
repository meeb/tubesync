---
availability:
- {place: web}
domain: media
references:
- kind: code
  role: implementation
  target: tubesync/sync/tasks.py#rename_all_media_for_source
- kind: code
  role: implementation
  target: tubesync/sync/models/media.py#Media
- kind: code
  role: implementation
  target: tubesync/tubesync/local_settings.py.container
---

# Rename media files

After the media of a Source is checked, TubeSync moves downloaded files and the files saved beside them to the name and folder the current media format gives. It applies to every Source by default, or only to the Sources the deployment lists.
