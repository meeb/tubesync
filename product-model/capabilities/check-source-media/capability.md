---
availability:
- {place: web}
domain: media
references:
- kind: code
  role: implementation
  target: tubesync/sync/tasks.py#save_all_media_for_source
- kind: code
  role: implementation
  target: tubesync/sync/signals.py#source_post_save
---

# Check all media of a source

After a Source is saved or indexed, TubeSync re-checks every one of its media items against the current settings, refreshes formats for media that has none matching, and then renames downloaded files where renaming applies.
