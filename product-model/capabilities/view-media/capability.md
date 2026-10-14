---
availability:
- {place: web}
domain: media
references:
- kind: code
  role: implementation
  target: tubesync/sync/views/media.py#MediaItemView
- kind: code
  role: implementation
  target: tubesync/sync/templates/sync/media-item.html
---

# View media

The User reads one media item: its title, description, thumbnail, download state, the format the Source wants, the formats YouTube offers and which ones match, and for downloaded media where and how it was saved.
