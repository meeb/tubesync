---
availability:
- {place: web}
domain: sources
references:
- kind: code
  role: implementation
  target: tubesync/sync/views/sources.py#UpdateSourceView
- kind: code
  role: implementation
  target: tubesync/sync/signals.py#source_pre_save
- kind: code
  role: implementation
  target: tubesync/sync/signals.py#source_post_save
---

# Edit source

The User changes a Source settings on the same form used to add it. Saving re-checks all of its media against the new settings.
