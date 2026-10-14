---
availability:
- {place: web}
references:
- kind: code
  role: implementation
  target: tubesync/sync/tasks.py#schedule_indexing
- kind: code
  role: implementation
  target: tubesync/sync/tasks.py#index_source
- kind: code
  role: implementation
  target: tubesync/sync/tasks.py#cleanup_removed_media
- kind: code
  role: implementation
  target: tubesync/sync/models/source.py#Source
- kind: doc
  role: intent
  target: README.md
---

# Index source

On its schedule TubeSync asks YouTube which videos, and for channels which live streams, a Source has. New videos become media items whose metadata and thumbnails are then fetched. When the Source deletes removed media, media no longer listed is removed.
