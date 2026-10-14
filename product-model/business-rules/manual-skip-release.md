---
appliesTo:
- type: entity
  id: media
  effect: changes
  from: Manually skipped
permits:
- actors:
  - user
references:
- kind: code
  role: implementation
  target: tubesync/sync/signals.py#media_post_save
- kind: code
  role: implementation
  target: tubesync/sync/views/media.py#MediaEnableView
---

# Only the User takes media out of Manually skipped

Manually skipped media is never re-checked, refreshed or downloaded by TubeSync on its own; only the User unskips it or begins its download.
