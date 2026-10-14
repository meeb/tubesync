---
appliesTo:
- type: entity
  id: media
  effect: changes
  to: Downloading
permits:
- actors:
  - user
- unattended: true
references:
- kind: code
  role: implementation
  target: tubesync/sync/signals.py#media_post_save
- kind: code
  role: implementation
  target: tubesync/sync/views/media.py#MediaRedownloadView
---

# Media is queued for download by TubeSync checks or at the User request

TubeSync queues media whose format matches and whose Source filters keep it; the User may also queue any media item that has a matching format, whatever the filters say.
