---
appliesTo:
- type: entity
  id: media
  effect: changes
  to: Downloaded
permits:
- unattended: true
references:
- kind: code
  role: implementation
  target: tubesync/sync/models/media__tasks.py#download_finished
---

# Only TubeSync marks media as downloaded

Media becomes downloaded only when a TubeSync download saves its file; the User can ask for a download but never marks media downloaded.
