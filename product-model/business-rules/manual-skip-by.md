---
appliesTo:
- type: entity
  id: media
  effect: changes
  to: Manually skipped
permits:
- actors:
  - user
- unattended: true
  when:
  - entity: source
    fact: Delete old media
    is: 'On'
- unattended: true
  when:
  - entity: source
    fact: Delete removed media
    is: 'On'
references:
- kind: code
  role: implementation
  target: tubesync/sync/views/media.py#MediaSkipView
- kind: code
  role: implementation
  target: tubesync/sync/tasks.py#cleanup_old_media
- kind: code
  role: implementation
  target: tubesync/sync/tasks.py#cleanup_removed_media
---

# Media becomes manually skipped only by the User or by its source cleanup settings

Media is marked never to be downloaded when the User skips it, when its Source deletes old media and it has expired, or when its Source deletes removed media and it is no longer listed.
