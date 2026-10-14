---
appliesTo:
- type: capability
  id: check-media
- type: capability
  id: check-source-media
- type: entity
  id: source
  facts:
  - Download media
references:
- kind: code
  role: implementation
  target: tubesync/sync/signals.py#media_post_save
---

# Media of a source that does not download media is only indexed

While Download media is off, the media of a Source is indexed and its metadata fetched, but no download is queued; turning it on queues the downloads that match.
