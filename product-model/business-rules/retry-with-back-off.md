---
appliesTo:
- type: capability
  id: download-media
- type: capability
  id: refresh-formats
- type: capability
  id: fetch-media-metadata
- type: capability
  id: run-task
references:
- kind: code
  role: implementation
  target: tubesync/sync/tasks.py#RefreshFormatsBackoff
- kind: code
  role: implementation
  target: tubesync/common/huey.py#DjangoBackgroundTasksBackoff
- kind: doc
  role: intent
  target: README.md
---

# Failed work is retried with growing delays

TubeSync aims to be hands-free: a media item whose download fails has its formats refreshed up to fifteen times, waiting ten minutes plus one hour for each attempt so far, and each refresh that finds a matching format queues the download again. Metadata is retried three times ten minutes apart; thumbnails, channel images and Source checks retry with delays that grow with the fourth power of the attempt.

## Rationale

YouTube failures are often temporary, so retrying for days makes downloads reliable without the User watching.
