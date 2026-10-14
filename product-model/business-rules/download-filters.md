---
appliesTo:
- type: capability
  id: check-media
- type: capability
  id: check-source-media
- type: entity
  id: source
  facts:
  - Filter text
  - Invert filter text
  - Filter seconds
  - Filter seconds mode
  - Download cap
  - Delete old media
  - Days to keep
references:
- kind: code
  role: implementation
  target: tubesync/sync/filtering.py#filter_media
---

# Media that is unpublished, too old, expired or outside the source filters is skipped

Media without a published time, published before the Source download cap, downloaded longer ago than the days to keep when old media is deleted, whose title does not match the filter text (or matches it when inverted), or whose duration breaks the filter seconds limit is skipped by the system and not downloaded.
