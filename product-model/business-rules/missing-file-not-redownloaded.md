---
appliesTo:
- type: capability
  id: check-media
- type: capability
  id: redownload-media
references:
- kind: code
  role: implementation
  target: tubesync/sync/signals.py#media_post_save
---

# A downloaded file deleted outside TubeSync is not downloaded again on its own

When the file of downloaded media disappears from disk, TubeSync marks the media skipped rather than downloading it again; the User redownloads it when wanted.
