---
availability:
- {place: web}
domain: media
references:
- kind: code
  role: implementation
  target: tubesync/sync/tasks.py#upcoming_media
- kind: code
  role: implementation
  target: tubesync/sync/models/media__tasks.py#wait_for_premiere
---

# Release premiere

Every hour TubeSync releases media whose premiere has started so it is fetched and downloaded like any other.
