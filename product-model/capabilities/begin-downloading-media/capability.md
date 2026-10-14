---
availability:
- {place: web}
domain: media
references:
- kind: code
  role: implementation
  target: tubesync/sync/views/media.py#MediaRedownloadView
- kind: code
  role: implementation
  target: tubesync/sync/models/media__tasks.py#download_checklist
---

# Begin downloading media

The User starts the download of a media item that is not downloaded but has a matching format, even when the Source filters skipped it.
