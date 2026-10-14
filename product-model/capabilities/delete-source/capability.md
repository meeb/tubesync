---
availability:
- {place: web}
domain: sources
references:
- kind: code
  role: implementation
  target: tubesync/sync/views/sources.py#DeleteSourceView
- kind: code
  role: implementation
  target: tubesync/sync/forms.py#ConfirmDeleteSourceForm
- kind: code
  role: implementation
  target: tubesync/sync/signals.py#source_pre_delete
- kind: code
  role: implementation
  target: tubesync/sync/tasks.py#delete_all_media_for_source
---

# Delete source

The User deletes a Source and all its media from TubeSync, choosing whether its downloaded files are removed too.
