---
appliesTo:
- type: entity
  id: media
  effect: changes
  from: Downloaded
  to: Downloaded
permits:
- unattended: true
  when:
  - entity: deployment-settings
    fact: Upgrade media
    is: 'On'
references:
- kind: code
  role: implementation
  target: tubesync/sync/tasks.py#upgrade_media
---

# Downloaded media is upgraded only while the deployment allows upgrades

Downloading a downloaded video again in a format with more lines happens only while upgrades are on, which is the default.
