---
availability:
- {place: web}
domain: media
references:
- kind: code
  role: implementation
  target: tubesync/sync/tasks.py#upgrade_media
- kind: code
  role: implementation
  target: tubesync/tubesync/settings.py
---

# Upgrade media

After a video downloads, TubeSync tries again later and downloads it anew when a format with more lines than the saved file has become available. It exists only while the deployment allows upgrades, which it does by default.
