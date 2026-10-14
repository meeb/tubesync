---
appliesTo:
- type: capability
  id: download-media
- type: capability
  id: fetch-media-metadata
- type: capability
  id: refresh-formats
references:
- kind: code
  role: implementation
  target: tubesync/sync/tasks.py#wait_for_errors
- kind: doc
  role: intent
  target: README.md
---

# Downloads and lookups pause while YouTube is limiting requests

When recent tasks were answered "Too Many Requests", the next download, metadata fetch or format refresh waits ten seconds for each such answer before it starts, showing "paused (429)".

## Rationale

The project asks to be polite to YouTube to avoid throttling or bans.
